"""Independent exact replay of archived rational gap certificates."""

from fractions import Fraction
from functools import lru_cache
from hashlib import sha256
import json

F = Fraction


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _dot(x, y):
    if len(x) != len(y):
        raise ValueError("dimension mismatch")
    return sum((a * b for a, b in zip(x, y)), F(0))


def _determinant(matrix):
    a = [row[:] for row in matrix]
    det = F(1)
    for j in range(len(a)):
        pivot_row = next((i for i in range(j, len(a)) if a[i][j]), None)
        if pivot_row is None:
            return F(0)
        if pivot_row != j:
            a[j], a[pivot_row] = a[pivot_row], a[j]
            det = -det
        pivot = a[j][j]
        det *= pivot
        for i in range(j + 1, len(a)):
            ratio = a[i][j] / pivot
            for k in range(j + 1, len(a)):
                a[i][k] -= ratio * a[j][k]
    return det


def _solve(matrix, rhs):
    n = len(matrix)
    if len(rhs) != n or any(len(row) != n for row in matrix):
        raise ValueError("linear system dimension mismatch")
    a = [row[:] + [v] for row, v in zip(matrix, rhs)]
    for j in range(n):
        pivot = next((i for i in range(j, n) if a[i][j]), None)
        if pivot is None:
            raise ValueError("singular metric")
        a[j], a[pivot] = a[pivot], a[j]
        scale = a[j][j]
        a[j] = [v / scale for v in a[j]]
        for i in range(n):
            if i != j:
                scale = a[i][j]
                a[i] = [x - scale * y for x, y in zip(a[i], a[j])]
    return [row[-1] for row in a]


@lru_cache(maxsize=256)
def _positive_definite(metric):
    matrix = [list(row) for row in metric]
    return matrix == [list(row) for row in zip(*matrix)] and all(
        _determinant([row[:k] for row in matrix[:k]]) > 0 for k in range(1, len(matrix) + 1)
    )


@lru_cache(maxsize=4096)
def _support_quadratic(metric, direction):
    # Cache only exact mathematical inputs, never reported certificate hashes.
    return _dot(direction, _solve([list(row) for row in metric], direction))


def _validate_cones(cones, row_count):
    expected_offset = 0
    for cone in cones:
        offset, dimension = cone["offset"], cone["dimension"]
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or isinstance(dimension, bool)
            or not isinstance(dimension, int)
            or offset != expected_offset
            or dimension < 1
            or offset + dimension > row_count
        ):
            raise ValueError("cones must form an ordered complete row partition")
        kind = cone["kind"]
        if kind == "lorentz" and dimension < 2:
            raise ValueError("Lorentz cone dimension must be at least two")
        if kind not in ("lorentz", "nonnegative"):
            raise ValueError("unknown cone")
        expected_offset += dimension
    if expected_offset != row_count:
        raise ValueError("cones do not cover all constraint rows")


def _cone_feasible(vector, cones):
    for cone in cones:
        offset, dimension = cone["offset"], cone["dimension"]
        part = vector[offset : offset + dimension]
        if cone["kind"] == "lorentz":
            if part[0] < 0 or part[0] ** 2 < sum(v * v for v in part[1:]):
                return False
        elif any(v < 0 for v in part):
            return False
    return True


def _problem_arrays(problem):
    P = [[F(float(v)) for v in row] for row in problem["P"]]
    J = [[F(float(v)) for v in row] for row in problem["J"]]
    q, b = [F(float(v)) for v in problem["q"]], [F(float(v)) for v in problem["b"]]
    n = len(P)
    if (
        not n
        or any(len(row) != n for row in P)
        or len(q) != n
        or len(J) != len(b)
        or any(len(row) != n for row in J)
    ):
        raise ValueError("invalid problem dimensions")
    _validate_cones(problem["cones"], len(b))
    return P, J, q, b


def payload_identity(problem, certificate):
    """Hash the exact problem and complete payload, excluding elapsed time."""
    payload = {
        "problem": problem,
        "certificate": {k: v for k, v in certificate.items() if k != "elapsed_ns"},
    }
    return sha256(_canonical(payload)).hexdigest()


def verify_certificate(problem, certificate):
    """Replay all certificate claims with exact Fractions; raise ValueError on failure.

    Floating problem coefficients are converted to their exact binary-float
    rational values, matching the archived checker contract. Certificate
    numbers must be rational strings. A successful return means replay passed;
    it does not upgrade any source result to VALIDATED.
    """
    if certificate["status"] != "VALIDATED":
        raise ValueError("certificate is not VALIDATED")
    P, J, q, b = _problem_arrays(problem)
    if [[F(v) for v in row] for row in certificate["metric"]] != P:
        raise ValueError("metric mismatch")
    normalized = {
        "P": [[f"{v.numerator}/{v.denominator}" for v in row] for row in P],
        "J": [[f"{v.numerator}/{v.denominator}" for v in row] for row in J],
        "q": [f"{v.numerator}/{v.denominator}" for v in q],
        "b": [f"{v.numerator}/{v.denominator}" for v in b],
        "cones": problem["cones"],
        "problem_id": problem["problem_id"],
        "units": problem["units"],
        "schema_version": "conebound.rational_problem/1",
    }
    if certificate["problem_sha256"] != sha256(_canonical(normalized)).hexdigest():
        raise ValueError("reported problem digest mismatch")
    witnesses = certificate["witnesses"]
    inputs = {
        "problem": normalized,
        "primal": witnesses["primal"],
        "dual": witnesses["dual"],
        "directions": [s["direction"] for s in certificate["supports"]],
    }
    if certificate["input_sha256"] != sha256(_canonical(inputs)).hexdigest():
        raise ValueError("reported input digest mismatch")
    x, y = list(map(F, witnesses["primal"])), list(map(F, witnesses["dual"]))
    if len(x) != len(q) or len(y) != len(b):
        raise ValueError("witness dimension mismatch")
    slack = [_dot(row, x) + v for row, v in zip(J, b)]
    if "slack" in certificate and list(map(F, certificate["slack"])) != slack:
        raise ValueError("stored slack mismatch")
    if not _cone_feasible(slack, problem["cones"]):
        raise ValueError("primal witness infeasible")
    if not _cone_feasible(y, problem["cones"]):
        raise ValueError("dual witness infeasible")
    metric = tuple(tuple(row) for row in P)
    if not _positive_definite(metric):
        raise ValueError("metric not SPD")
    a = [_dot(col, y) - v for col, v in zip(zip(*J), q)]
    center = list(map(F, certificate["center"]))
    if len(center) != len(P) or [_dot(row, center) for row in P] != a:
        raise ValueError("center linear equation mismatch")
    objective = _dot(x, [_dot(row, x) for row in P]) / 2 + _dot(q, x)
    dual_objective = -_dot(a, center) / 2 - _dot(b, y)
    if F(certificate["objective_primal"]) != objective:
        raise ValueError("primal objective mismatch")
    if F(certificate["objective_dual"]) != dual_objective:
        raise ValueError("dual objective mismatch")
    gap = objective - dual_objective
    if gap < 0 or F(certificate["gap"]) != gap:
        raise ValueError("gap mismatch or negative gap")
    if F(certificate["radius_squared"]) != 2 * gap:
        raise ValueError("radius mismatch")
    for support in certificate["supports"]:
        direction = list(map(F, support["direction"]))
        if len(direction) != len(P):
            raise ValueError("support direction dimension mismatch")
        middle = _dot(direction, center)
        lo, hi = map(F, support["interval"])
        radicand = 2 * gap * _support_quadratic(metric, tuple(direction))
        if not lo <= middle <= hi:
            raise ValueError("support midpoint outside interval")
        if (middle - lo) ** 2 < radicand or (hi - middle) ** 2 < radicand:
            raise ValueError("support endpoints do not enclose radius")
    return True
