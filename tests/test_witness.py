from decimal import Decimal, localcontext
from fractions import Fraction
import math

import pytest
from conebound import scalar_witness, restricted_isotropic_spectrum, verify_scalar_failure


@pytest.mark.parametrize(
    "kappa", [Fraction(1, 10**12), Fraction(1, 3), Fraction(1), Fraction(10**12)]
)
def test_exact_scalar_failure_and_decimal_kkt(kappa):
    gate = verify_scalar_failure(kappa)
    assert Fraction(gate["cross_product_difference"]) == 9 * (1 + 4 * kappa) - (9 + 4 * kappa)
    assert Fraction(9) / (9 + 4 * kappa) > Fraction(1) / (1 + 4 * kappa)
    result = scalar_witness(kappa)
    with localcontext() as context:
        context.prec = 80
        k = Decimal(kappa.numerator) / Decimal(kappa.denominator)
        x = list(map(Decimal, result["point"]))
        y = list(map(Decimal, result["dual_witness_decimal80"]))
        assert abs(x[0] * y[0] + x[1] * y[1] - k) < Decimal("1e-60") * max(1, k)
        assert abs(x[0] * y[1] + x[1] * y[0]) < Decimal("1e-60") * max(1, k)
        assert x[0] > abs(x[1]) and y[0] > abs(y[1])
        assert Decimal(result["segment_miss"]) > 0


def test_recorded_witness_miss_and_exact_gate_below_decimal_resolution():
    miss = Decimal(scalar_witness(1)["segment_miss"])
    assert Decimal("0.0483821540743") < miss < Decimal("0.0483821540744")
    assert verify_scalar_failure(Fraction(1, 10**120))["verified"]


def test_six_coordinate_source_substitution():
    with localcontext() as context:
        context.prec = 80
        r = list(map(Decimal, scalar_witness(1)["point"]))
        c = list(map(Decimal, (2, 1, 0)))
        x = [-v / 2 for v in r] + [v / 2 for v in r]
        q = [-v for v in c] + c
        dual = [a + b for a, b in zip(c, r)]
        jt_dual = [-v for v in dual] + dual
        assert max(abs(2 * a + b - d) for a, b, d in zip(x, q, jt_dual)) < Decimal("1e-75")
        recovered = [x[j + 3] - x[j] for j in range(3)]
        assert recovered == r
        objective = sum(v * v for v in x) + sum(a * b for a, b in zip(q, x))
        reduced = sum(v * v for v in r) / 2 + sum(a * b for a, b in zip(c, r))
        assert abs(objective - reduced) < Decimal("1e-75")
        # J[-I,I] times (2I)^-1 times J^T, evaluated independently.
        J = [[-int(i == j) for j in range(3)] + [int(i == j) for j in range(3)] for i in range(3)]
        assert [[sum(Fraction(a * b, 2) for a, b in zip(u, v)) for v in J] for u in J] == [
            [int(i == j) for j in range(3)] for i in range(3)
        ]


def projection_lorentz(v):
    norm = math.hypot(*v[1:])
    if norm <= v[0]:
        return tuple(v)
    if norm <= -v[0]:
        return (0.0,) * len(v)
    head = (norm + v[0]) / 2
    return (head, *(head * x / norm for x in v[1:]))


@pytest.mark.parametrize("c", [(2, 1, 0), (2, 0, 0), (-2, 1, 0), (0, 0, 0), (1, 1, 0)])
@pytest.mark.parametrize("alpha", [0.5, 2.0])
def test_restricted_spectral_identity_against_direct_projection(c, alpha):
    k = 0.7
    result = restricted_isotropic_spectrum(c, k, alpha)
    expected = projection_lorentz(tuple(-v / alpha for v in c))
    assert result["hard_optimizer"] == pytest.approx(expected, abs=1e-14)
    norm = math.hypot(*c[1:])
    u = tuple(v / norm for v in c[1:]) if norm else (1, 0)
    coefficients = []
    for beta, weight in zip(result["beta"], result["spectral_weights"]):
        assert 1 <= weight <= 2
        coefficients.append(k * weight / math.hypot(beta, 2 * math.sqrt(alpha * k)))
    correction = (
        (coefficients[0] + coefficients[1]) / 2,
        *(((coefficients[0] - coefficients[1]) / 2) * v for v in u),
    )
    assert tuple(a - b for a, b in zip(result["point"], correction)) == pytest.approx(
        expected, abs=1e-14
    )


def test_derivative_matches_finite_difference_with_negative_beta():
    k, h = 0.8, 1e-6
    c = (-1, 0, 0)
    at = restricted_isotropic_spectrum(c, k)
    before = restricted_isotropic_spectrum(c, k - h)["point"]
    after = restricted_isotropic_spectrum(c, k + h)["point"]
    assert at["derivative"][0] == pytest.approx((after[0] - before[0]) / (2 * h), rel=1e-7)


@pytest.mark.parametrize("kappa", [0, -1, float("inf"), float("nan"), True])
def test_invalid_kappa(kappa):
    with pytest.raises(ValueError):
        scalar_witness(kappa)
