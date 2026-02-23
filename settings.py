"""
Persistent settings manager — reads/writes a JSON file that survives
Docker container restarts when /app/data is mounted as a volume.
"""

import json
import os
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path(os.getenv("SETTINGS_PATH", "/app/data/settings.json"))

_DEFAULTS: dict[str, Any] = {
    "timezone": "America/New_York",
    "gemini_api_key": "",
}


def _ensure_file() -> None:
    """Create the settings file with defaults if it doesn't exist."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        SETTINGS_PATH.write_text(json.dumps(_DEFAULTS, indent=2))


def load_settings() -> dict[str, Any]:
    """Return the full settings dict, back-filling any missing keys."""
    _ensure_file()
    try:
        data = json.loads(SETTINGS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        data = {}
    # Back-fill any missing keys from defaults
    for key, default in _DEFAULTS.items():
        data.setdefault(key, default)
    return data


def save_settings(data: dict[str, Any]) -> None:
    """Persist the settings dict to disk."""
    _ensure_file()
    SETTINGS_PATH.write_text(json.dumps(data, indent=2))


def get(key: str) -> Any:
    """Get a single setting value."""
    return load_settings().get(key, _DEFAULTS.get(key))
