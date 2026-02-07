from copy import deepcopy
from decimal import Decimal


def normalize_preferences(preferences):
    """Normalize preference payload for deterministic filtering and persistence."""
    normalized = deepcopy(preferences)
    location = normalized.get('location')
    if isinstance(location, str):
        normalized['location'] = location.strip().lower()

    if not normalized.get('stipend_currency'):
        normalized['stipend_currency'] = 'INR'

    return normalized


def to_json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_json_safe(v) for v in value]
    return value
