"""
Data Cleaner
============
Cleans and normalises raw collected data before loading into databases.

Steps:
  1. Standardise field names across sources
  2. Clean postcodes
  3. Clean restaurant names
  4. Remove Deliveroo duplicate price rows
  5. Sanitise data before LLM calls
"""

import re
import json
import os
from pathlib import Path
from datetime import datetime, timezone

from config import RAW_DIR, PROCESSED_DIR
from processing.lineage import log_transformation, generate_run_id


NON_RESTAURANT_TYPES = {
    "lodging", "hotel", "pharmacy", "store", "supermarket",
    "grocery_or_supermarket", "convenience_store", "clothing_store",
    "home_goods_store", "furniture_store", "electronics_store",
    "car_dealer", "car_rental", "gas_station", "bank", "atm",
    "gym", "spa", "beauty_salon", "hair_care", "hospital",
    "doctor", "dentist", "school", "university", "library",
    "movie_theater", "bowling_alley", "amusement_park",
}

def is_restaurant(record: dict) -> bool:
    """Return True only if record is primarily a restaurant/food business."""
    types = set(record.get("types") or [])

    # Exclude anything with lodging — hotels with restaurants still aren't restaurants
    if "lodging" in types:
        return False

    # Must have at least one food-related type
    food_types = {
        "restaurant", "food", "cafe", "bakery", "bar",
        "meal_takeaway", "meal_delivery",
    }
    return bool(types & food_types)

# ==================================================================
# Postcode cleaning
# ==================================================================

def clean_postcode(postcode: str) -> str | None:
    """Standardise postcode — uppercase, single space, valid format."""
    if not postcode:
        return None
    postcode = postcode.upper().strip().replace("  ", " ")
    match = re.match(r"([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})", postcode)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return None


# ==================================================================
# Name cleaning
# ==================================================================

def clean_name(name: str) -> str | None:
    """Standardise restaurant name for matching."""
    if not name:
        return None
    name = name.strip()
    # Remove branch suffixes for matching
    name = re.sub(r"\s*[-–]\s*(shoreditch|peckham|hackney|london|tower hill|spitalfields|bethnal green|brick lane|dalston|hoxton|old street).*$", "", name, flags=re.I)
    # Normalise whitespace
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def normalise_name(name: str) -> str:
    """Lowercase, remove punctuation for fuzzy matching."""
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


# ==================================================================
# Deliveroo menu cleaning
# ==================================================================

def clean_menu_items(items: list[dict]) -> list[dict]:
    """
    Remove duplicate price rows, calorie rows, and promo items
    from Deliveroo menu items.
    """
    cleaned = []
    seen = set()

    for item in items:
        name = (item.get("name") or "").strip()

        # Skip empty names
        if not name:
            continue

        # Skip price-only rows like "£17.99"
        if re.match(r"^£[\d.]+", name):
            continue

        # Skip discounted price rows like "£18.00£20.25"
        if re.match(r"^£[\d.]+£[\d.]+", name):
            continue

        # Skip calorie rows like "869 kcal"
        if re.match(r"^\d+\s*kcal", name, re.I):
            continue

        # Skip promo items
        promo_phrases = ["% off", "new customers", "off entire", "free item", "meal deal"]
        if any(p in name.lower() for p in promo_phrases):
            continue

        # Deduplicate by name + price
        key = (name.lower(), item.get("price"))
        if key in seen:
            continue
        seen.add(key)

        cleaned.append(item)

    return cleaned


# ==================================================================
# Sanitisation — strip personal data before LLM
# ==================================================================

def sanitise_for_llm(text: str) -> str:
    """
    Strip personal data before sending to LLM.
    Removes: phone numbers, emails, reviewer names.
    """
    if not text:
        return ""
    # Remove phone numbers
    text = re.sub(r"\b(\+44|0)[\d\s\-]{9,13}\b", "[PHONE]", text)
    # Remove email addresses
    text = re.sub(r"[\w.\-]+@[\w.\-]+\.\w+", "[EMAIL]", text)
    # Remove UK postcodes from free text (keep in structured fields)
    text = re.sub(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b", "[POSTCODE]", text)
    return text


def sanitise_reviews(reviews: list[dict]) -> list[dict]:
    """Sanitise review text and remove author names."""
    sanitised = []
    for review in reviews:
        sanitised.append({
            "text": sanitise_for_llm(review.get("text", "")),
            "rating": review.get("rating"),
            "date": review.get("date"),
            "language": review.get("language", "en"),
        })
    return sanitised


# ==================================================================
# Source-specific cleaners
# ==================================================================

def clean_google_places(records: list[dict]) -> list[dict]:
    """Clean Google Places records."""
    cleaned = []
    for r in records:
        # Skip non-restaurants
        if not is_restaurant(r):
            continue
        cleaned.append({
            "google_place_id": r.get("google_place_id"),
            "name": clean_name(r.get("name")),
            "name_normalised": normalise_name(r.get("name", "")),
            "address": r.get("address"),
            "postcode": clean_postcode(
                re.search(r"[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}", r.get("address", ""), re.I).group()
                if re.search(r"[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}", r.get("address", ""), re.I)
                else None
            ),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "rating": r.get("rating"),
            "review_count": r.get("review_count"),
            "price_level": r.get("price_level"),
            "types": r.get("types", []),
            "opening_hours": r.get("opening_hours", []),
            "reviews": sanitise_reviews(r.get("reviews", [])),
            "neighbourhood": r.get("neighbourhood"),
            "_lineage": r.get("_lineage"),
        })
    return cleaned


def clean_fsa(records: list[dict]) -> list[dict]:
    """Clean FSA records."""
    cleaned = []
    for r in records:
        rating = r.get("rating_value")
        try:
            rating = int(rating) if rating is not None else None
        except (ValueError, TypeError):
            rating = None

        cleaned.append({
            "fsa_id": r.get("fsa_id"),
            "name": clean_name(r.get("business_name")),
            "name_normalised": normalise_name(r.get("business_name", "")),
            "address": r.get("address"),
            "postcode": clean_postcode(r.get("postcode")),
            "rating_value": rating,
            "rating_date": r.get("rating_date"),
            "business_type": r.get("business_type"),
            "score_hygiene": r.get("score_hygiene"),
            "score_structural": r.get("score_structural"),
            "score_management": r.get("score_management"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "local_authority": r.get("local_authority"),
            "neighbourhood": r.get("neighbourhood"),
            "_lineage": r.get("_lineage"),
        })
    return cleaned


def clean_companies_house(records: list[dict]) -> list[dict]:
    """Clean Companies House records."""
    cleaned = []
    for r in records:
        cleaned.append({
            "company_number": r.get("company_number"),
            "name": clean_name(r.get("company_name")),
            "name_normalised": normalise_name(r.get("company_name", "")),
            "registered_address": r.get("registered_address"),
            "postcode": clean_postcode(
                re.search(r"[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}", r.get("registered_address", ""), re.I).group()
                if re.search(r"[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}", r.get("registered_address", ""), re.I)
                else None
            ),
            "status": r.get("status"),
            "incorporation_date": r.get("incorporation_date"),
            "sic_codes": r.get("sic_codes", []),
            "accounts_overdue": r.get("accounts_overdue", False),
            "distress_signals": r.get("distress_signals", []),
            "officers": r.get("officers", []),
            "filing_summary": r.get("filing_summary", {}),
            "neighbourhood": r.get("neighbourhood"),
            "_lineage": r.get("_lineage"),
        })
    return cleaned


def clean_deliveroo(records: list[dict]) -> list[dict]:
    """Clean Deliveroo records."""
    cleaned = []
    for r in records:
        menu_items = clean_menu_items(r.get("menu_items", []))
        cleaned.append({
            "name": clean_name(r.get("name")),
            "name_normalised": normalise_name(r.get("name", "")),
            "postcode": clean_postcode(r.get("postcode")),
            "deliveroo_rating": r.get("deliveroo_rating"),
            "delivery_fee": r.get("delivery_fee"),
            "min_order": r.get("min_order"),
            "estimated_delivery_mins": r.get("estimated_delivery_mins"),
            "cuisine_tags": r.get("cuisine_tags", []),
            "menu_items": menu_items,
            "menu_item_count": len(menu_items),
            "neighbourhood": r.get("neighbourhood"),
            "_lineage": r.get("_lineage"),
        })
    return cleaned


def clean_ons_census(records: list[dict]) -> list[dict]:
    """Clean ONS census records — mostly pass through."""
    cleaned = []
    for r in records:
        record = {k: v for k, v in r.items()}
        cleaned.append(record)
    return cleaned


# ==================================================================
# Main runner
# ==================================================================

CLEANERS = {
    "google_places": clean_google_places,
    "fsa": clean_fsa,
    "companies_house": clean_companies_house,
    "deliveroo": clean_deliveroo,
    "ons_census": clean_ons_census,
}


def load_latest(source: str, area_name: str) -> tuple[Path, list[dict]]:
    """Load most recent raw file for a source/area."""
    folder = RAW_DIR / source
    slug = area_name.lower().replace(" ", "_").replace("-", "_")
    files = sorted(
        [f for f in folder.glob(f"{slug}*.json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    if not files:
        return None, []
    with open(files[0], encoding="utf-8") as f:
        return files[0], json.load(f)


def save_processed(data: list[dict], source: str, area_name: str) -> Path:
    """Save cleaned data to processed folder."""
    folder = PROCESSED_DIR / source
    folder.mkdir(parents=True, exist_ok=True)
    slug = area_name.lower().replace(" ", "_").replace("-", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = folder / f"{slug}_{timestamp}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return filepath


def run_cleaning():
    """Clean all raw data and save to processed folder."""
    from config import TARGET_AREAS

    print(f"\n{'='*60}")
    print(f"  PHASE 4 — STEP 1: DATA CLEANING")
    print(f"{'='*60}\n")

    total_in = 0
    total_out = 0

    for source, cleaner in CLEANERS.items():
        print(f"\n--- {source} ---")
        for area in TARGET_AREAS:
            run_id = generate_run_id()
            filepath, records = load_latest(source, area["name"])

            if not records:
                print(f"  {area['name']}: no data found")
                continue

            cleaned = cleaner(records)
            out_path = save_processed(cleaned, source, area["name"])

            log_transformation(
                run_id=run_id,
                source_file=str(filepath),
                destination_table=f"processed/{source}",
                records_in=len(records),
                records_out=len(cleaned),
                transformations=["cleaned", "normalised", "sanitised"],
            )

            total_in += len(records)
            total_out += len(cleaned)
            print(f"  {area['name']}: {len(records)} → {len(cleaned)} records → {out_path.name}")

    print(f"\n{'='*60}")
    print(f"  DONE: {total_in} records in → {total_out} records out")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_cleaning()