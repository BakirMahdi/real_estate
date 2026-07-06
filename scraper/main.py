from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from .scrapers.tayara import scrape_tayara
from .scrapers.mubawab import scrape_mubawab
from .insert import bulk_get_existing_ids, bulk_insert_properties
from .queries import get_properties, get_property_by_id, get_all_properties
from .db import get_conn
from .sample_log import log_scrape_samples
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

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

async def hourly_scheduler():
    global next_scrape_time
    while True:
        now_ts = time.time()
        next_scrape_time = ((now_ts // 3600) + 1) * 3600
        delay = next_scrape_time - now_ts
        if delay <= 0:
            delay = 3600
        
        print(f"[Scheduler] Next auto-scrape scheduled at timestamp {next_scrape_time} ({datetime.fromtimestamp(next_scrape_time).isoformat()}) (in {delay:.2f} seconds)")
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            break
            
        next_scrape_time = next_scrape_time + 3600
        
        if not scrape_status_state["is_scraping"]:
            print(f"[Scheduler] Starting automatic hourly scrape at {datetime.now().isoformat()}...")
            asyncio.create_task(asyncio.to_thread(_run_scrape_task))
        else:
            print(f"[Scheduler] Automatic hourly scrape skipped because a scrape is already running.")
            
        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(hourly_scheduler())

def _run_scrape_task():
    try:
        scrape_status_state["is_scraping"] = True
        scrape_status_state["results"] = None
        scrape_status_state["error"] = None

        results = []
        source_samples = []

        # Run both scrapers in parallel
        scrapers = [scrape_tayara, scrape_mubawab]
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

            # Bulk existence check: one DB round-trip for all ad_ids
            all_ad_ids = [item["ad_id"] for item in data if item.get("ad_id")]
            existing_ids = bulk_get_existing_ids(source_tag, all_ad_ids)

            # Filter to only new items
            new_items = [
                item for item in data
                if item.get("ad_id") and item["ad_id"] not in existing_ids
            ]
            skipped = len(data) - len(new_items)
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
                "message": (
                    "skipped = annonces déjà présentes en base (doublons source+ad_id)"
                    if skipped
                    else None
                ),
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
def list_all_properties():
    properties = get_all_properties()
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
):
    properties = get_properties(
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
    )
    return {"count": len(properties), "items": properties}


@app.get("/properties/{property_id}")
def property_detail(property_id: int):
    property_data = get_property_by_id(property_id)
    if not property_data:
        raise HTTPException(status_code=404, detail="Property not found")
    return property_data