import json
import os
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(os.getenv("SCRAPE_SAMPLE_LOG_DIR", "logs"))
LOG_FILE = LOG_DIR / "scrape_first_rows.json"


def _serialize_row(row: dict) -> dict:
    return {key: value for key, value in row.items()}


def log_scrape_samples(source_samples: list[dict]) -> Path:
    """Append first extracted row per source for this scrape run."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    entries = []
    if LOG_FILE.exists():
        try:
            with LOG_FILE.open(encoding="utf-8") as handle:
                existing = json.load(handle)
            if isinstance(existing, list):
                entries = existing
        except (json.JSONDecodeError, OSError):
            entries = []

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": {},
    }

    for sample in source_samples:
        source = sample["source"]
        first_row = sample.get("first_row")
        entry["sources"][source] = {
            "total_count": sample.get("total_count", 0),
            "first_row": _serialize_row(first_row) if first_row else None,
        }

        if sample.get("error"):
            entry["sources"][source]["error"] = sample["error"]

    entries.append(entry)

    with LOG_FILE.open("w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)

    return LOG_FILE
