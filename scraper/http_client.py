"""Shared HTTP session for all scrapers.

`requests.get(...)` opens and tears down a brand-new connection (full TCP +
TLS handshake) on every call. At the volume the scrapers operate at
(thousands of detail-page requests per run) that stops being free: every
closed connection lingers in TIME_WAIT, and deep into a long scrape the OS
has to search a shrinking pool of free local ports for each new connection,
so requests get progressively slower the longer the scrape runs.

A shared Session with a connection-pooling HTTPAdapter reuses keep-alive
connections per host instead, so request latency stays flat regardless of
how deep into the scrape we are.

The adapter also retries transient failures (dropped connections, 429/5xx
throttling responses) with exponential backoff. Without this a single
momentary hiccup can make a scraper silently return zero results for a whole
site.
"""

import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Sized for the whole run: all four sites can scrape concurrently, each with
# its own pool of detail workers, so the pool must comfortably exceed
# (number of sites) x (detail workers per site) across distinct hosts.
_POOL_MAXSIZE = int(os.getenv("SCRAPER_POOL_MAXSIZE", "64"))
_POOL_CONNECTIONS = int(os.getenv("SCRAPER_POOL_CONNECTIONS", "20"))

_retry = Retry(
    total=3,
    connect=3,          # retry connection-level failures (instant RST / unreachable)
    read=3,
    backoff_factor=0.5,  # 0s, 0.5s, 1s, 2s between attempts
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET", "HEAD"]),
    respect_retry_after_header=True,
)

_session = requests.Session()
_adapter = HTTPAdapter(
    pool_connections=_POOL_CONNECTIONS,
    pool_maxsize=_POOL_MAXSIZE,
    max_retries=_retry,
)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


def get_session():
    """Return the shared, thread-safe requests.Session used by all scrapers."""
    return _session
