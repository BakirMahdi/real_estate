from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from .scrapers import tayara as tayara_scraper
from .scrapers import mubawab as mubawab_scraper
from .scrapers import expat as expat_scraper
from .insert import bulk_insert_properties, bulk_get_latest_properties, is_same_property, delete_properties_by_ids, get_active_ad_ids
from .queries import get_properties, get_property_by_id, get_all_properties, search_properties_by_id, search_properties_admin, archive_property, unarchive_property
from .db import get_conn
from .cancellation import ScrapeCancelled
from .scrape_log import ScrapeLogger
from .auth import create_user, authenticate_user, create_access_token, verify_token, verify_token as verify_jwt_token, is_admin
from pydantic import BaseModel
import asyncio
import gc
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

# On Windows networks with custom root CAs, this lets requests trust the OS store.
try:
    import certifi_win32  # type: ignore # noqa: F401
except Exception:
    pass

app = FastAPI(title="Real Estate API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
security = HTTPBearer()

class UserRegister(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Protect /scrape and /scrape/status (but not /properties/...)
        if request.url.path.startswith("/scrape"):
            # Exclude OPTIONS for CORS preflight
            if request.method != "OPTIONS":
                # Check for JWT token first, fall back to API key for backward compatibility
                auth_header = request.headers.get("authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]
                    payload = verify_token(token)
                    if payload:
                        return await call_next(request)

                # sendBeacon (used to auto-cancel on page close) cannot set
                # headers, so also accept the JWT as a query parameter.
                query_token = request.query_params.get("token")
                if query_token and verify_token(query_token):
                    return await call_next(request)

                # Fall back to API key
                api_key = request.headers.get("x-api-key")
                if api_key != ADMIN_PASSWORD:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Unauthorized: Invalid or missing token/API key"}
                    )
        return await call_next(request)

app.add_middleware(AuthMiddleware)

@app.get("/")
def home():
    return {"status": "API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        return {"status": "ok", "database": "reachable"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database unavailable: {e}")


next_scrape_time = ((time.time() // 3600) + 1) * 3600

# Websites are scraped sequentially; within each website the phases run in
# this order, and each phase is flushed to the DB before the next one starts.
SCRAPE_PHASES = ("rent", "sale", "land")

SCRAPER_SOURCES = (
    ("tayara", tayara_scraper.iter_scrape_phases),
    ("mubawab", mubawab_scraper.iter_scrape_phases),
    ("expat", expat_scraper.iter_scrape_phases),
)

scrape_cancel_event = threading.Event()
scrape_logger = ScrapeLogger()


def _blank_phase_stats():
    return {"status": "pending", "count": 0, "inserted": 0, "skipped": 0, "errors": 0}


def _blank_progress():
    return {
        "total_sources": len(SCRAPER_SOURCES),
        "completed_sources": 0,
        "sources": {
            name: {
                "status": "pending",
                "phase": None,
                "step": None,
                "pages_processed": 0,
                "total_pages": 0,
                "items_found": 0,
                "phases": {phase: _blank_phase_stats() for phase in SCRAPE_PHASES},
            }
            for name, _ in SCRAPER_SOURCES
        },
    }


scrape_status_state = {
    "is_scraping": False,
    "cancel_requested": False,
    "cancelled": False,
    "triggered_by": None,
    "results": None,
    "error": None,
    "progress": _blank_progress(),
}

async def weekly_scheduler():
    global next_scrape_time
    while True:
        now = datetime.now()
        # Calculate next Monday at 00:00
        days_until_monday = (0 - now.weekday()) % 7  # 0 = Monday
        if days_until_monday == 0:
            # If today is Monday, check if it's already past 00:00
            if now.hour >= 0:
                days_until_monday = 7  # Next Monday
        
        next_monday = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_until_monday)
        next_scrape_time = next_monday.timestamp()
        delay = (next_scrape_time - now.timestamp())
        
        if delay <= 0:
            delay = 7 * 24 * 3600  # 7 days in seconds
        
        print(f"[Scheduler] Next auto-scrape scheduled for Monday at 00:00: {next_monday.isoformat()} (in {delay:.2f} seconds)")
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            break
            
        if not scrape_status_state["is_scraping"]:
            print(f"[Scheduler] Starting automatic weekly scrape at {datetime.now().isoformat()}...")
            asyncio.create_task(asyncio.to_thread(_run_scrape_task, "auto"))
        else:
            print(f"[Scheduler] Automatic weekly scrape skipped because a scrape is already running.")
            
        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(weekly_scheduler())

def archive_missing_ads(found_ad_ids, completed_sources):
    """Archive ads in the DB that a *successful* scrape of their source didn't find.

    Only ads whose source completed without error are considered. This prevents
    a site that failed or was skipped this run (e.g. a transient block) from
    having all of its existing ads wrongly archived just because we didn't see
    them this time.
    """
    if not completed_sources:
        return {}

    try:
        conn = get_conn()
        cur = conn.cursor()

        # Get all non-archived ad_ids from DB
        cur.execute("SELECT source, ad_id FROM properties WHERE archived = FALSE")
        all_db_ads = {(row[0], row[1]) for row in cur.fetchall()}

        # Find ads that should be archived (in DB but not in current scrape),
        # restricted to sources that completed successfully this run.
        to_archive = []
        for source, ad_id in all_db_ads:
            if source not in completed_sources:
                continue
            if (source, ad_id) not in found_ad_ids:
                to_archive.append((source, ad_id))

        # Archive them
        if to_archive:
            for source, ad_id in to_archive:
                cur.execute(
                    "UPDATE properties SET archived = TRUE WHERE source = %s AND ad_id = %s",
                    (source, ad_id)
                )
            conn.commit()

        cur.close()
        conn.close()

        # Count archived per source so each source's row shows its own total
        counts = {}
        for source, _ad_id in to_archive:
            counts[source] = counts.get(source, 0) + 1
        return counts
    except Exception as e:
        print(f"Error archiving ads: {e}")
        return {}


try:
    import ctypes
    _libc = ctypes.CDLL("libc.so.6")
except Exception:
    _libc = None


def _reclaim_memory():
    """Force freed memory back to the OS after a phase.

    gc.collect() drops unreachable objects, and malloc_trim returns the freed
    heap arenas to the OS (glibc holds onto them by default). Without this the
    process RSS creeps upward across a long multi-phase scrape even though the
    logical memory has been released.
    """
    gc.collect()
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass


def _process_phase_items(source_name, data):
    """Deduplicate one phase's scraped items against the DB and insert the new ones.

    Returns per-phase stats, the inserted row ids (kept so a cancelled scrape
    can be rolled back), and the set of (source, ad_id) seen in this phase (used
    for archiving). No shared state is mutated, so this is safe to run for
    several websites in parallel.

    Items flagged "_known" were recognised (by ad_id) as already in the DB and
    deliberately not re-downloaded, so they count as already-in-db and are only
    recorded as "found" (so they are not archived) — never re-inserted.
    """
    source_tag = next((item["source"] for item in data if item.get("source")), source_name)

    found = set()
    skipped = 0
    to_consider = []
    for item in data:
        ad_id = item.get("ad_id")
        if not ad_id:
            continue
        if item.get("_known"):
            found.add((source_tag, ad_id))
            skipped += 1
        else:
            to_consider.append(item)

    # Bulk latest properties retrieval for the freshly-downloaded items only
    all_ad_ids = [item["ad_id"] for item in to_consider]
    latest_properties = bulk_get_latest_properties(source_tag, all_ad_ids)

    # Insert if new or if values changed (versioning)
    new_items = []
    for item in to_consider:
        found.add((source_tag, item["ad_id"]))
        latest_db = latest_properties.get(item["ad_id"])
        if latest_db is not None and is_same_property(item, latest_db):
            skipped += 1
        else:
            new_items.append(item)

    no_id_errors = sum(1 for item in data if not item.get("ad_id"))

    inserted, insert_errors, inserted_ids = bulk_insert_properties(new_items)

    return {
        "count": len(data),
        "inserted": inserted,
        "skipped": skipped,
        "errors": no_id_errors + insert_errors,
    }, inserted_ids, found


def _run_site(source_name, iter_phases):
    """Scrape one website through all its phases, flushing each phase to the DB.

    Returns (result_row_or_None, inserted_row_ids, found_ad_ids). Designed to be
    run in its own thread so all four websites scrape concurrently: it only
    writes to its own progress entry and to the internally-locked logger.
    """
    src_progress = scrape_status_state["progress"]["sources"][source_name]
    src_progress["status"] = "running"
    scrape_logger.start_website(source_name)

    # Ads we already have: their detail pages are skipped, not re-downloaded.
    # Set SCRAPER_REFRESH_ALL=1 to re-download everything (catches price/detail
    # changes on existing ads, at the cost of a much slower run).
    if os.getenv("SCRAPER_REFRESH_ALL", "0") == "1":
        known_ad_ids = set()
    else:
        try:
            known_ad_ids = get_active_ad_ids(source_name)
        except Exception as e:
            print(f"WARNING: could not load known ad_ids for {source_name}: {e}")
            known_ad_ids = set()

    inserted_ids = []
    found = set()
    site_totals = {"count": 0, "inserted": 0, "skipped": 0, "errors": 0}
    site_error = None
    cancelled = False
    current_phase = {"name": None}

    def progress_callback(phase, step, done, total, items_found,
                          _sp=src_progress, _site=source_name, _cur=current_phase):
        if phase != _cur["name"]:
            _cur["name"] = phase
            scrape_logger.start_phase(_site, phase)
            _sp["phases"][phase]["status"] = "running"
        _sp.update({
            "phase": phase,
            "step": step,
            "pages_processed": done,
            "total_pages": total,
            "items_found": items_found,
        })

    try:
        for phase, items in iter_phases(progress_callback=progress_callback,
                                        cancel_event=scrape_cancel_event,
                                        known_ad_ids=known_ad_ids):
            # The generator may not have reported progress for an empty phase;
            # make sure the log still opens it before we close it.
            if current_phase["name"] != phase:
                current_phase["name"] = phase
                scrape_logger.start_phase(source_name, phase)

            src_progress["step"] = "inserting"
            stats, phase_inserted_ids, phase_found = _process_phase_items(source_name, items)
            inserted_ids.extend(phase_inserted_ids)
            found |= phase_found

            scrape_logger.end_phase(
                source_name, phase,
                ads_scraped=stats["count"],
                ads_inserted=stats["inserted"],
                ads_already_in_db=stats["skipped"],
                errors=stats["errors"],
            )
            src_progress["phases"][phase] = {"status": "completed", **stats}
            for key in site_totals:
                site_totals[key] += stats[key]

            # Free this phase's data (and return it to the OS) before the next
            items.clear()
            del items
            _reclaim_memory()

            if scrape_cancel_event.is_set():
                raise ScrapeCancelled()

        src_progress["status"] = "completed"
        scrape_logger.end_website(source_name, "completed")
    except ScrapeCancelled:
        cancelled = True
        src_progress["status"] = "cancelled"
        scrape_logger.end_website(source_name, "cancelled")
    except Exception as e:
        site_error = str(e)
        src_progress["status"] = "error"
        scrape_logger.end_website(source_name, "error", error=site_error)

    if site_error:
        result = {"source": source_name, "error": site_error}
    elif cancelled:
        result = None  # partial numbers get rolled back, so don't report them
    else:
        result = {
            "source": source_name,
            **site_totals,
            "archived": 0,
            "phases": {phase: dict(src_progress["phases"][phase]) for phase in SCRAPE_PHASES},
            "message": (
                "skipped = annonces déjà présentes en base (doublons source+ad_id)"
                if site_totals["skipped"]
                else None
            ),
        }

    return result, inserted_ids, found


def _run_scrape_task(triggered_by="manual"):
    # All row ids inserted during this run, so a cancel can undo everything
    inserted_row_ids = []

    try:
        scrape_cancel_event.clear()
        scrape_status_state.update({
            "is_scraping": True,
            "cancel_requested": False,
            "cancelled": False,
            "triggered_by": triggered_by,
            "results": None,
            "error": None,
            "progress": _blank_progress(),
        })
        scrape_logger.start_run(triggered_by)

        results = []
        found_ad_ids = set()  # (source, ad_id) found in this scrape, for archiving

        try:
            # Scrape websites concurrently, but only a couple at a time. They
            # hit different domains (no shared rate limit), so running 2 in
            # parallel roughly halves wall time vs. fully sequential, while
            # keeping the number of HTML documents being parsed at once — the
            # dominant memory cost — low enough not to exhaust RAM and crash.
            # Raise SCRAPER_SITE_CONCURRENCY if the host has memory to spare.
            site_concurrency = int(os.getenv("SCRAPER_SITE_CONCURRENCY", "2"))
            completed_lock = threading.Lock()

            def run_and_count(name, fn):
                try:
                    return _run_site(name, fn)
                finally:
                    with completed_lock:
                        scrape_status_state["progress"]["completed_sources"] += 1

            with ThreadPoolExecutor(max_workers=max(1, site_concurrency)) as site_executor:
                futures = [
                    site_executor.submit(run_and_count, source_name, iter_phases)
                    for source_name, iter_phases in SCRAPER_SOURCES
                ]
                for future in as_completed(futures):
                    result, site_inserted_ids, site_found = future.result()
                    inserted_row_ids.extend(site_inserted_ids)
                    found_ad_ids |= site_found
                    if result is not None:
                        results.append(result)

            # Sites finish in nondeterministic order; present them in a stable
            # order so the results table doesn't jump around between runs.
            source_order = {name: i for i, (name, _) in enumerate(SCRAPER_SOURCES)}
            results.sort(key=lambda r: source_order.get(r["source"], len(source_order)))

            if scrape_cancel_event.is_set():
                raise ScrapeCancelled()

            # Archive ads that were not found in this scrape, but only for
            # sources that finished successfully (a site that errored or was
            # skipped must not have its existing ads archived).
            completed_sources = {
                r["source"] for r in results if "error" not in r and r["source"] != "archiving"
            }
            archived_by_source = archive_missing_ads(found_ad_ids, completed_sources)
            total_archived = sum(archived_by_source.values())
            scrape_logger.set_archived(total_archived)

            # Attribute each source's archived count to its own results row
            for r in results:
                if r.get("source") in archived_by_source:
                    r["archived"] = archived_by_source[r["source"]]

            # Grand-total summary row: aggregate every source's stats so the
            # table ends with a single "Total" line across all websites.
            source_rows = [r for r in results if "error" not in r]
            if source_rows:
                results.append({
                    "source": "total",
                    "count": sum(r.get("count", 0) for r in source_rows),
                    "inserted": sum(r.get("inserted", 0) for r in source_rows),
                    "skipped": sum(r.get("skipped", 0) for r in source_rows),
                    "errors": sum(r.get("errors", 0) for r in source_rows),
                    "archived": total_archived,
                })

            scrape_logger.end_run("completed")
            scrape_status_state["results"] = results

        except ScrapeCancelled:
            # Undo every DB modification made during this run
            deleted = 0
            try:
                deleted = delete_properties_by_ids(inserted_row_ids)
            except Exception as e:
                print(f"ERROR rolling back cancelled scrape: {e}")
            scrape_logger.end_run("cancelled", rolled_back=deleted)
            scrape_status_state["cancelled"] = True
            print(f"[Scrape] Cancelled: rolled back {deleted} inserted rows.")

    except Exception as e:
        scrape_status_state["error"] = str(e)
        try:
            scrape_logger.end_run("error")
        except Exception:
            pass
    finally:
        scrape_status_state["is_scraping"] = False
        scrape_status_state["cancel_requested"] = False
        scrape_cancel_event.clear()


@app.post("/scrape")
def start_scrape(background_tasks: BackgroundTasks):
    if scrape_status_state["is_scraping"]:
        return {"status": "already_running"}

    background_tasks.add_task(_run_scrape_task, "manual")
    return {"status": "started"}


@app.post("/scrape/cancel")
def cancel_scrape():
    """Cancel the running scrape; all its DB modifications are rolled back."""
    if not scrape_status_state["is_scraping"]:
        return {"status": "not_running"}

    scrape_status_state["cancel_requested"] = True
    scrape_cancel_event.set()
    return {"status": "cancelling"}


@app.post("/scrape/cancel-beacon")
def cancel_scrape_beacon():
    """Auto-cancel endpoint hit by navigator.sendBeacon when the dashboard page
    is refreshed or closed. Only cancels manually started scrapes so the weekly
    automatic scrape keeps running unattended."""
    if scrape_status_state["is_scraping"] and scrape_status_state["triggered_by"] == "manual":
        scrape_status_state["cancel_requested"] = True
        scrape_cancel_event.set()
        return {"status": "cancelling"}
    return {"status": "ignored"}


@app.get("/scrape/status")
def get_scrape_status():
    return {
        **scrape_status_state,
        "next_scrape_time": next_scrape_time
    }


@app.get("/scrape/log")
def get_scrape_log():
    """Return the detailed JSON log of the current/most recent scrape."""
    data = scrape_logger.read()
    return data if data is not None else {"status": "no_scrape_yet"}


@app.get("/properties/all")
def list_all_properties(include_archived: bool = Query(default=False)):
    properties = get_all_properties(include_archived=include_archived)
    return {"count": len(properties), "items": properties}


@app.get("/properties/search")
def search_properties(
    city: str | None = Query(default=None),
    property_type: str | None = Query(default=None),
    listing_type: str | None = Query(default=None),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    min_area: int | None = Query(default=None),
    max_area: int | None = Query(default=None),
    bedrooms: int | None = Query(default=None),
    query: str | None = Query(default=None),
    subcategory: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_archived: bool = Query(default=False),
    archived_only: bool = Query(default=False),
):
    properties, total_count = get_properties(
        city=city,
        property_type=property_type,
        listing_type=listing_type,
        min_price=min_price,
        max_price=max_price,
        min_area=min_area,
        max_area=max_area,
        bedrooms=bedrooms,
        query=query,
        subcategory=subcategory,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        archived_only=archived_only,
    )
    return {"count": total_count, "items": properties}


@app.get("/properties/{property_id}")
def property_detail(property_id: int):
    property_data = get_property_by_id(property_id)
    if not property_data:
        raise HTTPException(status_code=404, detail="Property not found")
    return property_data


@app.post("/register")
def register(user: UserRegister):
    if len(user.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(user.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    success = create_user(user.username, user.password)
    if not success:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    return {"message": "User created successfully"}


@app.post("/login")
def login(user: UserLogin):
    authenticated_user = authenticate_user(user.username, user.password)
    if not authenticated_user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    access_token = create_access_token(data={"sub": authenticated_user["username"], "role": authenticated_user["role"]})
    return {"access_token": access_token, "token_type": "bearer", "role": authenticated_user["role"]}


def get_current_user_role(request: Request):
    """Extract and verify the user's role from the JWT token."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    
    token = auth_header.split(" ")[1]
    payload = verify_token(token)
    if not payload:
        return None
    
    return payload.get("role")


@app.get("/admin/search")
def admin_search(search_id: str, include_archived: bool = False, request: Request = None):
    """Search for properties by ID or ad_id. Admin only."""
    role = get_current_user_role(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    properties = search_properties_by_id(search_id, include_archived=include_archived)
    return {"count": len(properties), "items": properties}


@app.get("/admin/archive-search")
def admin_archive_search(
    search: str | None = Query(default=None),
    archived_only: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=200),
    sort_by: str = Query(default="id"),
    sort_dir: str = Query(default="desc"),
    request: Request = None,
):
    """Server-side paginated search for the archiving section's DataTable.
    Returns one page of results plus counts for DataTables' pagination.
    Admin only."""
    role = get_current_user_role(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    return search_properties_admin(
        search=search,
        archived_only=archived_only,
        offset=offset,
        limit=limit,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@app.post("/admin/{property_id}/archive")
def admin_archive_property(property_id: int, request: Request = None):
    """Archive a property by ID. Admin only."""
    role = get_current_user_role(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    archive_property(property_id)
    return {"message": "Property archived successfully"}


@app.post("/admin/{property_id}/unarchive")
def admin_unarchive_property(property_id: int, request: Request = None):
    """Unarchive a property by ID. Admin only."""
    role = get_current_user_role(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    unarchive_property(property_id)
    return {"message": "Property unarchived successfully"}


@app.get("/admin/kpis")
def get_kpis(request: Request = None):
    """Get dashboard KPIs. Admin only."""
    role = get_current_user_role(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_conn()
    cur = conn.cursor()
    
    # Properties per property type
    cur.execute("""
        SELECT property_type, COUNT(*) as count
        FROM properties
        WHERE archived = FALSE
        GROUP BY property_type
        ORDER BY count DESC
    """)
    properties_by_type = {row[0]: row[1] for row in cur.fetchall()}
    
    # Number of archived ads
    cur.execute("SELECT COUNT(*) FROM properties WHERE archived = TRUE")
    archived_count = cur.fetchone()[0]
    
    # Number of users registered (excluding admin)
    cur.execute("SELECT COUNT(*) FROM users WHERE role != 'admin'")
    user_count = cur.fetchone()[0]
    
    # Number of ads scraped from each website
    cur.execute("""
        SELECT source, COUNT(*) as count
        FROM properties
        WHERE archived = FALSE
        GROUP BY source
        ORDER BY count DESC
    """)
    ads_by_source = {row[0]: row[1] for row in cur.fetchall()}
    
    cur.close()
    conn.close()
    
    return {
        "properties_by_type": properties_by_type,
        "archived_count": archived_count,
        "user_count": user_count,
        "ads_by_source": ads_by_source
    }