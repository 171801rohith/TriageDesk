"""Domain exceptions raised by services and mapped to HTTP codes in `app/main.py`.

Keeps HTTP concerns (status codes, `HTTPException`) out of the service layer
(implement_1.md Phase 6, step 5).
"""


class TriageDeskError(Exception):
    """Base class for all domain errors."""


class NotFound(TriageDeskError):
    """Requested entity does not exist → HTTP 404."""


class Conflict(TriageDeskError):
    """Operation not allowed in the entity's current state → HTTP 409 (e.g. FR-18)."""
