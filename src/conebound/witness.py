"""A fixed three-dimensional SOC counterexample and restricted spectral identity."""

from decimal import Decimal, localcontext
from fractions import Fraction
import math


def _exact_positive(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be positive and finite")
    try:
        exact = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"{name} must be positive and finite") from exc
    if exact <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return exact


def verify_scalar_failure(kappa):
    """Verify the scalar-weight contradiction with exact rational arithmetic."""
    k = _exact_positive(kappa, "kappa")
    numerator = 9 * (1 + 4 * k) - (9 + 4 * k)
    if numerator != 32 * k or numerator <= 0:
        raise ValueError("exact scalar inequality does not hold")
    return {
        "kappa": f"{k.numerator}/{k.denominator}",
        "cross_product_difference": f"{numerator.numerator}/{numerator.denominator}",
        "verified": True,
    }


def _decimal_fraction(value):
    return Decimal(value.numerator) / Decimal(value.denominator)


def scalar_witness(kappa=1.0):
    """Return an 80-digit numerical witness for c=(2,1,0), P=I, alpha=1.

    Exact non-representability is checked by verify_scalar_failure. Decimal
    values corroborate the point, derivative and segment miss; they are not proof.
    """
    exact_gate = verify_scalar_failure(kappa)
    with localcontext() as ctx:
        ctx.prec = 80
        k = _decimal_fraction(Fraction(kappa))
        roots = [(Decimal(b * b) + 4 * k).sqrt() for b in (3, 1)]
        t = [2 * k / (r + Decimal(b)) for r, b in zip(roots, (3, 1))]
        dt = [1 / r for r in roots]
        point = [(t[0] + t[1]) / 2, (t[0] - t[1]) / 2, Decimal(0)]
        derivative = [(dt[0] + dt[1]) / 2, (dt[0] - dt[1]) / 2, Decimal(0)]
        dual = [point[0] + 2, point[1] + 1, Decimal(0)]
        weight = sum(a * b for a, b in zip(point, derivative)) / (
            k * sum(v * v for v in derivative)
        )
        weight = max(Decimal(1), min(Decimal(2), weight))
        miss = sum((a - k * weight * b) ** 2 for a, b in zip(point, derivative)).sqrt()
        return {
            "kappa": str(k),
            "exact_gate": exact_gate,
            "point": [str(v) for v in point],
            "derivative": [str(v) for v in derivative],
            "hard_optimizer": ["0", "0", "0"],
            "dual_witness_decimal80": [str(v) for v in dual],
            "exact_dual_feasibility_reason": "the exact point is in the Lorentz cone and (2,1,0) is interior; their sum is in the cone",
            "required_coordinate_weights": [str(point[i] / (k * derivative[i])) for i in (0, 1)],
            "best_segment_weight": str(weight),
            "segment_miss": str(miss),
            "exact_inequality": "9/(9+4*kappa) > 1/(1+4*kappa); cross-product difference is exactly 32*kappa",
            "evidence_kind": "decimal80_corroboration",
        }


def restricted_isotropic_spectrum(c, kappa, alpha=1.0):
    """Evaluate the separated spectral formula for an isotropic fixed cone.

    This algebraic identity applies to the isotropic quadratic-plus-linear
    Lorentz-cone problem only. It is not a generic cone-QP algorithm.
    """
    k_exact, a_exact = _exact_positive(kappa, "kappa"), _exact_positive(alpha, "alpha")
    try:
        k, a = float(k_exact), float(a_exact)
    except OverflowError as exc:
        raise ValueError("floating spectral parameters exceed supported range") from exc
    if not math.isfinite(k) or not math.isfinite(a) or min(k, a) <= 0:
        raise ValueError("floating spectral parameters exceed supported range")
    values = tuple(float(v) for v in c)
    if len(values) < 2 or not all(map(math.isfinite, values)):
        raise ValueError("c must be a finite vector of dimension at least two")
    norm = math.hypot(*values[1:])
    unit = tuple(v / norm for v in values[1:]) if norm else (1.0,) + (0.0,) * (len(values) - 2)
    beta = (values[0] + norm, values[0] - norm)
    roots = tuple(math.hypot(b, 2 * math.sqrt(a * k)) for b in beta)
    if not all(math.isfinite(r) and r > 0 for r in roots):
        raise ValueError("floating spectral roots exceed supported range")
    t = tuple(2 * k / (r + b) if b > 0 else (r - b) / (2 * a) for b, r in zip(beta, roots))
    dt = tuple(1 / r for r in roots)
    hard = tuple(max(-b / a, 0.0) for b in beta)

    def lift(values_):
        head = (values_[0] + values_[1]) / 2
        tail = (values_[0] - values_[1]) / 2
        return (head, *(tail * u for u in unit))

    return {
        "point": lift(t),
        "derivative": lift(dt),
        "hard_optimizer": lift(hard),
        "beta": beta,
        "spectral_weights": tuple(2 * r / (r + abs(b)) for b, r in zip(beta, roots)),
        "arithmetic": "float64 numerical",
        "scope": "isotropic separated Lorentz cone only",
    }
