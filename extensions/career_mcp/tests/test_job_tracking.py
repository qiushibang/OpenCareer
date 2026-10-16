import pytest

from extensions.career_mcp.domain.job_tracking import (
    TrackingValidationError,
    normalize_tracking_patch,
)


def test_normalize_tracking_patch_accepts_supported_fields():
    assert normalize_tracking_patch(
        {
            "expected_version": 0,
            "is_favorite": True,
            "application_status": "preparing",
            "note": "  本周完成材料  ",
        }
    ) == {
        "expected_version": 0,
        "is_favorite": True,
        "application_status": "preparing",
        "note": "本周完成材料",
    }


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"expected_version": -1, "is_favorite": True}, "INVALID_INPUT"),
        ({"expected_version": 0}, "INVALID_INPUT"),
        (
            {"expected_version": 0, "application_status": "unknown"},
            "INVALID_STATUS",
        ),
        ({"expected_version": 0, "is_favorite": 1}, "INVALID_INPUT"),
        (
            {"expected_version": 0, "note": "x" * 2001},
            "INVALID_INPUT",
        ),
    ],
)
def test_normalize_tracking_patch_rejects_invalid_values(patch, code):
    with pytest.raises(TrackingValidationError) as error:
        normalize_tracking_patch(patch)

    assert error.value.code == code
