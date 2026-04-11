"""
Restaurant Matcher
==================
Fuzzy matches restaurants across all sources by name and postcode.
Creates one master record per restaurant combining fields from all sources.

Match strategy:
  1. Exact postcode match + fuzzy name match (>85 score) = confident match
  2. Fuzzy name only (>90 score) = possible match
  3. No match = unmatched record

Output: data/processed/master/master_{area}_{timestamp}.json
"""

import json
import os
from pathlib import Path
from datetime import datetime
from fuzzywuzzy import fuzz

from config import PROCESSED_DIR
from processing.lineage import log_transformation, generate_run_id


# ==================================================================
# Loaders
# ==================================================================

def load_processed(source: str, area_name: str) -> list[dict]:
    """Load most recent processed file for a source/area."""
    folder = PROCESSED_DIR / source
    if not folder.exists():
        return []
    slug = area_name.lower().replace(" ", "_").replace("-", "_")
    files = sorted(
        [f for f in folder.glob(f"{slug}*.json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    if not files:
        return []
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)


# ==================================================================
# Matching logic
# ==================================================================

def name_score(name1: str, name2: str) -> int:
    """Fuzzy match score using multiple strategies."""
    if not name1 or not name2:
        return 0
    scores = [
        fuzz.token_sort_ratio(name1, name2),
        fuzz.token_set_ratio(name1, name2),
        fuzz.partial_ratio(name1, name2),
    ]
    return max(scores)


def postcode_matches(pc1: str, pc2: str) -> bool:
    """Check if two postcodes match at district level (e.g. E1)."""
    if not pc1 or not pc2:
        return False
    # Compare first part only e.g. "E1" from "E1 6AB"
    p1 = pc1.upper().split()[0] if pc1 else ""
    p2 = pc2.upper().split()[0] if pc2 else ""
    return p1 == p2


def find_match(
    record: dict,
    candidates: list[dict],
    name_threshold: int = 75,
) -> dict | None:
    """
    Find best matching record from candidates.
    Uses postcode district + fuzzy name matching.
    """
    name = record.get("name_normalised", "")
    postcode = record.get("postcode", "")

    best_score = 0
    best_match = None

    for candidate in candidates:
        cand_name = candidate.get("name_normalised", "")
        cand_postcode = candidate.get("postcode", "")

        # Base fuzzy score
        score = name_score(name, cand_name)

        # Postcode district match — strong signal
        if postcode and cand_postcode:
            if postcode_matches(postcode, cand_postcode):
                score = min(100, score + 15)
            else:
                # Penalise mismatched postcodes
                score = max(0, score - 20)

        # First word match bonus — "dishoom" in "dishoom limited"
        first_word = name.split()[0] if name else ""
        if first_word and len(first_word) > 3:
            if first_word in cand_name:
                score = min(100, score + 10)

        if score > best_score:
            best_score = score
            best_match = candidate

    if best_score >= name_threshold:
        return best_match
    return None


# ==================================================================
# Master record builder
# ==================================================================

def build_master_record(
    google: dict = None,
    fsa: dict = None,
    companies: dict = None,
    deliveroo: dict = None,
) -> dict:
    """
    Merge matched records from all sources into one master record.
    Google Places is the primary source for name/location.
    """
    # Use Google Places as primary, fall back to FSA
    primary = google or fsa or {}

    return {
        # Identity
        "name": primary.get("name"),
        "name_normalised": primary.get("name_normalised"),
        "neighbourhood": primary.get("neighbourhood"),

        # Location
        "address": primary.get("address") or (fsa or {}).get("address"),
        "postcode": (
            primary.get("postcode")
            or (fsa or {}).get("postcode")
            or (deliveroo or {}).get("postcode")
        ),
        "latitude": (
            (google or {}).get("latitude")
            or (fsa or {}).get("latitude")
        ),
        "longitude": (
            (google or {}).get("longitude")
            or (fsa or {}).get("longitude")
        ),

        # Google Places data
        "google_place_id": (google or {}).get("google_place_id"),
        "google_rating": (google or {}).get("rating"),
        "google_review_count": (google or {}).get("review_count"),
        "google_price_level": (google or {}).get("price_level"),
        "google_types": (google or {}).get("types", []),
        "opening_hours": (google or {}).get("opening_hours", []),
        "reviews": (google or {}).get("reviews", []),

        # FSA hygiene data
        "fsa_id": (fsa or {}).get("fsa_id"),
        "hygiene_rating": (fsa or {}).get("rating_value"),
        "hygiene_rating_date": (fsa or {}).get("rating_date"),
        "score_hygiene": (fsa or {}).get("score_hygiene"),
        "score_structural": (fsa or {}).get("score_structural"),
        "score_management": (fsa or {}).get("score_management"),
        "business_type": (fsa or {}).get("business_type"),

        # Companies House data
        "company_number": (companies or {}).get("company_number"),
        "company_name": (companies or {}).get("name"),
        "company_status": (companies or {}).get("status"),
        "incorporation_date": (companies or {}).get("incorporation_date"),
        "sic_codes": (companies or {}).get("sic_codes", []),
        "accounts_overdue": (companies or {}).get("accounts_overdue"),
        "distress_signals": (companies or {}).get("distress_signals", []),

        # Deliveroo data
        "deliveroo_rating": (deliveroo or {}).get("deliveroo_rating"),
        "delivery_fee": (deliveroo or {}).get("delivery_fee"),
        "min_order": (deliveroo or {}).get("min_order"),
        "estimated_delivery_mins": (deliveroo or {}).get("estimated_delivery_mins"),
        "menu_items": (deliveroo or {}).get("menu_items", []),
        "menu_item_count": (deliveroo or {}).get("menu_item_count", 0),

        # Sources matched
        "sources_matched": [
            s for s, r in [
                ("google_places", google),
                ("fsa", fsa),
                ("companies_house", companies),
                ("deliveroo", deliveroo),
            ] if r is not None
        ],

        # Lineage
        "_lineage": {
            "source": "matcher",
            "collected_at": datetime.now().isoformat(),
            "collector_version": "1.0",
            "run_id": "matcher",
            "sources_merged": [
                s for s, r in [
                    ("google_places", google),
                    ("fsa", fsa),
                    ("companies_house", companies),
                    ("deliveroo", deliveroo),
                ] if r is not None
            ],
        }
    }


# ==================================================================
# Main matching runner
# ==================================================================

def match_area(area_name: str) -> list[dict]:
    """Match all sources for one area and return master records."""
    print(f"\n  Matching: {area_name}")

    # Load processed data
    google_records = load_processed("google_places", area_name)
    fsa_records = load_processed("fsa", area_name)
    company_records = load_processed("companies_house", area_name)
    deliveroo_records = load_processed("deliveroo", area_name)

    print(f"    Google Places: {len(google_records)}")
    print(f"    FSA:           {len(fsa_records)}")
    print(f"    Companies House: {len(company_records)}")
    print(f"    Deliveroo:     {len(deliveroo_records)}")

    master_records = []
    used_fsa = set()
    used_companies = set()
    used_deliveroo = set()

    # Use Google Places as anchor — match other sources to it
    for google in google_records:
        fsa_match = find_match(google, fsa_records, name_threshold=75)
        company_match = find_match(google, company_records, name_threshold=70)
        deliveroo_match = find_match(google, deliveroo_records, name_threshold=75)

        if fsa_match:
            used_fsa.add(fsa_match.get("fsa_id") or fsa_match.get("name"))
        if company_match:
            used_companies.add(company_match.get("company_number"))
        if deliveroo_match:
            used_deliveroo.add(deliveroo_match.get("name_normalised"))

        master = build_master_record(
            google=google,
            fsa=fsa_match,
            companies=company_match,
            deliveroo=deliveroo_match,
        )
        master_records.append(master)

    # Add unmatched FSA records not matched to any Google Places record
    for fsa in fsa_records:
        fsa_key = fsa.get("fsa_id") or fsa.get("name")
        if fsa_key not in used_fsa:
            master = build_master_record(fsa=fsa)
            master_records.append(master)

    print(f"    Master records: {len(master_records)}")
    print(f"    FSA matched: {len(used_fsa)}/{len(fsa_records)}")
    print(f"    Companies matched: {len(used_companies)}/{len(company_records)}")
    print(f"    Deliveroo matched: {len(used_deliveroo)}/{len(deliveroo_records)}")

    return master_records


def save_master(records: list[dict], area_name: str) -> Path:
    """Save master records to processed/master folder."""
    folder = PROCESSED_DIR / "master"
    folder.mkdir(parents=True, exist_ok=True)
    slug = area_name.lower().replace(" ", "_").replace("-", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = folder / f"{slug}_{timestamp}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False, default=str)
    return filepath


def run_matching():
    from config import TARGET_AREAS

    print(f"\n{'='*60}")
    print(f"  PHASE 4 — STEP 2: FUZZY MATCHING")
    print(f"{'='*60}")

    total_master = 0

    for area in TARGET_AREAS:
        run_id = generate_run_id()
        records = match_area(area["name"])

        filepath = save_master(records, area["name"])

        log_transformation(
            run_id=run_id,
            source_file=f"processed/all/{area['name']}",
            destination_table="processed/master",
            records_in=sum([
                len(load_processed(s, area["name"]))
                for s in ["google_places", "fsa", "companies_house", "deliveroo"]
            ]),
            records_out=len(records),
            transformations=["fuzzy_matched", "merged"],
        )

        total_master += len(records)
        print(f"    Saved: {filepath.name}")

    print(f"\n{'='*60}")
    print(f"  DONE: {total_master} master records created")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_matching()