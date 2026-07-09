"""Detailed JSON logging for scrape runs.

One file (logs/scrape_log.json) holds the full log of the *current* scrape
only: starting a new run wipes everything related to previous runs. The file
is rewritten after every state change so it is always up to date, even if the
run is cancelled or crashes midway.
"""

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(os.getenv("SCRAPE_LOG_DIR", "logs"))
LOG_FILE = LOG_DIR / "scrape_log.json"

PHASES = ("rent", "sale", "land")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _blank_stats():
    return {
        "ads_scraped": 0,
        "ads_inserted": 0,
        "ads_already_in_db": 0,
        "errors": 0,
    }


class ScrapeLogger:
    def __init__(self, path=LOG_FILE):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.data = None
        self._run_t0 = None
        self._site_t0 = {}
        self._phase_t0 = {}

    # ------------------------------------------------------------------ run

    def start_run(self, triggered_by):
        with self._lock:
            self._run_t0 = time.time()
            self._site_t0 = {}
            self._phase_t0 = {}
            self.data = {
                "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                "triggered_by": triggered_by,
                "started_at": _now_iso(),
                "finished_at": None,
                "duration_seconds": None,
                "status": "running",
                "websites": {},
                "totals": {
                    **_blank_stats(),
                    "archived": 0,
                    "rolled_back": 0,
                },
            }
            self._flush()

    def end_run(self, status, rolled_back=0):
        with self._lock:
            if self.data is None:
                return
            self.data["status"] = status
            self.data["finished_at"] = _now_iso()
            self.data["duration_seconds"] = round(time.time() - self._run_t0, 2)
            self.data["totals"]["rolled_back"] = rolled_back
            if status == "cancelled":
                # Mark anything still running as cancelled
                for site in self.data["websites"].values():
                    if site["status"] == "running":
                        site["status"] = "cancelled"
                    for phase in site["phases"].values():
                        if phase["status"] == "running":
                            phase["status"] = "cancelled"
            self._flush()

    def set_archived(self, count):
        with self._lock:
            if self.data is None:
                return
            self.data["totals"]["archived"] = count
            self._flush()

    # -------------------------------------------------------------- website

    def start_website(self, site):
        with self._lock:
            if self.data is None:
                return
            self._site_t0[site] = time.time()
            self.data["websites"][site] = {
                "status": "running",
                "started_at": _now_iso(),
                "finished_at": None,
                "duration_seconds": None,
                "phases": {
                    phase: {"status": "pending", **_blank_stats()}
                    for phase in PHASES
                },
                "totals": _blank_stats(),
            }
            self._flush()

    def end_website(self, site, status="completed", error=None):
        with self._lock:
            entry = (self.data or {}).get("websites", {}).get(site)
            if not entry:
                return
            entry["status"] = status
            entry["finished_at"] = _now_iso()
            entry["duration_seconds"] = round(time.time() - self._site_t0.get(site, time.time()), 2)
            if error:
                entry["error"] = str(error)
            self._flush()

    # ---------------------------------------------------------------- phase

    def start_phase(self, site, phase):
        with self._lock:
            entry = (self.data or {}).get("websites", {}).get(site)
            if not entry:
                return
            self._phase_t0[(site, phase)] = time.time()
            entry["phases"][phase] = {
                "status": "running",
                "started_at": _now_iso(),
                "finished_at": None,
                "duration_seconds": None,
                **_blank_stats(),
            }
            self._flush()

    def end_phase(self, site, phase, ads_scraped=0, ads_inserted=0,
                  ads_already_in_db=0, errors=0, status="completed"):
        with self._lock:
            entry = (self.data or {}).get("websites", {}).get(site)
            if not entry:
                return
            phase_entry = entry["phases"].get(phase)
            if not phase_entry:
                return
            phase_entry.update({
                "status": status,
                "finished_at": _now_iso(),
                "duration_seconds": round(
                    time.time() - self._phase_t0.get((site, phase), time.time()), 2
                ),
                "ads_scraped": ads_scraped,
                "ads_inserted": ads_inserted,
                "ads_already_in_db": ads_already_in_db,
                "errors": errors,
            })
            # Roll the phase numbers up into the website + run totals
            for key, value in (
                ("ads_scraped", ads_scraped),
                ("ads_inserted", ads_inserted),
                ("ads_already_in_db", ads_already_in_db),
                ("errors", errors),
            ):
                entry["totals"][key] += value
                self.data["totals"][key] += value
            self._flush()

    # ---------------------------------------------------------------- misc

    def read(self):
        """Return the current log contents (from memory, or disk on restart)."""
        with self._lock:
            if self.data is not None:
                return self.data
        try:
            with self.path.open(encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None

    def _flush(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"WARNING: could not write scrape log {self.path}: {e}")
