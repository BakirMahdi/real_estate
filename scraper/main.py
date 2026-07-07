from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from .scrapers.tayara import scrape_tayara
from .scrapers.mubawab import scrape_mubawab
from .scrapers.affare import scrape_affare
from .scrapers.expat import scrape_expat
from .insert import bulk_get_existing_ids, bulk_insert_properties, bulk_get_latest_properties, is_same_property
from .queries import get_properties, get_property_by_id, get_all_properties, search_properties_by_id, archive_property, unarchive_property
from .db import get_conn
from .sample_log import log_scrape_samples
from .auth import create_user, authenticate_user, create_access_token, verify_token, verify_token as verify_jwt_token, is_admin
from pydantic import BaseModel
import asyncio
import time
import os
from concurrent.futures import ThreadPoolExecutor
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

scrape_status_state = {
    "is_scraping": False,
    "results": None,
    "error": None,
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
            asyncio.create_task(asyncio.to_thread(_run_scrape_task))
        else:
            print(f"[Scheduler] Automatic weekly scrape skipped because a scrape is already running.")
            
        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(weekly_scheduler())

def archive_missing_ads(found_ad_ids):
    """Archive ads that are in the DB but were not found in the current scrape."""
    if not found_ad_ids:
        return 0
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        # Get all non-archived ad_ids from DB
        cur.execute("SELECT source, ad_id FROM properties WHERE archived = FALSE")
        all_db_ads = {(row[0], row[1]) for row in cur.fetchall()}
        
        # Find ads that should be archived (in DB but not in current scrape)
        to_archive = []
        for source, ad_id in all_db_ads:
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
        return len(to_archive)
    except Exception as e:
        print(f"Error archiving ads: {e}")
        return 0


def _run_scrape_task():
    try:
        scrape_status_state["is_scraping"] = True
        scrape_status_state["results"] = None
        scrape_status_state["error"] = None

        results = []
        source_samples = []
        
        # Track all ad_ids found in this scrape for archiving later
        found_ad_ids = set()

        # Run all scrapers in parallel
        scrapers = [scrape_tayara, scrape_mubawab, scrape_affare, scrape_expat]
        scraper_data = {}
        with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
            futures = {executor.submit(s): s for s in scrapers}
            for future in futures:
                scraper_fn = futures[future]
                try:
                    scraper_data[scraper_fn.__name__] = future.result()
                except Exception as e:
                    scraper_data[scraper_fn.__name__] = e

        for scraper in scrapers:
            name = scraper.__name__
            data_or_err = scraper_data.get(name)

            if isinstance(data_or_err, Exception):
                source_samples.append({"source": name, "total_count": 0, "first_row": None, "error": str(data_or_err)})
                results.append({"source": name, "error": str(data_or_err)})
                continue

            data = data_or_err

            # Determine source tag from the first item, fall back to scraper name
            source_tag = data[0]["source"] if data else name

            # Bulk latest properties retrieval: one DB round-trip for all ad_ids
            all_ad_ids = [item["ad_id"] for item in data if item.get("ad_id")]
            latest_properties = bulk_get_latest_properties(source_tag, all_ad_ids)

            # Filter scraped items: insert if new or if values changed (versioning)
            new_items = []
            skipped = 0
            for item in data:
                ad_id = item.get("ad_id")
                if not ad_id:
                    continue
                found_ad_ids.add((source_tag, ad_id))
                latest_db = latest_properties.get(ad_id)
                if latest_db is None:
                    new_items.append(item)
                else:
                    if is_same_property(item, latest_db):
                        skipped += 1
                    else:
                        # Values changed - insert as new version
                        new_items.append(item)

            no_id_errors = sum(1 for item in data if not item.get("ad_id"))

            # Bulk insert in a single DB connection/transaction
            inserted, insert_errors = bulk_insert_properties(new_items)
            errors = no_id_errors + insert_errors

            source_samples.append({
                "source": name,
                "total_count": len(data),
                "first_row": data[0] if data else None,
            })
            results.append({
                "source": name,
                "count": len(data),
                "inserted": inserted,
                "skipped": skipped,
                "errors": errors,
                "archived": 0,  # Will be updated below
                "message": (
                    "skipped = annonces déjà présentes en base (doublons source+ad_id)"
                    if skipped
                    else None
                ),
            })

        # Archive ads that were not found in this scrape
        archived_count = archive_missing_ads(found_ad_ids)
        if archived_count > 0:
            results.append({
                "source": "archiving",
                "count": 0,
                "inserted": 0,
                "skipped": 0,
                "errors": 0,
                "archived": archived_count,
                "message": f"Archived {archived_count} ads not found in scrape"
            })

        log_scrape_samples(source_samples)
        scrape_status_state["results"] = results
    except Exception as e:
        scrape_status_state["error"] = str(e)
    finally:
        scrape_status_state["is_scraping"] = False


@app.post("/scrape")
def start_scrape(background_tasks: BackgroundTasks):
    if scrape_status_state["is_scraping"]:
        return {"status": "already_running"}
    
    background_tasks.add_task(_run_scrape_task)
    return {"status": "started"}

@app.get("/scrape/status")
def get_scrape_status():
    return {
        **scrape_status_state,
        "next_scrape_time": next_scrape_time
    }


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