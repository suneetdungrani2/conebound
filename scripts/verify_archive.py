"""Verify the supplement inventory and replay embedded VALIDATED gap outputs."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from conebound import payload_identity, verify_certificate


def digest(path):
    value = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("archive_verification.json"))
    args = parser.parse_args()
    archive_root = args.archive_root.resolve()
    manifest_path = archive_root / "manifest.json"
    pin_path = Path(__file__).resolve().parents[1] / "data/benchmark_archive.json"
    pin = json.loads(pin_path.read_text())
    manifest_bytes = manifest_path.read_bytes()
    manifest_digest = sha256(manifest_bytes).hexdigest()
    if manifest_digest != pin["manifest_sha256"]:
        raise ValueError("supplement manifest does not match the pinned benchmark archive")
    manifest = json.loads(manifest_bytes)
    if manifest["schema_version"] != "conebound.supplement-manifest/1":
        raise ValueError("unsupported supplement manifest")
    expected_files = set(manifest["files"]) | {"manifest.json"}
    actual_files = {
        str(p.relative_to(archive_root)) for p in archive_root.rglob("*") if p.is_file()
    }
    if actual_files != expected_files:
        raise ValueError("supplement inventory differs from manifest")
    for name, entry in manifest["files"].items():
        path = (archive_root / name).resolve()
        if (
            not path.is_relative_to(archive_root)
            or not path.is_file()
            or path.stat().st_size != entry["size_bytes"]
            or digest(path) != entry["sha256"]
        ):
            raise ValueError(f"supplement member mismatch: {name}")
    reports = {}
    for cohort in ("original", "corrected"):
        root = archive_root / "cohorts" / cohort
        bank = {}
        for path in sorted((root / "data").glob("*.jsonl")):
            for line in path.open():
                item = json.loads(line)
                if "problem" in item:
                    problem = item["problem"]
                    pid = problem["problem_id"]
                    if pid in bank and bank[pid] != problem:
                        raise ValueError(f"conflicting problem payload: {pid}")
                    bank[pid] = problem
        attempted, seen, sources, statuses = 0, set(), {}, Counter()
        for path in sorted((root / "results").rglob("*.jsonl")):
            # Raw and timing rows contain methods; index/failure logs do not.
            if "raw" not in path.name and path.name != "timing.jsonl":
                continue
            sources[str(path.relative_to(root))] = digest(path)
            for line_number, line in enumerate(path.open(), 1):
                row = json.loads(line)
                for result in row.get("methods", {}).values():
                    statuses[result.get("status", "missing")] += 1
                    cert = result.get("certificate", {})
                    if result.get("status") == "VALIDATED" and cert.get("status") != "VALIDATED":
                        raise ValueError(
                            f"VALIDATED result without a certificate: {path}:{line_number}"
                        )
                    if cert.get("status") != "VALIDATED":
                        continue
                    attempted += 1
                    problem = bank[row["problem_id"]]
                    key = payload_identity(problem, cert)
                    if key not in seen:
                        try:
                            verify_certificate(problem, cert)
                        except (ValueError, KeyError, TypeError) as exc:
                            raise ValueError(
                                f"{cohort}/{path.relative_to(root)}:{line_number}: {exc}"
                            ) from exc
                        seen.add(key)
        if not attempted:
            raise ValueError(f"no validated certificates found for {cohort}")
        reports[cohort] = {
            "certificate_outputs": attempted,
            "distinct_payloads": len(seen),
            "method_statuses": dict(statuses),
            "input_files_sha256": sources,
        }
        print(json.dumps({cohort: reports[cohort]}), flush=True)
    args.output.write_text(
        json.dumps(
            {
                "status": "VERIFIED",
                "manifest_sha256": manifest_digest,
                "inventory_files": len(manifest["files"]),
                "cohorts": reports,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
