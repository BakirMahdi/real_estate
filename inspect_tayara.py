import json
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

with open("tayara_debug.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
next_data = soup.find("script", id="__NEXT_DATA__")
if next_data:
    json_data = json.loads(next_data.string)
    page_props = json_data.get("props", {}).get("pageProps", {})
    action = page_props.get("searchedListingsAction", {})
    hits = list(action.get("newHits") or [])
    
    print("Found", len(hits), "hits in tayara_debug.html")
    for idx, ad in enumerate(hits):
        title = ad.get("title")
        metadata = ad.get("metadata", {})
        subcat = metadata.get("subCategory")
        category = metadata.get("category")
        print(f"Hit {idx}: Title={title} | subCategory={subcat} | category={category}")
else:
    print("No __NEXT_DATA__ found")
