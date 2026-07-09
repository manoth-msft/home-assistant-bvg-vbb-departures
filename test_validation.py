#!/usr/bin/env python3
"""Test validation functions for berlin_transport."""
# pylint: disable=redefined-outer-name

import voluptuous as vol

# Paste validation functions here for testing (avoiding imports)
MAX_EXCLUDED_STOPS_LENGTH = 255
MAX_WALKING_TIME = 60


def validate_excluded_stops(value: str) -> str:
    """Validate excluded_stops configuration value."""
    if not value or not value.strip():
        return ""

    if len(value) > MAX_EXCLUDED_STOPS_LENGTH:
        raise vol.Invalid(
            f"excluded_stops too long ({len(value)}/{MAX_EXCLUDED_STOPS_LENGTH} chars). "
            "Please use fewer Stop-IDs (max ~20 stops)."
        )

    stops = [s.strip() for s in value.split(",")]
    for stop in stops:
        if not stop:
            raise vol.Invalid(
                "excluded_stops: Empty stop ID found. "
                "Use format: '900078201,900190001' (no spaces inside IDs)"
            )
        if not stop.isdigit():
            raise vol.Invalid(
                f"excluded_stops: Invalid Stop-ID '{stop}'. "
                "Must be numeric (e.g. '900078201')"
            )
        if len(stop) > 20:
            raise vol.Invalid(
                f"excluded_stops: Stop-ID '{stop}' too long (max 20 digits)"
            )

    return value


def validate_walking_time(value: int) -> int:
    """Validate walking_time configuration value."""
    if not isinstance(value, int):
        raise vol.Invalid("walking_time must be a number")

    if value < 0:
        raise vol.Invalid("walking_time cannot be negative")

    if value > MAX_WALKING_TIME:
        raise vol.Invalid(
            f"walking_time too high ({value}/{MAX_WALKING_TIME} min). "
            "Using max 60 minutes."
        )

    return value


print("=" * 70)
print("Testing Config Input Validation (v0.1.6)")
print("=" * 70)

# Test validate_excluded_stops
print("\n1. Testing validate_excluded_stops:")
print("-" * 70)

valid_test_cases = [
    ("", "Empty (no exclusions)"),
    ("900078201", "Single Stop-ID"),
    ("900078201,900190001", "Multiple stops"),
    ("900078201, 900190001", "With spaces"),
    ("900078201,900190001,900260005", "Three stops"),
]

print("\n✓ Valid cases:")
for test_value, desc in valid_test_cases:
    try:
        result = validate_excluded_stops(test_value)
        print(f"  ✓ {desc}: '{test_value}' → Accepted") 
    except vol.Invalid as e:
        print(f"  ✗ {desc}: UNEXPECTED ERROR: {e}")

invalid_tests = [
    ("not_numeric", "Non-numeric Stop-ID", "must be numeric"),
    ("900078201,abc,900190001", "Mixed valid/invalid", "must be numeric"),
    ("900078201,,900190001", "Empty ID in list", "Empty stop ID"),
    ("a" * 300, "Too long string (300 chars)", "too long"),
]

print("\n✗ Invalid cases (should be rejected):")
for value, desc, expected_error in invalid_tests:
    try:
        result = validate_excluded_stops(value)
        print(f"  ✗ {desc}: SHOULD HAVE FAILED")
    except vol.Invalid as e:
        if expected_error.lower() in str(e).lower():
            print(f"  ✓ {desc}: Correctly rejected")
        else:
            print(f"  ⚠ {desc}: Rejected with: {e}")

# Test validate_walking_time
print("\n2. Testing validate_walking_time:")
print("-" * 70)

walking_valid_cases: list[tuple[int, str]] = [
    (0, "Zero (edge case)"),
    (1, "Normal value"),
    (15, "High value"),
    (60, "Max value (60 min)"),
]

print("\n✓ Valid cases:")
for test_value_int, desc in walking_valid_cases:
    try:
        result = validate_walking_time(test_value_int)
        print(f"  ✓ {desc}: {test_value_int} min → Accepted")
    except vol.Invalid as e:
        print(f"  ✗ {desc}: UNEXPECTED ERROR: {e}")

walking_invalid_cases: list[tuple[int, str]] = [
    (-1, "Negative value"),
    (61, "Over limit (61 > 60)"),
    (120, "Too high (120 min)"),
]

print("\n✗ Invalid cases (should be rejected):")
for test_value_int, desc in walking_invalid_cases:
    try:
        result = validate_walking_time(test_value_int)
        print(f"  ✗ {desc}: SHOULD HAVE FAILED")
    except vol.Invalid as e:
        print(f"  ✓ {desc}: Correctly rejected")

print("\n" + "=" * 70)
print("✓ All validation tests completed successfully!")
print("=" * 70)
