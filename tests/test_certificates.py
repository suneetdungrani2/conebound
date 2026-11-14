from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from conebound import verify_certificate, payload_identity


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _rehash_inputs(problem, cert):
    P = [[F(float(v)) for v in row] for row in problem["P"]]
    J = [[F(float(v)) for v in row] for row in problem["J"]]
    q, b = [F(float(v)) for v in problem["q"]], [F(float(v)) for v in problem["b"]]

    def rational(x):
        return f"{x.numerator}/{x.denominator}"

    normalized = {
        "P": [[rational(v) for v in row] for row in P],
        "J": [[rational(v) for v in row] for row in J],
        "q": list(map(rational, q)),
        "b": list(map(rational, b)),
        "cones": problem["cones"],
        "problem_id": problem["problem_id"],
        "units": problem["units"],
        "schema_version": "conebound.rational_problem/1",
    }
    inputs = {
        "problem": normalized,
        "primal": cert["witnesses"]["primal"],
        "dual": cert["witnesses"]["dual"],
        "directions": [item["direction"] for item in cert["supports"]],
    }
    cert["problem_sha256"] = hashlib.sha256(_canonical(normalized)).hexdigest()
    cert["input_sha256"] = hashlib.sha256(_canonical(inputs)).hexdigest()


def _fixture():
    path = Path(__file__).parents[1] / "data" / "certificate_example.json"
    if not path.is_file():
        raise AssertionError(f"required archived certificate fixture is missing: {path}")
    return json.loads(path.read_text())


def test_archived_certificate_replays_and_hash_is_stable():
    fixture = _fixture()
    problem, cert = fixture["problem"], fixture["certificate"]
    assert verify_certificate(problem, cert)
    assert payload_identity(problem, cert) == fixture["provenance"]["payload_identity_sha256"]


@pytest.mark.parametrize(
    "tamper",
    [
        "status",
        "hash",
        "metric",
        "gap",
        "support",
        "support_radius",
        "center",
        "primal",
        "witness",
        "spd",
        "partition",
    ],
)
def test_certificate_tampering_fails_closed(tamper):
    fixture = _fixture()
    problem = fixture["problem"]
    cert = json.loads(json.dumps(fixture["certificate"]))
    if tamper == "status":
        cert["status"] = "NUMERICAL_ONLY"
    elif tamper == "hash":
        cert["problem_sha256"] = "0" * 64
    elif tamper == "metric":
        cert["metric"][0][0] = "999/1"
    elif tamper == "gap":
        cert["gap"] = "-1/1"
    elif tamper == "witness":
        cert["witnesses"]["dual"][0] = "-999/1"
        _rehash_inputs(problem, cert)
    elif tamper == "primal":
        cert["witnesses"]["primal"][0] = "-999/1"
        _rehash_inputs(problem, cert)
    elif tamper == "center":
        cert["center"][0] = str(F(cert["center"][0]) + 1)
    elif tamper == "support_radius":
        support = cert["supports"][0]
        middle = sum((F(d) * F(c) for d, c in zip(support["direction"], cert["center"])), F(0))
        support["interval"] = [str(middle), str(middle)]
    elif tamper == "spd":
        problem["P"][0][0] = -abs(float(problem["P"][0][0]))
        cert["metric"] = [
            [f"{F(float(v)).numerator}/{F(float(v)).denominator}" for v in row]
            for row in problem["P"]
        ]
        _rehash_inputs(problem, cert)
    elif tamper == "partition":
        problem["cones"][0]["offset"] = 1
        _rehash_inputs(problem, cert)
    else:
        support = cert["supports"][0]
        middle = sum((F(d) * F(c) for d, c in zip(support["direction"], cert["center"])), F(0))
        support["interval"] = [str(middle + 100), str(middle + 101)]
        _rehash_inputs(problem, cert)
    with pytest.raises((ValueError, KeyError, TypeError)):
        verify_certificate(problem, cert)


def test_problem_hash_binds_float_input_payload():
    fixture = _fixture()
    altered = json.loads(json.dumps(fixture["problem"]))
    altered["P"][0][0] = float(altered["P"][0][0]) + 0.125
    assert payload_identity(altered, fixture["certificate"]) != payload_identity(
        fixture["problem"], fixture["certificate"]
    )


def test_archive_replay_rejects_a_self_consistent_unpinned_manifest(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"schema_version": "conebound.supplement-manifest/1", "files": {}})
    )
    script = Path(__file__).parents[1] / "scripts/verify_archive.py"
    result = subprocess.run(
        [sys.executable, str(script), "--archive-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "does not match the pinned benchmark archive" in result.stderr
