"""Local JSON persistence for monitor + improve data."""

import json
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path.home() / ".config" / "seo-cli" / "data"


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_data(filename: str) -> dict:
    """Load JSON data from ~/.config/seo-cli/data/{filename}."""
    _ensure_dir()
    path = DATA_DIR / filename
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def save_data(filename: str, data: dict):
    """Save JSON data to ~/.config/seo-cli/data/{filename}."""
    _ensure_dir()
    path = DATA_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def timestamp() -> str:
    """Return current UTC timestamp as ISO string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
