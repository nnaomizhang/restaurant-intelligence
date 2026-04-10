"""
Data Completeness Validator
============================
Validates collected raw data files before processing.
Sources: google_places, fsa, companies_house, deliveroo, ons_census

Usage:
  python tests/test_data_completeness.py
  python tests/test_data_completeness.py --source fsa
  python tests/test_data_completeness.py --area Shoreditch
  python tests/test_data_completeness.py --verbose
"""

import json
import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import TARGET_AREAS, RAW_DIR


# ==================================================================
# Field specifications
# ==================================================================

GOOGLE_PLACES_FIELDS = {
    "google_place_id": {"required": True,  "type": str,          "description": "Google Place ID"},
    "name":            {"required": True,  "type": str,          "description": "Business name"},
    "address":         {"required": True,  "type": str,          "description": "Full address"},
    "latitude":        {"required": True,  "type": (int, float), "description": "Latitude"},
    "longitude":       {"required": True,  "type": (int, float), "description": "Longitude"},
    "rating":          {"required": False, "type": (int, float), "description": "Google rating"},
    "review_count":    {"required": False, "type": int,          "description": "Total reviews"},
    "price_level":     {"required": False, "type": int,          "description": "Price level 1-4"},
    "types":           {"required": False, "type": list,         "description": "Business types"},
    "reviews":         {"required": True,  "type": list,         "description": "Review list"},
    "neighbourhood":   {"required": True,  "type": str,          "description": "Target neighbourhood"},
}

GOOGLE_PLACES_REVIEW_FIELDS = {
    "text":     {"required": True,  "type": str,          "description": "Review text"},
    "rating":   {"required": True,  "type": (int, float), "description": "Review rating"},
    "language": {"required": False, "type": str,          "description": "Language code"},
}

FSA_FIELDS = {
    "business_name":   {"required": True,  "type": str,          "description": "Business name"},
    "address":         {"required": True,  "type": str,          "description": "Full address"},
    "postcode":        {"required": True,  "type": str,          "description": "Postcode"},
    "rating_value":    {"required": True,  "type": (int, float), "description": "Hygiene rating 0-5"},
    "business_type":   {"required": False, "type": str,          "description": "FSA business category"},
    "score_hygiene":   {"required": False, "type": (str, int),   "description": "Hygiene sub-score"},
    "score_structural":{"required": False, "type": (str, int),   "description": "Structural sub-score"},
    "score_management":{"required": False, "type": (str, int),   "description": "Management sub-score"},
    "neighbourhood":   {"required": True,  "type": str,          "description": "Target neighbourhood"},
}

COMPANIES_HOUSE_FIELDS = {
    "company_number":     {"required": True,  "type": str,  "description": "Company registration number"},
    "company_name":       {"required": True,  "type": str,  "description": "Registered company name"},
    "status":             {"required": True,  "type": str,  "description": "Company status"},
    "registered_address": {"required": False, "type": str,  "description": "Registered address"},
    "incorporation_date": {"required": False, "type": str,  "description": "Date of incorporation"},
    "sic_codes":          {"required": False, "type": list, "description": "SIC codes"},
    "accounts_overdue":   {"required": False, "type": bool, "description": "Accounts overdue flag"},
    "filing_summary":     {"required": False, "type": dict, "description": "Filing history"},
    "officers":           {"required": False, "type": list, "description": "Officers list"},
    "distress_signals":   {"required": False, "type": list, "description": "Distress signals"},
    "neighbourhood":      {"required": True,  "type": str,  "description": "Target neighbourhood"},
}

DELIVEROO_FIELDS = {
    "name":                    {"required": True,  "type": str,          "description": "Restaurant name"},
    "menu_items":              {"required": True,  "type": list,         "description": "Menu items"},
    "postcode":                {"required": False, "type": str,          "description": "Postcode"},
    "deliveroo_rating":        {"required": False, "type": (int, float), "description": "Deliveroo rating"},
    "delivery_fee":            {"required": False, "type": (int, float), "description": "Delivery fee"},
    "estimated_delivery_mins": {"required": False, "type": str,         "description": "Delivery time"},
    "neighbourhood":           {"required": True,  "type": str,         "description": "Target neighbourhood"},
}

DELIVEROO_MENU_FIELDS = {
    "name":         {"required": True,  "type": str,          "description": "Dish name"},
    "price":        {"required": True,  "type": (int, float), "description": "Price"},
    "category":     {"required": False, "type": str,          "description": "Menu section"},
    "description":  {"required": False, "type": str,          "description": "Dish description"},
    "dietary_tags": {"required": False, "type": list,         "description": "Dietary tags"},
}

ONS_CENSUS_FIELDS = {
    "neighbourhood":      {"required": True,  "type": str,          "description": "Target neighbourhood"},
    "total_population":   {"required": True,  "type": (int, float), "description": "Total population"},
}

LINEAGE_FIELDS = {
    "source":            {"required": True, "type": str, "description": "Source name"},
    "collected_at":      {"required": True, "type": str, "description": "Collection timestamp"},
    "collector_version": {"required": True, "type": str, "description": "Collector version"},
    "run_id":            {"required": True, "type": str, "description": "Run ID"},
}

SOURCES = [
    "google_places",
    "fsa",
    "companies_house",
    "deliveroo",
    "ons_census",
]


# ==================================================================
# Validation engine
# ==================================================================

class ValidationResult:
    def __init__(self, source: str, area: str):
        self.source = source
        self.area = area
        self.file_path = None
        self.record_count = 0
        self.errors = []
        self.warnings = []
        self.passes = []

    @property
    def passed(self):
        return len(self.errors) == 0

    def error(self, field, msg):
        self.errors.append(f"{field}: {msg}")

    def warn(self, field, msg):
        self.warnings.append(f"{field}: {msg}")

    def ok(self, field, msg):
        self.passes.append(f"{field}: {msg}")

    def summary_line(self):
        icon = "✓" if self.passed else "✗"
        warns = f" ({len(self.warnings)} warnings)" if self.warnings else ""
        return (f"  {icon} {self.source}/{self.area}: "
                f"{self.record_count} records, "
                f"{len(self.errors)} errors{warns}")


def load_latest_file(source: str, area_name: str):
    folder = RAW_DIR / source
    if not folder.exists():
        return None, None

    slug = area_name.lower().replace(" ", "_").replace("-", "_")
    files = sorted(
        [f for f in folder.glob(f"{slug}*.json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    if not files:
        return None, None

    filepath = files[0]
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    return filepath, data if isinstance(data, list) else [data]


def check_fields(record: dict, spec: dict, result: ValidationResult, prefix: str, verbose: bool):
    for field, meta in spec.items():
        value = record.get(field)
        empty = value is None or value == "" or value == []
        if empty:
            if meta["required"]:
                result.error(f"{prefix}.{field}", f"MISSING — {meta['description']}")
            elif verbose:
                result.warn(f"{prefix}.{field}", f"empty optional — {meta['description']}")
        elif not isinstance(value, meta["type"]):
            if meta["required"]:
                result.error(f"{prefix}.{field}", f"wrong type: got {type(value).__name__}")
        elif verbose:
            result.ok(f"{prefix}.{field}", meta["description"])


# ==================================================================
# Source validators
# ==================================================================

def validate_google_places(records, result, verbose):
    for i, rec in enumerate(records[:5]):
        check_fields(rec, GOOGLE_PLACES_FIELDS, result, f"record[{i}]", verbose)
        reviews = rec.get("reviews", [])
        if reviews:
            check_fields(reviews[0], GOOGLE_PLACES_REVIEW_FIELDS, result, f"record[{i}].review[0]", verbose)

    with_reviews = sum(1 for r in records if r.get("reviews"))
    with_coords = sum(1 for r in records if r.get("latitude") and r.get("longitude"))
    total_reviews = sum(len(r.get("reviews", [])) for r in records)

    status = "PASS" if with_reviews > 0 else "FAIL"
    result.warn("reviews", f"{with_reviews}/{len(records)} restaurants have reviews") if with_reviews < len(records) else result.ok("reviews", f"{with_reviews}/{len(records)} have reviews")
    result.ok("coordinates", f"{with_coords}/{len(records)} have coordinates")
    result.ok("total_reviews", f"{total_reviews} total reviews collected")


def validate_fsa(records, result, verbose):
    for i, rec in enumerate(records[:5]):
        check_fields(rec, FSA_FIELDS, result, f"record[{i}]", verbose)

    rated = sum(1 for r in records if r.get("rating_value") is not None)
    with_scores = sum(1 for r in records if r.get("score_hygiene") is not None)
    low_rated = sum(1 for r in records if isinstance(r.get("rating_value"), (int, float)) and r["rating_value"] < 4)

    result.ok("rated", f"{rated}/{len(records)} have hygiene rating")
    result.ok("sub_scores", f"{with_scores}/{len(records)} have hygiene sub-scores")
    result.ok("low_rated", f"{low_rated} establishments rated below 4")

    # Check no pubs
    types = set(r.get("business_type", "").lower() for r in records)
    if "pub/bar/nightclub" in types:
        result.warn("business_types", "pub/bar/nightclub still present — filter not applied")
    else:
        result.ok("business_types", "No pub/bar/nightclub records")


def validate_companies_house(records, result, verbose):
    for i, rec in enumerate(records[:5]):
        check_fields(rec, COMPANIES_HOUSE_FIELDS, result, f"record[{i}]", verbose)

    with_officers = sum(1 for r in records if r.get("officers"))
    with_filings = sum(1 for r in records if r.get("filing_summary", {}).get("recent_filings"))
    with_signals = sum(1 for r in records if r.get("distress_signals"))
    active = sum(1 for r in records if r.get("status") == "active")

    result.ok("officers", f"{with_officers}/{len(records)} have officer records")
    result.ok("filings", f"{with_filings}/{len(records)} have filing history")
    result.ok("distress", f"{with_signals}/{len(records)} have distress signals")
    result.ok("active", f"{active}/{len(records)} companies active")


def validate_deliveroo(records, result, verbose):
    for i, rec in enumerate(records[:5]):
        check_fields(rec, DELIVEROO_FIELDS, result, f"record[{i}]", verbose)
        items = rec.get("menu_items", [])
        if items:
            check_fields(items[0], DELIVEROO_MENU_FIELDS, result, f"record[{i}].menu[0]", verbose)

    with_menus = sum(1 for r in records if r.get("menu_items"))
    total_items = sum(len(r.get("menu_items", [])) for r in records)
    with_postcode = sum(1 for r in records if r.get("postcode"))
    with_fee = sum(1 for r in records if r.get("delivery_fee") is not None)

    result.ok("menus", f"{with_menus}/{len(records)} restaurants have menus")
    result.ok("menu_items", f"{total_items} total menu items")
    result.ok("postcodes", f"{with_postcode}/{len(records)} have postcodes")
    result.warn("delivery_fee", f"{with_fee}/{len(records)} have delivery fee") if with_fee == 0 else result.ok("delivery_fee", f"{with_fee}/{len(records)} have delivery fee")


def validate_ons_census(records, result, verbose):
    for i, rec in enumerate(records[:3]):
        check_fields(rec, ONS_CENSUS_FIELDS, result, f"record[{i}]", verbose)

    fields_present = [
        k for k in records[0].keys()
        if k not in ("neighbourhood", "_lineage")
    ] if records else []
    result.ok("fields", f"{len(fields_present)} data fields per record")
    result.ok("records", f"{len(records)} LSOA/area records")


def validate_lineage(records, result, verbose):
    with_lineage = sum(1 for r in records if "_lineage" in r)
    if with_lineage == 0:
        result.error("_lineage", "No records have lineage metadata")
        return
    if with_lineage < len(records):
        result.warn("_lineage", f"Only {with_lineage}/{len(records)} have lineage")
    else:
        result.ok("_lineage", f"All {len(records)} records have lineage")

    lineage = records[0].get("_lineage", {})
    check_fields(lineage, LINEAGE_FIELDS, result, "_lineage", verbose)


# ==================================================================
# Main runner
# ==================================================================

VALIDATORS = {
    "google_places": validate_google_places,
    "fsa": validate_fsa,
    "companies_house": validate_companies_house,
    "deliveroo": validate_deliveroo,
    "ons_census": validate_ons_census,
}


def run_validation(sources=None, areas=None, verbose=False):
    sources = sources or SOURCES
    areas = areas or TARGET_AREAS
    results = []

    for source in sources:
        for area in areas:
            result = ValidationResult(source, area["name"])
            filepath, records = load_latest_file(source, area["name"])

            if not filepath:
                result.error("_file", f"No data file found in {RAW_DIR / source}/")
                results.append(result)
                continue

            result.file_path = filepath
            result.record_count = len(records) if records else 0

            if not records:
                result.error("_data", "File is empty")
                results.append(result)
                continue

            VALIDATORS[source](records, result, verbose)
            validate_lineage(records, result, verbose)
            results.append(result)

    # Print report
    total_errors = sum(len(r.errors) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)
    total_records = sum(r.record_count for r in results)

    print(f"\n{'='*64}")
    print(f"  DATA COMPLETENESS REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*64}")
    print(f"  Status:   {'ALL CLEAR' if total_errors == 0 else 'ISSUES FOUND'}")
    print(f"  Records:  {total_records}")
    print(f"  Errors:   {total_errors}")
    print(f"  Warnings: {total_warnings}")
    print()

    for r in results:
        print(r.summary_line())
        if r.file_path:
            print(f"    File: {r.file_path.name}")
        for err in r.errors:
            print(f"    ✗ {err}")
        for warn in r.warnings:
            print(f"    ⚠ {warn}")
        if verbose:
            for ok in r.passes:
                print(f"    ✓ {ok}")
        print()

    print(f"{'='*64}\n")
    return total_errors == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate collected data")
    parser.add_argument("--source", "-s", choices=SOURCES)
    parser.add_argument("--area", "-a")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    sources = [args.source] if args.source else None
    areas = None
    if args.area:
        areas = [a for a in TARGET_AREAS if a["name"].lower() == args.area.lower()]
        if not areas:
            print(f"Area not found. Options: {[a['name'] for a in TARGET_AREAS]}")
            sys.exit(1)

    success = run_validation(sources=sources, areas=areas, verbose=args.verbose)
    sys.exit(0 if success else 1)