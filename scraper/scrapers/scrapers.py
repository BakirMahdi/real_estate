def normalize_price(price_str):
    # Removes "DT", spaces, and dots
    clean = price_str.replace("DT", "").replace(" ", "").replace(".", "")
    return float(clean) if clean.isdigit() else 0.0