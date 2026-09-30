"""Curating the worksite / truck-plate vocabulary (core/known_values.py).

`KnownValueError` carries one of these straight to the browser, so each says
what the user did wrong rather than which internal check caught it.
"""

MESSAGES = {
    "known_values.invalid_kind": "Invalid type",
    "known_values.empty_value": "Empty value",
    "known_values.duplicate": "This value already exists.",
    "known_values.not_found": "Value not found",
    "known_values.merge_into_itself": "Cannot merge a value with itself",
    "known_values.kind_mismatch": "Both values must be of the same type",
    "known_values.target_merged": "The target value has already been merged elsewhere",
}
