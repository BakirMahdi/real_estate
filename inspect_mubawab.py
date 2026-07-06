import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.mubawab.tn/fr/ct/tunis/immobilier-a-vendre"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    response = requests.get(url, headers=headers, timeout=20)
    print("Status:", response.status_code)
    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select("div.listingBox[linkRef]")
    print("Found", len(cards), "cards")
    if cards:
        card = cards[0]
        # Let's print the card's inner HTML or elements that might be images
        print("Card keys:", card.attrs)
        print("Images inside card:")
        for img in card.select("img"):
            print("  img:", img.attrs)
        # Let's print the HTML of the first card to check where image is
        print("\nCard HTML:")
        print(card.prettify()[:2000])
except Exception as e:
    print("Error:", e)
