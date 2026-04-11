"""
Data Cleaner
============
Cleans and normalises raw data from all collectors.

Steps per source:
  - Normalise names and postcodes
  - Filter non-restaurants (hotels, supermarkets, florists)
  - Sanitise personal data before LLM ingestion
  - Clean Deliveroo menu items (remove price rows, dupes)
"""

import re
import json
from pathlib import Path
from datetime import datetime, timezone

from config import RAW_DIR, PROCESSED_DIR
from processing.lineage import log_transformation, generate_run_id


# ==================================================================
# Google Places — filter non-restaurants
# ==================================================================

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

    # Exclude anything with lodging
    if "lodging" in types:
        return False

    # Must have at least one food-related type
    food_types = {
        "restaurant", "food", "cafe", "bakery", "bar",
        "meal_takeaway", "meal_delivery",
    }
    return bool(types & food_types)


# ==================================================================
# Deliveroo — filter non-food businesses
# ==================================================================

DELIVEROO_EXCLUDE_KEYWORDS = {
    "whole foods", "tesco", "sainsbury", "waitrose", "marks & spencer",
    "m&s food", "co-op", "lidl", "aldi", "morrisons", "asda", "boots",
    "superdrug", "pharmacy", "chemist", "flowers", "florist",
    "amazon", "deliveroo hop", "gorillas", "getir", "gopuff",
}


def is_restaurant_deliveroo(record: dict) -> bool:
    """Filter out supermarkets and non-food businesses from Deliveroo."""
    name = (record.get("name") or "").lower()
    return not any(kw in name for kw in DELIVEROO_EXCLUDE_KEYWORDS)


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
    name = re.sub(
        r"\s*[-–]\s*(shoreditch|peckham|hackney|london|tower hill|"
        r"spitalfields|bethnal green|brick lane|dalston|hoxton|old street).*$",
        "", name, flags=re.I
    )
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

        if not name:
            continue
        if re.match(r"^£[\d.]+", name):
            continue
        if re.match(r"^£[\d.]+£[\d.]+", name):
            continue
        if re.match(r"^\d+\s*kcal", name, re.I):
            continue

        promo_phrases = ["% off", "new customers", "off entire", "free item", "meal deal"]
        if any(p in name.lower() for p in promo_phrases):
            continue

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
    """Strip personal data before sending to LLM."""
    if not text:
        return ""
    text = re.sub(r"\b(\+44|0)[\d\s\-]{9,13}\b", "[PHONE]", text)
    text = re.sub(r"[\w.\-]+@[\w.\-]+\.\w+", "[EMAIL]", text)
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
    """Clean Google Places records — filter hotels, normalise fields."""
    cleaned = []
    for r in records:
        if not is_restaurant(r):
            continue
        cleaned.append({
            "google_place_id": r.get("google_place_id"),
            "name": clean_name(r.get("name")),
            "name_normalised": normalise_name(r.get("name", "")),
            "address": r.get("address"),
            "postcode": clean_postcode(
                re.search(
                    r"[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}",
                    r.get("address", ""), re.I
                ).group()
                if re.search(
                    r"[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}",
                    r.get("address", ""), re.I
                ) else None
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
    """Clean FSA records — normalise ratings and postcodes."""
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
                re.search(
                    r"[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}",
                    r.get("registered_address", ""), re.I
                ).group()
                if re.search(
                    r"[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}",
                    r.get("registered_address", ""), re.I
                ) else None
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
    """Clean Deliveroo records — filter non-food businesses, clean menus."""
    cleaned = []
    for r in records:
        # Skip non-food businesses
        if not is_restaurant_deliveroo(r):
            continue

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
    """Clean ONS census records — pass through with minor fixes."""
    return [{k: v for k, v in r.items()} for r in records]


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