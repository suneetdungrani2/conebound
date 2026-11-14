"""Small public scientific core; this package does not implement a general solver."""

from .witness import scalar_witness, verify_scalar_failure, restricted_isotropic_spectrum
from .certificates import verify_certificate, payload_identity

__all__ = [
    "scalar_witness",
    "verify_scalar_failure",
    "restricted_isotropic_spectrum",
    "verify_certificate",
    "payload_identity",
]
