"""Pure validation for user-owned job tracking state."""

from __future__ import annotations

APPLICATION_STATUSES = (
    "not_started",
    "preparing",
    "applied",
    "assessment",
    "interviewing",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
)
APPLIED_STATUSES = frozenset(APPLICATION_STATUSES[2:])
_MUTABLE_FIELDS = ("is_favorite", "application_status", "note")


class TrackingValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_tracking_patch(patch: object) -> dict:
    if not isinstance(patch, dict):
        raise TrackingValidationError(
            "INVALID_INPUT",
            "patch must be an object",
        )
    version = patch.get("expected_version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < 0
    ):
        raise TrackingValidationError(
            "INVALID_INPUT",
            "expected_version must be a non-negative integer",
        )
    if not any(field in patch for field in _MUTABLE_FIELDS):
        raise TrackingValidationError(
            "INVALID_INPUT",
            "at least one tracking field is required",
        )

    result: dict = {"expected_version": version}
    if "is_favorite" in patch:
        favorite = patch["is_favorite"]
        if not isinstance(favorite, bool):
            raise TrackingValidationError(
                "INVALID_INPUT",
                "is_favorite must be a boolean",
            )
        result["is_favorite"] = favorite
    if "application_status" in patch:
        status = patch["application_status"]
        if status not in APPLICATION_STATUSES:
            raise TrackingValidationError(
                "INVALID_STATUS",
                "unsupported application status",
            )
        result["application_status"] = status
    if "note" in patch:
        note = patch["note"]
        if not isinstance(note, str) or len(note.strip()) > 2000:
            raise TrackingValidationError(
                "INVALID_INPUT",
                "note must contain at most 2000 characters",
            )
        result["note"] = note.strip() or None
    return result
