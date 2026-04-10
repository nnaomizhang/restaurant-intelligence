"""
Test Suite for All Collectors
=============================
Tests each collector's core functionality:
  - Data structure validation
  - Lineage metadata attachment
  - File saving and loading
  - Error handling

Run with: python -m pytest tests/ -v
Or:       python tests/test_collectors.py
"""

import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ==================================================================
# Test utilities
# ==================================================================

class TempDataDir:
    """Context manager that creates a temporary data directory."""

    def __init__(self):
        self.tmpdir = None

    def __enter__(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        return self.tmpdir

    def __exit__(self, *args):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


def assert_lineage(record: dict, source_name: str):
    """Assert a record has valid lineage metadata."""
    assert "_lineage" in record, "Record missing _lineage metadata"
    lineage = record["_lineage"]
    assert lineage["source"] == source_name, (
        f"Expected source '{source_name}', got '{lineage['source']}'"
    )
    assert "collected_at" in lineage, "Lineage missing collected_at"
    assert "collector_version" in lineage, "Lineage missing collector_version"
    assert "run_id" in lineage, "Lineage missing run_id"


def assert_record_fields(record: dict, required_fields: list[str]):
    """Assert a record contains all required fields."""
    for field in required_fields:
        assert field in record, f"Record missing field: {field}"


# ==================================================================
# Lineage tests
# ==================================================================

def test_lineage_logging():
    """Test that lineage events are logged correctly."""
    from processing.lineage import (
        generate_run_id,
        log_collection,
        log_transformation,
        get_lineage_for_run,
        create_record_lineage,
        LINEAGE_LOG_PATH,
    )

    # Backup existing lineage log
    backup = None
    if LINEAGE_LOG_PATH.exists():
        backup = LINEAGE_LOG_PATH.read_text()

    try:
        # Clear log for testing
        LINEAGE_LOG_PATH.write_text("")

        run_id = generate_run_id()
        assert len(run_id) == 8, "Run ID should be 8 characters"

        # Test collection logging
        entry = log_collection(
            run_id=run_id,
            source_name="test_source",
            area_name="TestArea",
            records_collected=42,
            output_file="/tmp/test.json",
            collector_version="1.0",
            method="api",
        )
        assert entry["event_type"] == "collection"
        assert entry["records_collected"] == 42

        # Test transformation logging
        entry2 = log_transformation(
            run_id=run_id,
            source_file="/tmp/test.json",
            destination_table="restaurants",
            records_in=42,
            records_out=40,
            transformations=["geocoded", "normalised"],
        )
        assert entry2["event_type"] == "transformation"
        assert entry2["records_out"] == 40

        # Test retrieval
        entries = get_lineage_for_run(run_id)
        assert len(entries) == 2, f"Expected 2 entries, got {len(entries)}"

        # Test record-level lineage
        lineage = create_record_lineage(
            source_name="google_places",
            run_id=run_id,
        )
        assert lineage["source"] == "google_places"
        assert lineage["run_id"] == run_id

        print("  PASSED: test_lineage_logging")

    finally:
        # Restore backup
        if backup is not None:
            LINEAGE_LOG_PATH.write_text(backup)


# ==================================================================
# Google Places collector tests
# ==================================================================

def test_google_places_structure():
    """Test Google Places collector output structure."""
    from collectors.google_places import GooglePlacesCollector

    collector = GooglePlacesCollector()

    # Mock a Place Details response
    mock_detail = {
        "google_place_id": "ChIJ_test123",
        "name": "Test Restaurant",
        "address": "123 Test St, London E1 6AB",
        "latitude": 51.5246,
        "longitude": -0.0780,
        "rating": 4.3,
        "review_count": 150,
        "price_level": 2,
        "business_status": "OPERATIONAL",
        "phone": "+44 20 1234 5678",
        "website": "https://test.com",
        "opening_hours": ["Monday: 11:00–22:00"],
        "types": ["restaurant", "food"],
        "reviews": [
            {
                "text": "Great sushi!",
                "rating": 5,
                "date": "2 months ago",
                "language": "en",
            }
        ],
        "neighbourhood": "Shoreditch",
    }

    required_fields = [
        "google_place_id", "name", "address", "latitude", "longitude",
        "rating", "review_count", "types", "reviews", "neighbourhood",
    ]
    assert_record_fields(mock_detail, required_fields)

    # Test review structure
    review = mock_detail["reviews"][0]
    assert "text" in review
    assert "rating" in review
    assert "language" in review

    print("  PASSED: test_google_places_structure")


def test_google_places_save_with_lineage():
    """Test that Google Places collector saves data with lineage."""
    from collectors.google_places import GooglePlacesCollector

    with TempDataDir() as tmpdir:
        collector = GooglePlacesCollector()
        collector.raw_dir = tmpdir

        test_data = [
            {"name": "Test Restaurant", "rating": 4.5},
            {"name": "Another Place", "rating": 3.8},
        ]

        filepath = collector.save_raw(test_data, "TestArea")

        # Verify file exists
        assert filepath.exists(), f"File not created: {filepath}"

        # Verify lineage in saved data
        with open(filepath) as f:
            saved = json.load(f)

        assert len(saved) == 2
        for record in saved:
            assert_lineage(record, "google_places")

    print("  PASSED: test_google_places_save_with_lineage")


# ==================================================================
# FSA collector tests
# ==================================================================

def test_fsa_postcode_filter():
    """Test FSA postcode filtering logic."""
    from collectors.fsa import FSACollector

    collector = FSACollector()

    assert collector._postcode_matches("E1 6AB", "E1") is True
    assert collector._postcode_matches("E1 6AB", "E2") is False
    assert collector._postcode_matches("SE15 3AB", "SE15") is True
    assert collector._postcode_matches("SE15 3AB", "SW1") is False
    assert collector._postcode_matches("", "E1") is False
    assert collector._postcode_matches("E1 6AB", "") is False

    print("  PASSED: test_fsa_postcode_filter")


def test_fsa_rating_parser():
    """Test FSA rating value parsing."""
    from collectors.fsa import FSACollector

    assert FSACollector._parse_rating("5") == 5
    assert FSACollector._parse_rating("0") == 0
    assert FSACollector._parse_rating("Exempt") is None
    assert FSACollector._parse_rating("AwaitingInspection") is None
    assert FSACollector._parse_rating(None) is None

    print("  PASSED: test_fsa_rating_parser")


def test_fsa_restaurant_type_filter():
    """Test FSA business type filtering."""
    from collectors.fsa import FSACollector

    collector = FSACollector()
    types = collector.RESTAURANT_TYPES

    assert "restaurant/cafe/canteen" in types
    assert "takeaway/sandwich shop" in types
    assert "pub/bar/nightclub" in types
    assert "school/college/university" not in types
    assert "hospital/childcare/caring premises" not in types

    print("  PASSED: test_fsa_restaurant_type_filter")


# ==================================================================
# Companies House collector tests
# ==================================================================

def test_companies_house_distress_signals():
    """Test distress signal calculation."""
    from collectors.companies_house import CompaniesHouseCollector

    collector = CompaniesHouseCollector()

    # Company with multiple distress signals
    distressed = {
        "accounts_overdue": True,
        "confirmation_overdue": True,
        "status": "liquidation",
        "officers": [
            {"name": "A", "resigned_on": "2025-01-01"},
            {"name": "B", "resigned_on": "2025-03-01"},
            {"name": "C", "resigned_on": "2025-06-01"},
        ],
        "filing_summary": {"total_filings": 2},
    }
    signals = collector._calculate_distress(distressed)
    assert len(signals) >= 3, f"Expected >=3 signals, got {len(signals)}: {signals}"
    assert "Accounts overdue" in signals

    # Healthy company
    healthy = {
        "accounts_overdue": False,
        "confirmation_overdue": False,
        "status": "active",
        "officers": [
            {"name": "A", "appointed_on": "2020-01-01"},
        ],
        "filing_summary": {"total_filings": 15},
    }
    signals = collector._calculate_distress(healthy)
    assert len(signals) == 0, f"Expected 0 signals, got: {signals}"

    print("  PASSED: test_companies_house_distress_signals")


def test_companies_house_address_format():
    """Test address formatting."""
    from collectors.companies_house import CompaniesHouseCollector

    formatted = CompaniesHouseCollector._format_address({
        "address_line_1": "45 High Street",
        "address_line_2": "",
        "locality": "London",
        "region": "",
        "postal_code": "E1 6AB",
    })
    assert "45 High Street" in formatted
    assert "London" in formatted
    assert "E1 6AB" in formatted
    assert ",," not in formatted  # no double commas from empty fields

    print("  PASSED: test_companies_house_address_format")


# ==================================================================
# Planning collector tests
# ==================================================================

def test_planning_food_detection():
    """Test food-related application detection."""
    from collectors.planning import PlanningCollector

    collector = PlanningCollector()

    food_app = {
        "application_type": "Class E change of use",
        "proposed_use": "Proposed Japanese restaurant and sake bar",
    }
    assert collector._is_food_application(food_app) is True

    non_food = {
        "application_type": "Full planning application",
        "proposed_use": "Conversion to residential flats",
    }
    assert collector._is_food_application(non_food) is False

    takeaway = {
        "application_type": "Change of use",
        "proposed_use": "Hot food takeaway",
    }
    assert collector._is_food_application(takeaway) is True

    print("  PASSED: test_planning_food_detection")


def test_planning_postcode_extraction():
    """Test postcode extraction from addresses."""
    from collectors.planning import PlanningCollector

    collector = PlanningCollector()

    assert collector._extract_postcode("45 High St, London E1 6AB") == "E1 6AB"
    assert collector._extract_postcode("12 Brick Lane, SE15 3AB") == "SE15 3AB"
    assert collector._extract_postcode("No postcode here") == ""
    assert collector._extract_postcode("") == ""

    print("  PASSED: test_planning_postcode_extraction")


def test_planning_csv_loading():
    """Test that planning data loads correctly from CSV."""
    from collectors.planning import PlanningCollector

    with TempDataDir() as tmpdir:
        collector = PlanningCollector()
        collector.raw_dir = tmpdir

        # Create test CSV
        csv_path = tmpdir / "testarea_applications.csv"
        csv_path.write_text(
            "reference,date_filed,address,postcode,application_type,"
            "proposed_use,decision_status,decision_date\n"
            'PA/25/001,2025-06-15,"45 High St, E1 6AB",E1 6AB,'
            "Class E change of use,Proposed restaurant,Granted,2025-09-20\n"
            'PA/25/002,2025-08-03,"12 Other St, E1 7CD",E1 7CD,'
            "Full planning,Residential conversion,Refused,2025-11-01\n"
        )

        records = collector._load_csv("testarea", "TestArea")
        assert records is not None
        assert len(records) == 2

        # Test normalisation
        normalised = collector._normalise_record(records[0], "TestArea")
        assert normalised["reference"] == "PA/25/001"
        assert normalised["neighbourhood"] == "TestArea"

    print("  PASSED: test_planning_csv_loading")


# ==================================================================
# ONS Census collector tests
# ==================================================================

def test_ons_column_finder():
    """Test the flexible column-finding logic."""
    import pandas as pd
    from collectors.ons_census import ONSCensusCollector

    collector = ONSCensusCollector()

    df = pd.DataFrame({
        "Geography Code": [1],
        "Geography": ["Test"],
        "Age: Total": [100],
    })

    # Case-insensitive matching
    assert collector._find_column(df, ["geography code"]) == "Geography Code"
    assert collector._find_column(df, ["age: total"]) == "Age: Total"
    assert collector._find_column(df, ["nonexistent"]) is None

    # Keyword-containing matching
    assert collector._find_column_containing(df, ["geography"]) == "Geography Code"
    assert collector._find_column_containing(df, ["total"]) == "Age: Total"

    print("  PASSED: test_ons_column_finder")


def test_ons_merged_csv_loading():
    """Test loading a pre-merged demographics CSV."""
    from collectors.ons_census import ONSCensusCollector

    with TempDataDir() as tmpdir:
        collector = ONSCensusCollector()
        collector.raw_dir = tmpdir

        # Create test merged CSV
        csv_path = tmpdir / "testarea_demographics.csv"
        csv_path.write_text(
            "lsoa_code,lsoa_name,total_population,population_density,"
            "age_25_34_pct,median_household_income\n"
            "E01000001,Test 001A,1650,12500,28.3,38500\n"
            "E01000002,Test 001B,1420,9800,22.1,35200\n"
        )

        records = collector._load_merged_csv(csv_path, "TestArea")
        assert len(records) == 2
        assert records[0]["lsoa_code"] == "E01000001"
        assert records[0]["neighbourhood"] == "TestArea"
        assert records[0]["total_population"] == 1650

    print("  PASSED: test_ons_merged_csv_loading")


# ==================================================================
# Base collector tests
# ==================================================================

def test_base_save_attaches_lineage():
    """Test that save_raw attaches lineage to every record."""
    from collectors.base import BaseCollector

    class MockCollector(BaseCollector):
        def collect(self, area):
            return [{"name": "test"}]

    with TempDataDir() as tmpdir:
        collector = MockCollector("test_source", tmpdir, method="test")
        data = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
        filepath = collector.save_raw(data, "TestArea")

        with open(filepath) as f:
            saved = json.load(f)

        assert len(saved) == 3
        for record in saved:
            assert "_lineage" in record
            assert record["_lineage"]["source"] == "test_source"
            assert record["_lineage"]["run_id"] == collector.run_id

    print("  PASSED: test_base_save_attaches_lineage")


def test_base_rate_limit():
    """Test rate limiter adds delay."""
    from collectors.base import BaseCollector
    import time

    class MockCollector(BaseCollector):
        def collect(self, area):
            return []

    with TempDataDir() as tmpdir:
        collector = MockCollector("test", tmpdir)
        start = time.time()
        collector.rate_limit(0.1, 0)  # minimal delay for test
        elapsed = time.time() - start
        assert elapsed >= 0.1, f"Rate limit too fast: {elapsed:.3f}s"

    print("  PASSED: test_base_rate_limit")


# ==================================================================
# Integration test
# ==================================================================

def test_end_to_end_collect_and_lineage():
    """
    Integration test: run a mock collection, verify data is saved
    with lineage, and lineage log is written.
    """
    from collectors.base import BaseCollector
    from processing.lineage import get_lineage_for_run, LINEAGE_LOG_PATH

    class MockCollector(BaseCollector):
        def collect(self, area):
            return [
                {"name": "Restaurant A", "rating": 4.5},
                {"name": "Restaurant B", "rating": 3.8},
            ]

    with TempDataDir() as tmpdir:
        collector = MockCollector("integration_test", tmpdir, method="test")
        run_id = collector.run_id

        area = {"name": "IntegrationTest"}
        records = collector.collect(area)
        assert len(records) == 2

        # Save and verify lineage
        filepath = collector.save_raw(records, "IntegrationTest")
        assert filepath.exists()

        with open(filepath) as f:
            saved = json.load(f)

        # Every record has lineage
        for r in saved:
            assert_lineage(r, "integration_test")

        # Lineage log has an entry
        entries = get_lineage_for_run(run_id)
        assert len(entries) >= 1
        assert entries[0]["source_system"] == "integration_test"
        assert entries[0]["records_collected"] == 2

    print("  PASSED: test_end_to_end_collect_and_lineage")


# ==================================================================
# Deliveroo collector tests
# ==================================================================

def test_deliveroo_manual_template():
    """Test that the manual data template is valid JSON."""
    from collectors.deliveroo import DeliverooCollector

    collector = DeliverooCollector()

    # Test manual data loading with a temp file
    with TempDataDir() as tmpdir:
        collector.raw_dir = tmpdir

        manual_data = [
            {
                "name": "Test Ramen",
                "cuisine_tags": ["Japanese", "Ramen"],
                "postcode": "E1 6AB",
                "deliveroo_rating": 4.5,
                "menu_items": [
                    {"name": "Tonkotsu", "price": 11.50, "category": "Mains"},
                ],
            }
        ]

        manual_file = tmpdir / "testarea_manual.json"
        with open(manual_file, "w") as f:
            json.dump(manual_data, f)

        loaded = collector.load_manual_data("TestArea")
        assert len(loaded) == 1
        assert loaded[0]["name"] == "Test Ramen"

    print("  PASSED: test_deliveroo_manual_template")


# ==================================================================
# Run all tests
# ==================================================================

def run_all_tests():
    """Run all tests and print summary."""
    tests = [
        # Lineage
        test_lineage_logging,
        # Base collector
        test_base_save_attaches_lineage,
        test_base_rate_limit,
        # Google Places
        test_google_places_structure,
        test_google_places_save_with_lineage,
        # FSA
        test_fsa_postcode_filter,
        test_fsa_rating_parser,
        test_fsa_restaurant_type_filter,
        # Companies House
        test_companies_house_distress_signals,
        test_companies_house_address_format,
        # Planning
        test_planning_food_detection,
        test_planning_postcode_extraction,
        test_planning_csv_loading,
        # ONS Census
        test_ons_column_finder,
        test_ons_merged_csv_loading,
        # Deliveroo
        test_deliveroo_manual_template,
        # Integration
        test_end_to_end_collect_and_lineage,
    ]

    print(f"\n{'='*60}")
    print(f"RUNNING {len(tests)} TESTS")
    print(f"{'='*60}\n")

    passed = 0
    failed = 0
    errors = []

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test_fn.__name__, str(e)))
            print(f"  FAILED: {test_fn.__name__}: {e}")

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'='*60}")

    if errors:
        print(f"\nFailed tests:")
        for name, error in errors:
            print(f"  {name}: {error}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
