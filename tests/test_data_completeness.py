"""
Data Completeness Validator
============================
Validates that collected raw data files contain ALL required fields
from the data collection checklist (52 data points across 6 sources).

Run AFTER collection to verify data quality before processing.

Usage:
  python tests/test_data_completeness.py                    # Check all sources
  python tests/test_data_completeness.py --source deliveroo # Check one source
  python tests/test_data_completeness.py --area Shoreditch  # Check one area
  python tests/test_data_completeness.py --verbose          # Show every field check
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
# Required field definitions (maps to the 52-point checklist)
# ==================================================================

DELIVEROO_RESTAURANT_FIELDS = {
    "name":                    {"required": True,  "type": str,   "description": "Restaurant name"},
    "cuisine_tags":            {"required": True,  "type": list,  "description": "Cuisine type / category tags"},
    "address":                 {"required": False, "type": str,   "description": "Full address"},
    "postcode":                {"required": False, "type": str,   "description": "Postcode for geocoding"},
    "deliveroo_rating":        {"required": False, "type": (int, float), "description": "Deliveroo star rating"},
    "delivery_fee":            {"required": False, "type": (int, float), "description": "Delivery fee"},
    "min_order":               {"required": False, "type": (int, float), "description": "Minimum order value"},
    "estimated_delivery_mins": {"required": False, "type": str,   "description": "Estimated delivery time"},
    "operating_hours":         {"required": False, "type": str,   "description": "Operating hours on platform"},
    "menu_items":              {"required": True,  "type": list,  "description": "Full menu item list"},
}

DELIVEROO_MENU_ITEM_FIELDS = {
    "name":         {"required": True,  "type": str,           "description": "Dish name"},
    "price":        {"required": True,  "type": (int, float),  "description": "Price per item"},
    "category":     {"required": False, "type": str,           "description": "Menu section (Starters, Mains, etc.)"},
    "description":  {"required": False, "type": str,           "description": "Dish description"},
    "is_popular":   {"required": False, "type": bool,          "description": "Popular/Top rated badge"},
    "dietary_tags": {"required": False, "type": list,          "description": "Dietary tags (vegan, GF, halal)"},
}

GOOGLE_PLACES_RESTAURANT_FIELDS = {
    "google_place_id": {"required": True,  "type": str,           "description": "Google Place ID (foreign key)"},
    "name":            {"required": True,  "type": str,           "description": "Business name"},
    "address":         {"required": True,  "type": str,           "description": "Full formatted address"},
    "latitude":        {"required": True,  "type": (int, float),  "description": "Latitude coordinate"},
    "longitude":       {"required": True,  "type": (int, float),  "description": "Longitude coordinate"},
    "rating":          {"required": False, "type": (int, float),  "description": "Google star rating"},
    "review_count":    {"required": False, "type": int,           "description": "Total review count"},
    "price_level":     {"required": False, "type": int,           "description": "Price level (1-4)"},
    "opening_hours":   {"required": False, "type": list,          "description": "Weekly opening hours"},
    "types":           {"required": False, "type": list,          "description": "Business type / category"},
    "reviews":         {"required": True,  "type": list,          "description": "Review list"},
}

GOOGLE_PLACES_REVIEW_FIELDS = {
    "text":     {"required": True,  "type": str,          "description": "Review full body text"},
    "rating":   {"required": True,  "type": (int, float), "description": "Star rating per review"},
    "date":     {"required": False, "type": str,          "description": "Review date / relative time"},
    "language": {"required": False, "type": str,          "description": "Review language code"},
}

FSA_FIELDS = {
    "fsa_id":            {"required": False, "type": str,          "description": "FSA establishment ID"},
    "business_name":     {"required": True,  "type": str,          "description": "Business name"},
    "address":           {"required": True,  "type": str,          "description": "Full address"},
    "postcode":          {"required": True,  "type": str,          "description": "Postcode"},
    "rating_value":      {"required": True,  "type": (int, float), "description": "Hygiene rating (0-5)"},
    "rating_date":       {"required": False, "type": str,          "description": "Inspection date"},
    "local_authority":   {"required": False, "type": str,          "description": "Local authority name"},
    "business_type":     {"required": False, "type": str,          "description": "FSA business category"},
    "score_hygiene":     {"required": False, "type": (str, int),   "description": "Hygiene sub-score"},
    "score_structural":  {"required": False, "type": (str, int),   "description": "Structural sub-score"},
    "score_management":  {"required": False, "type": (str, int),   "description": "Management sub-score"},
}

COMPANIES_HOUSE_FIELDS = {
    "company_number":      {"required": True,  "type": str,  "description": "Company registration number"},
    "company_name":        {"required": True,  "type": str,  "description": "Registered company name"},
    "registered_address":  {"required": False, "type": str,  "description": "Registered office address"},
    "status":              {"required": True,  "type": str,  "description": "Company status (active/dissolved/etc.)"},
    "incorporation_date":  {"required": False, "type": str,  "description": "Date of incorporation"},
    "sic_codes":           {"required": False, "type": list, "description": "SIC codes"},
    "accounts_overdue":    {"required": False, "type": bool, "description": "Accounts overdue flag"},
    "filing_summary":      {"required": False, "type": dict, "description": "Filing history summary"},
    "officers":            {"required": False, "type": list, "description": "Officers list with dates"},
    "distress_signals":    {"required": False, "type": list, "description": "Calculated distress signals"},
}

PLANNING_FIELDS = {
    "reference":        {"required": True,  "type": str, "description": "Application reference number"},
    "date_filed":       {"required": True,  "type": str, "description": "Date application filed"},
    "address":          {"required": True,  "type": str, "description": "Site address"},
    "postcode":         {"required": False, "type": str, "description": "Site postcode"},
    "application_type": {"required": False, "type": str, "description": "Application type (Class E, etc.)"},
    "proposed_use":     {"required": True,  "type": str, "description": "Proposed use description"},
    "decision_status":  {"required": True,  "type": str, "description": "Decision (granted/refused/pending)"},
    "decision_date":    {"required": False, "type": str, "description": "Decision date"},
}

ONS_CENSUS_FIELDS = {
    "lsoa_code":                {"required": True,  "type": str,           "description": "LSOA geographic code"},
    "lsoa_name":                {"required": False, "type": str,           "description": "LSOA name"},
    "total_population":         {"required": True,  "type": (int, float),  "description": "Total population"},
    "population_density":       {"required": False, "type": (int, float),  "description": "People per sq km"},
    "age_18_24_pct":            {"required": False, "type": (int, float),  "description": "Age 18-24 percentage"},
    "age_25_34_pct":            {"required": False, "type": (int, float),  "description": "Age 25-34 percentage"},
    "age_35_49_pct":            {"required": False, "type": (int, float),  "description": "Age 35-49 percentage"},
    "age_50_64_pct":            {"required": False, "type": (int, float),  "description": "Age 50-64 percentage"},
    "age_65_plus_pct":          {"required": False, "type": (int, float),  "description": "Age 65+ percentage"},
    "median_household_income":  {"required": False, "type": (int, float),  "description": "Median household income"},
    "ethnicity_white_pct":      {"required": False, "type": (int, float),  "description": "White ethnicity %"},
    "ethnicity_asian_pct":      {"required": False, "type": (int, float),  "description": "Asian ethnicity %"},
    "ethnicity_black_pct":      {"required": False, "type": (int, float),  "description": "Black ethnicity %"},
    "ethnicity_mixed_pct":      {"required": False, "type": (int, float),  "description": "Mixed ethnicity %"},
    "ethnicity_other_pct":      {"required": False, "type": (int, float),  "description": "Other ethnicity %"},
    "economically_active_pct":  {"required": False, "type": (int, float),  "description": "Economically active %"},
    "employment_office_pct":    {"required": False, "type": (int, float),  "description": "Office employment %"},
    "household_single_pct":     {"required": False, "type": (int, float),  "description": "Single-person households %"},
    "household_family_pct":     {"required": False, "type": (int, float),  "description": "Family households %"},
}

LINEAGE_FIELDS = {
    "source":            {"required": True, "type": str, "description": "Source system name"},
    "collected_at":      {"required": True, "type": str, "description": "Collection timestamp"},
    "collector_version": {"required": True, "type": str, "description": "Collector version"},
    "run_id":            {"required": True, "type": str, "description": "Collection run ID"},
}


# ==================================================================
# Validation engine
# ==================================================================

class ValidationResult:
    """Holds results for one validation check."""

    def __init__(self, source: str, area: str):
        self.source = source
        self.area = area
        self.file_path = None
        self.record_count = 0
        self.checks = []  # list of (field, status, message)
        self.errors = []
        self.warnings = []

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def add_check(self, field: str, status: str, message: str):
        self.checks.append((field, status, message))
        if status == "FAIL":
            self.errors.append(f"{field}: {message}")
        elif status == "WARN":
            self.warnings.append(f"{field}: {message}")

    def summary_line(self) -> str:
        icon = "✓" if self.passed else "✗"
        warns = f" ({len(self.warnings)} warnings)" if self.warnings else ""
        return (f"  {icon} {self.source}/{self.area}: "
                f"{self.record_count} records, "
                f"{len(self.errors)} errors{warns}")


def find_data_files(source: str, area_name: str) -> list[Path]:
    """Find all raw data files for a source/area combination."""
    source_dir = RAW_DIR / source
    if not source_dir.exists():
        return []

    slug = area_name.lower().replace(" ", "_").replace("-", "_")
    files = []

    # JSON files (timestamped or manual)
    for f in source_dir.glob(f"{slug}*.json"):
        files.append(f)

    # CSV files
    for f in source_dir.glob(f"{slug}*.csv"):
        files.append(f)

    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def load_records(filepath: Path) -> list[dict]:
    """Load records from a JSON or CSV file."""
    if filepath.suffix == ".json":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    elif filepath.suffix == ".csv":
        with open(filepath, "r", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    return []


def validate_fields(
    record: dict,
    field_spec: dict,
    record_label: str = "record",
) -> list[tuple[str, str, str]]:
    """
    Validate a single record against a field specification.
    Returns list of (field_name, status, message) tuples.
    """
    checks = []

    for field_name, spec in field_spec.items():
        required = spec["required"]
        expected_type = spec["type"]
        desc = spec["description"]

        value = record.get(field_name)

        if value is None or value == "" or value == []:
            if required:
                checks.append((
                    field_name, "FAIL",
                    f"MISSING required field — {desc}"
                ))
            else:
                checks.append((
                    field_name, "WARN",
                    f"Empty optional field — {desc}"
                ))
        elif not isinstance(value, expected_type):
            # Allow None for non-required fields with wrong type
            if required:
                checks.append((
                    field_name, "FAIL",
                    f"Wrong type: expected {expected_type.__name__ if isinstance(expected_type, type) else expected_type}, "
                    f"got {type(value).__name__} — {desc}"
                ))
            else:
                checks.append((
                    field_name, "WARN",
                    f"Unexpected type: {type(value).__name__} — {desc}"
                ))
        else:
            checks.append((field_name, "PASS", desc))

    return checks


def validate_source(
    source: str,
    area: dict,
    verbose: bool = False,
) -> ValidationResult:
    """Validate all collected data for one source/area pair."""
    area_name = area["name"]
    result = ValidationResult(source, area_name)

    # Find data files
    files = find_data_files(source, area_name)
    if not files:
        result.add_check("_file", "FAIL", f"No data files found in {RAW_DIR / source}/")
        return result

    # Use most recent file
    filepath = files[0]
    result.file_path = filepath

    # Load records
    try:
        records = load_records(filepath)
    except Exception as e:
        result.add_check("_file", "FAIL", f"Cannot read {filepath}: {e}")
        return result

    result.record_count = len(records)
    if not records:
        result.add_check("_data", "FAIL", "File contains 0 records")
        return result

    # Select field spec and validation approach based on source
    if source == "deliveroo":
        _validate_deliveroo(records, result, verbose)
    elif source == "google_places":
        _validate_google_places(records, result, verbose)
    elif source == "fsa":
        _validate_fsa(records, result, verbose)
    elif source == "companies_house":
        _validate_companies_house(records, result, verbose)
    elif source == "planning":
        _validate_planning(records, result, verbose)
    elif source == "ons_census":
        _validate_ons_census(records, result, verbose)

    # Check lineage on all sources
    _validate_lineage(records, result, verbose)

    return result


# ==================================================================
# Source-specific validators
# ==================================================================

def _validate_deliveroo(records, result, verbose):
    """Validate Deliveroo collected data."""
    # Check restaurant-level fields on a sample
    sample = records[:5]
    for i, rec in enumerate(sample):
        checks = validate_fields(rec, DELIVEROO_RESTAURANT_FIELDS, f"restaurant[{i}]")
        for field, status, msg in checks:
            if status != "PASS" or verbose:
                result.add_check(f"restaurant[{i}].{field}", status, msg)

    # Check menu items exist and have required fields
    total_items = 0
    restaurants_with_menus = 0
    popular_count = 0
    dietary_count = 0

    for rec in records:
        items = rec.get("menu_items", [])
        if items:
            restaurants_with_menus += 1
            total_items += len(items)

            # Validate first 3 menu items per restaurant
            for j, item in enumerate(items[:3]):
                checks = validate_fields(item, DELIVEROO_MENU_ITEM_FIELDS)
                for field, status, msg in checks:
                    if status == "FAIL":
                        result.add_check(
                            f"{rec.get('name', '?')}.menu[{j}].{field}",
                            status, msg,
                        )

            # Count quality signals
            for item in items:
                if item.get("is_popular"):
                    popular_count += 1
                if item.get("dietary_tags"):
                    dietary_count += 1

    # Summary checks
    if restaurants_with_menus == 0:
        result.add_check("menu_coverage", "FAIL", "No restaurants have menu items")
    else:
        pct = restaurants_with_menus / len(records) * 100
        status = "PASS" if pct >= 50 else "WARN"
        result.add_check(
            "menu_coverage", status,
            f"{restaurants_with_menus}/{len(records)} restaurants have menus ({pct:.0f}%)"
        )

    result.add_check(
        "total_menu_items", "PASS" if total_items > 0 else "FAIL",
        f"{total_items} total menu items across all restaurants"
    )
    result.add_check(
        "popular_badges", "PASS" if popular_count > 0 else "WARN",
        f"{popular_count} items flagged as popular"
    )
    result.add_check(
        "dietary_tags", "PASS" if dietary_count > 0 else "WARN",
        f"{dietary_count} items have dietary tags"
    )


def _validate_google_places(records, result, verbose):
    """Validate Google Places collected data."""
    sample = records[:5]
    for i, rec in enumerate(sample):
        checks = validate_fields(rec, GOOGLE_PLACES_RESTAURANT_FIELDS)
        for field, status, msg in checks:
            if status != "PASS" or verbose:
                result.add_check(f"restaurant[{i}].{field}", status, msg)

    # Check reviews
    total_reviews = 0
    restaurants_with_reviews = 0

    for rec in records:
        reviews = rec.get("reviews", [])
        if reviews:
            restaurants_with_reviews += 1
            total_reviews += len(reviews)

            # Validate first review
            checks = validate_fields(reviews[0], GOOGLE_PLACES_REVIEW_FIELDS)
            for field, status, msg in checks:
                if status == "FAIL":
                    result.add_check(
                        f"{rec.get('name', '?')}.review[0].{field}",
                        status, msg,
                    )

    result.add_check(
        "review_coverage",
        "PASS" if restaurants_with_reviews > 0 else "FAIL",
        f"{restaurants_with_reviews}/{len(records)} restaurants have reviews"
    )
    result.add_check(
        "total_reviews",
        "PASS" if total_reviews >= 10 else "WARN",
        f"{total_reviews} total reviews (target: 500+ for good RAG corpus)"
    )

    # Check coordinates coverage
    with_coords = sum(
        1 for r in records
        if r.get("latitude") is not None and r.get("longitude") is not None
    )
    result.add_check(
        "geocoding_coverage",
        "PASS" if with_coords == len(records) else "WARN",
        f"{with_coords}/{len(records)} restaurants have coordinates"
    )


def _validate_fsa(records, result, verbose):
    """Validate FSA collected data."""
    sample = records[:5]
    for i, rec in enumerate(sample):
        checks = validate_fields(rec, FSA_FIELDS)
        for field, status, msg in checks:
            if status != "PASS" or verbose:
                result.add_check(f"establishment[{i}].{field}", status, msg)

    # Check rating distribution
    rated = [r for r in records if r.get("rating_value") is not None]
    low_rated = [r for r in rated if isinstance(r["rating_value"], (int, float)) and r["rating_value"] < 4]

    result.add_check(
        "rated_establishments",
        "PASS" if len(rated) > 0 else "FAIL",
        f"{len(rated)}/{len(records)} have a numeric rating"
    )
    result.add_check(
        "low_ratings_found",
        "PASS" if low_rated else "WARN",
        f"{len(low_rated)} with rating < 4 (useful for distress detection)"
    )

    # Check sub-scores
    with_scores = sum(
        1 for r in records
        if r.get("score_hygiene") is not None
    )
    result.add_check(
        "sub_score_coverage",
        "PASS" if with_scores > 0 else "WARN",
        f"{with_scores}/{len(records)} have hygiene sub-scores"
    )


def _validate_companies_house(records, result, verbose):
    """Validate Companies House collected data."""
    sample = records[:5]
    for i, rec in enumerate(sample):
        checks = validate_fields(rec, COMPANIES_HOUSE_FIELDS)
        for field, status, msg in checks:
            if status != "PASS" or verbose:
                result.add_check(f"company[{i}].{field}", status, msg)

    # Check distress signal detection
    with_signals = [r for r in records if r.get("distress_signals")]
    result.add_check(
        "distress_detection",
        "PASS",
        f"{len(with_signals)}/{len(records)} companies have distress signals"
    )

    # Check officer data
    with_officers = sum(1 for r in records if r.get("officers"))
    result.add_check(
        "officer_data",
        "PASS" if with_officers > 0 else "WARN",
        f"{with_officers}/{len(records)} have officer records"
    )

    # Check filing history
    with_filings = sum(1 for r in records if r.get("filing_summary", {}).get("recent_filings"))
    result.add_check(
        "filing_history",
        "PASS" if with_filings > 0 else "WARN",
        f"{with_filings}/{len(records)} have filing history"
    )


def _validate_planning(records, result, verbose):
    """Validate planning application data."""
    sample = records[:5]
    for i, rec in enumerate(sample):
        checks = validate_fields(rec, PLANNING_FIELDS)
        for field, status, msg in checks:
            if status != "PASS" or verbose:
                result.add_check(f"application[{i}].{field}", status, msg)

    # Check decision status distribution
    statuses = {}
    for r in records:
        s = (r.get("decision_status") or "unknown").lower().strip()
        statuses[s] = statuses.get(s, 0) + 1

    result.add_check(
        "decision_distribution",
        "PASS",
        f"Statuses: {dict(statuses)}"
    )

    # Check proposed use descriptions are meaningful
    with_description = sum(
        1 for r in records
        if r.get("proposed_use") and len(r["proposed_use"]) > 10
    )
    result.add_check(
        "description_quality",
        "PASS" if with_description == len(records) else "WARN",
        f"{with_description}/{len(records)} have meaningful proposed use descriptions"
    )


def _validate_ons_census(records, result, verbose):
    """Validate ONS census demographic data."""
    sample = records[:3]
    for i, rec in enumerate(sample):
        checks = validate_fields(rec, ONS_CENSUS_FIELDS)
        for field, status, msg in checks:
            if status != "PASS" or verbose:
                result.add_check(f"lsoa[{i}].{field}", status, msg)

    # Check demographic completeness
    dimensions_present = set()
    dimension_checks = {
        "age_data": ["age_18_24_pct", "age_25_34_pct", "age_35_49_pct"],
        "ethnicity_data": ["ethnicity_white_pct", "ethnicity_asian_pct"],
        "economic_data": ["economically_active_pct"],
        "household_data": ["household_single_pct", "household_family_pct"],
        "income_data": ["median_household_income"],
    }

    for dim_name, fields in dimension_checks.items():
        has_data = any(
            records[0].get(f) is not None
            for f in fields
        ) if records else False

        if has_data:
            dimensions_present.add(dim_name)
            result.add_check(dim_name, "PASS", f"Present in data")
        else:
            result.add_check(dim_name, "WARN", f"Missing — download this census table")

    result.add_check(
        "demographic_dimensions",
        "PASS" if len(dimensions_present) >= 3 else "WARN",
        f"{len(dimensions_present)}/5 demographic dimensions present"
    )


def _validate_lineage(records, result, verbose):
    """Validate lineage metadata is present on records."""
    with_lineage = sum(1 for r in records if "_lineage" in r)

    if with_lineage == 0:
        result.add_check(
            "_lineage", "FAIL",
            "No records have lineage metadata — re-collect using the collectors"
        )
        return

    if with_lineage < len(records):
        result.add_check(
            "_lineage", "WARN",
            f"Only {with_lineage}/{len(records)} records have lineage metadata"
        )
    else:
        result.add_check("_lineage", "PASS", "All records have lineage metadata")

    # Validate lineage fields on first record
    lineage = records[0].get("_lineage", {})
    checks = validate_fields(lineage, LINEAGE_FIELDS)
    for field, status, msg in checks:
        if status != "PASS" or verbose:
            result.add_check(f"_lineage.{field}", status, msg)


# ==================================================================
# Report printer
# ==================================================================

def print_report(results: list[ValidationResult]):
    """Print a formatted validation report."""
    total_errors = sum(len(r.errors) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)
    total_records = sum(r.record_count for r in results)

    print(f"\n{'='*64}")
    print(f"  DATA COMPLETENESS VALIDATION REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*64}\n")

    # Overall summary
    icon = "✓ ALL CLEAR" if total_errors == 0 else "✗ ISSUES FOUND"
    print(f"  Status:   {icon}")
    print(f"  Records:  {total_records}")
    print(f"  Errors:   {total_errors}")
    print(f"  Warnings: {total_warnings}")
    print()

    # Per-source results
    for r in results:
        print(r.summary_line())

        if r.file_path:
            print(f"    File: {r.file_path}")

        # Print errors
        for err in r.errors:
            print(f"    ✗ {err}")

        # Print warnings (indented further)
        for warn in r.warnings:
            print(f"    ⚠ {warn}")

        if not r.errors and not r.warnings:
            print(f"    All fields present and valid")

        print()

    # Checklist summary per source
    print(f"{'─'*64}")
    print(f"  CHECKLIST COVERAGE SUMMARY")
    print(f"{'─'*64}")

    source_specs = {
        "deliveroo": (DELIVEROO_RESTAURANT_FIELDS, DELIVEROO_MENU_ITEM_FIELDS),
        "google_places": (GOOGLE_PLACES_RESTAURANT_FIELDS, GOOGLE_PLACES_REVIEW_FIELDS),
        "fsa": (FSA_FIELDS, None),
        "companies_house": (COMPANIES_HOUSE_FIELDS, None),
        "planning": (PLANNING_FIELDS, None),
        "ons_census": (ONS_CENSUS_FIELDS, None),
    }

    total_fields = 0
    for source, specs in source_specs.items():
        count = len(specs[0])
        if specs[1]:
            count += len(specs[1])
        total_fields += count
        print(f"  {source:<20} {count:>2} fields defined")

    print(f"  {'─'*35}")
    print(f"  {'Total':<20} {total_fields:>2} fields across all sources")
    print(f"{'='*64}\n")


# ==================================================================
# Main runner
# ==================================================================

SOURCES = [
    "deliveroo", "google_places", "fsa",
    "companies_house", "planning", "ons_census",
]


def run_validation(
    sources: list[str] = None,
    areas: list[dict] = None,
    verbose: bool = False,
) -> bool:
    """Run validation for specified sources and areas. Returns True if all pass."""
    sources = sources or SOURCES
    areas = areas or TARGET_AREAS

    results = []
    for source in sources:
        for area in areas:
            result = validate_source(source, area, verbose)
            results.append(result)

    print_report(results)

    return all(r.passed for r in results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate collected data completeness"
    )
    parser.add_argument(
        "--source", "-s",
        choices=SOURCES,
        help="Validate only this source",
    )
    parser.add_argument(
        "--area", "-a",
        help="Validate only this area (e.g. 'Shoreditch')",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show all field checks, not just failures",
    )

    args = parser.parse_args()

    sources = [args.source] if args.source else None

    areas = None
    if args.area:
        areas = [a for a in TARGET_AREAS if a["name"].lower() == args.area.lower()]
        if not areas:
            print(f"Area not found. Available: {[a['name'] for a in TARGET_AREAS]}")
            sys.exit(1)

    success = run_validation(sources=sources, areas=areas, verbose=args.verbose)
    sys.exit(0 if success else 1)
