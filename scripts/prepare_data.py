"""Extract small, traceable publication inputs from an unchanged study directory."""

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import median

from conebound import payload_identity, verify_certificate

METHODS = ("B0", "B1", "B2", "B3", "M1", "M2")


def digest(path):
    result = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


def rows(path):
    with path.open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def extract(root, output):
    inputs = [
        "data/test.jsonl",
        "data/analytic.jsonl",
        "data/bank_manifest.json",
        "configs/frozen_plan.json",
        "results/test/raw.jsonl",
        "results/test/timing.jsonl",
        "results/analytic/raw.jsonl",
        "analysis/summary.json",
        "analysis/base_failure_summary.json",
        "analysis/cohort_comparison.json",
    ]
    hashes = {name: digest(root / name) for name in inputs}
    manifest = json.loads((root / "data/bank_manifest.json").read_text())
    if (
        manifest["manifest_sha256"]
        != sha256(
            canonical({k: v for k, v in manifest.items() if k != "manifest_sha256"})
        ).hexdigest()
    ):
        raise ValueError("bank manifest integrity mismatch")
    if manifest["banks"]["test"]["sha256"] != hashes["data/test.jsonl"]:
        raise ValueError("test bank hash mismatch")
    if manifest["config_sha256"] != hashes["configs/frozen_plan.json"]:
        raise ValueError("frozen plan hash mismatch")
    bank = {item["problem"]["problem_id"]: item for item in rows(root / "data/test.jsonl")}
    families = ["F1", "F2", "F3", "F4", "F5"]
    kappas = [1e-6, 1e-4, 0.01, 1.0, 10.0, 100.0]
    if len(bank) != 240 or Counter(v["metadata"]["family"] for v in bank.values()) != Counter(
        dict.fromkeys(families, 48)
    ):
        raise ValueError("expected 240 bases, 48 per family")
    totals, misses = Counter(), Counter()
    cases = set()
    fixture = None
    statuses = defaultdict(Counter)
    family_counts = defaultdict(Counter)
    base_flags = defaultdict(Counter)
    for line, row in enumerate(rows(root / "results/test/raw.jsonl"), 1):
        pid, k = row["problem_id"], row["kappa"]
        if pid not in bank or k not in kappas or (pid, k) in cases:
            raise ValueError("unknown or duplicate held-out case")
        cases.add((pid, k))
        if row["metadata"] != bank[pid]["metadata"]:
            raise ValueError("result metadata differs from frozen bank")
        if row["input_sha256"] != sha256(canonical(bank[pid])).hexdigest():
            raise ValueError("result input digest differs from frozen bank")
        if set(row["methods"]) != set(METHODS):
            raise ValueError("incomplete held-out method set")
        key = row["metadata"]["family"], k
        totals[key] += 1
        for method, value in row["methods"].items():
            statuses[method][value["status"]] += 1
            counts = family_counts[key[0], method]
            counts["attempted"] += 1
            counts[value["status"]] += 1
            diag = row.get("diagnostics", {}).get(method, {})
            rounded = diag.get("rounded_set_separation", {})
            miss = (
                rounded.get("membership") == "DISJOINT"
                and rounded.get("validation_status") == "VALIDATED"
            )
            contained = (
                rounded.get("membership") == "CONTAINED"
                and rounded.get("validation_status") == "VALIDATED"
            )
            ideal = isinstance(diag.get("ideal_set_proof"), str) and bool(diag["ideal_set_proof"])
            counts["rounded_validated_misses"] += miss
            counts["ideal_proof_misses"] += ideal
            counts["false_certifications"] += value["status"] == "VALIDATED" and (miss or ideal)
            base_flags[pid, method].update(
                {"rounded_miss": miss, "contained": contained, "ideal_miss": ideal}
            )
            if method == "B2":
                misses[key] += miss
        cert = row["methods"].get("M2", {}).get("certificate", {})
        if fixture is None and cert.get("status") == "VALIDATED" and cert.get("supports"):
            problem = bank[pid]["problem"]
            verify_certificate(problem, cert)
            fixture = {
                "problem": problem,
                "certificate": cert,
                "provenance": {
                    "cohort": "protocol-corrected",
                    "raw_file": "results/test/raw.jsonl",
                    "raw_sha256": hashes["results/test/raw.jsonl"],
                    "line": line,
                    "method": "M2",
                    "kappa": row["kappa"],
                    "payload_identity_sha256": payload_identity(problem, cert),
                },
            }
    if len(cases) != 1440 or any(totals[f, k] != 48 for f in families for k in kappas):
        raise ValueError("incomplete held-out bank")
    points = defaultdict(lambda: defaultdict(list))
    excluded, timing_cases = Counter(), set()
    costs = defaultdict(list)
    timing_statuses = defaultdict(Counter)
    valid_base = defaultdict(lambda: True)
    timing_ids = {p for p, item in bank.items() if item["metadata"]["timing_subset"]}
    for row in rows(root / "results/test/timing.jsonl"):
        pid, k, repeat = row["problem_id"], row["kappa"], row["repeat"]
        key = pid, k, repeat
        if (
            pid not in bank
            or not bank[pid]["metadata"]["timing_subset"]
            or k not in kappas
            or isinstance(repeat, bool)
            or not isinstance(repeat, int)
            or not 0 <= repeat < 30
            or key in timing_cases
        ):
            raise ValueError("invalid timing case")
        timing_cases.add(key)
        methods = row["methods"]
        if set(methods) != set(METHODS) or row["metadata"] != bank[pid]["metadata"]:
            raise ValueError("timing methods or metadata differ from frozen design")
        if row["input_sha256"] != sha256(canonical(bank[pid])).hexdigest():
            raise ValueError("timing input digest differs from frozen bank")
        for method, value in methods.items():
            elapsed = value["total_elapsed_ns"]
            if isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed < 0:
                raise ValueError("invalid full-method cost")
            costs[method, pid, k].append(Fraction(elapsed))
            timing_statuses[method][value["status"]] += 1
            valid_base[method, pid] &= value["status"] == "VALIDATED"
        baseline = methods.get("B1", {}).get("widths")
        for method in ("B1", "M1", "M2"):
            value = methods.get(method, {})
            width, elapsed = value.get("widths"), value.get("total_elapsed_ns")
            if (
                not width
                or not baseline
                or len(width) != len(baseline)
                or elapsed is None
                or any(v <= 0 for v in baseline)
            ):
                excluded[method] += 1
                continue
            ratio = median(a / b for a, b in zip(width, baseline))
            if ratio <= 0 or not math.isfinite(ratio):
                excluded[method] += 1
                continue
            points[method][pid].append((elapsed / 1e6, ratio))
    expected_timing = {(p, k, r) for p in timing_ids for k in kappas for r in range(30)}
    if len(timing_ids) != 50 or timing_cases != expected_timing:
        raise ValueError("expected 50 timing bases, six levels, 30 repeats")
    plot = {
        "schema_version": "conebound.figure_data/1",
        "source_sha256": hashes,
        "cohort": "protocol-corrected",
        "families": families,
        "kappas": kappas,
        "known_rounded_misses": [[misses[f, k] for k in kappas] for f in families],
        "attempts": [[totals[f, k] for k in kappas] for f in families],
        "scatter": {
            method: [
                {
                    "problem_id": pid,
                    "cost_ms": median(x[0] for x in values),
                    "width_ratio": median(x[1] for x in values),
                    "rows": len(values),
                }
                for pid, values in sorted(by_base.items())
            ]
            for method, by_base in sorted(points.items())
        },
        "excluded_timing_rows": {m: excluded[m] for m in ("B1", "M1", "M2")},
        "scatter_aggregation": "Per row: median of directional width ratios. Per base: medians over all retained level/repeat rows. This descriptive plot differs from nested primary cost aggregation.",
        "limits": [
            "Other scalar-containment outcomes are unknown, not successes.",
            "Rounded-set separations do not imply exact source-set separations.",
            "M1 coefficients are numerical; no efficiency improvement is demonstrated.",
        ],
    }
    if fixture is None:
        raise ValueError("no recorded VALIDATED held-out certificate with support bounds")
    summary = json.loads((root / "analysis/summary.json").read_text())
    bases = json.loads((root / "analysis/base_failure_summary.json").read_text())
    comparison = json.loads((root / "analysis/cohort_comparison.json").read_text())
    if len(summary["family_method_table"]) != 30:
        raise ValueError("family/method summary is incomplete")
    for record in summary["family_method_table"]:
        counts = family_counts[record["family"], record["method"]]
        for field in (
            "attempted",
            "VALIDATED",
            "NUMERICAL_ONLY",
            "UNSUPPORTED",
            "FAILED",
            "INDETERMINATE",
            "rounded_validated_misses",
            "ideal_proof_misses",
            "false_certifications",
        ):
            if record[field] != counts[field]:
                raise ValueError(
                    f"raw/summary mismatch: {record['family']}/{record['method']}/{field}"
                )
    for record in bases["families"]:
        family, method = record["family"], record["method"]
        members = [p for p, item in bank.items() if item["metadata"]["family"] == family]
        flags = [base_flags[p, method] for p in members]
        eligible = [
            p
            for p in members
            if bank[p]["metadata"]["source_eligibility"]
            in ("eligible_exact_zero_cross_blocks", "eligible_single_contact")
        ]
        expected = {
            "base_count": len(members),
            "in_assumption_base_count": len(eligible),
            "rounded_validated_miss_base_count": sum(v["rounded_miss"] > 0 for v in flags),
            "rounded_unknown_base_count": sum(
                v["rounded_miss"] == 0 and v["contained"] != 6 for v in flags
            ),
            "exact_ideal_miss_in_assumption_base_count": sum(
                base_flags[p, method]["ideal_miss"] > 0 for p in eligible
            ),
            "ideal_unknown_base_count": sum(v["ideal_miss"] == 0 for v in flags),
        }
        if any(record[field] != value for field, value in expected.items()):
            raise ValueError(f"raw/base-frequency summary mismatch: {family}/{method}")
    for method in METHODS:
        base_costs = [median([median(costs[method, pid, k]) for k in kappas]) for pid in timing_ids]
        expected = {
            "median_base_cost_ns": median(base_costs),
            "p95_base_cost_ns": sorted(base_costs)[math.ceil(0.95 * len(base_costs)) - 1],
        }
        saved = comparison["timing"]["corrected"][method]
        if (
            any(Fraction(saved[field]) != value for field, value in expected.items())
            or saved["status_counts"] != dict(timing_statuses[method])
            or saved["all_variants_validated_bases"]
            != sum(valid_base[method, p] for p in timing_ids)
        ):
            raise ValueError(f"raw/nested-timing summary mismatch: {method}")
    # Per-case comparison records remain in the full benchmark supplement.
    comparison["raw_comparison"].pop("case_comparisons")
    for value in comparison["timing"]["actual_timing_paired_comparison"].values():
        value.pop("paired_base_results")
    reported = {
        "source_sha256": hashes,
        "heldout_status_counts": dict(statuses),
        "family_method_table": summary["family_method_table"],
        "base_failure_families": bases["families"],
        "timing": comparison["timing"],
        "raw_comparison": comparison["raw_comparison"],
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (
        ("figure_data.json", plot),
        ("certificate_example.json", fixture),
        ("reported_results.json", reported),
    ):
        (output / name).write_text(
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
    print(
        json.dumps(
            {
                "heldout_cases": len(cases),
                "timing_rows": len(timing_cases),
                "outputs_sha256": {p.name: digest(p) for p in sorted(output.glob("*.json"))},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    extract(args.study_root, args.output_dir)
