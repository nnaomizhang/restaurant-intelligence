"""
Test Suite for All Collectors
==============================
Run with: pytest tests/test_collectors.py -v
"""

import json
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ==================================================================
# Test utilities
# ==================================================================

class TempDataDir:
    def __enter__(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        return self.tmpdir

    def __exit__(self, *args):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


def assert_lineage(record: dict, source_name: str):
    assert "_lineage" in record, "Record missing _lineage"
    lineage = record["_lineage"]
    assert lineage["source"] == source_name
    assert "collected_at" in lineage
    assert "collector_version" in lineage
    assert "run_id" in lineage


def assert_record_fields(record: dict, required_fields: list):
    for field in required_fields:
        assert field in record, f"Record missing field: {field}"


# ==================================================================
# Lineage tests
# ==================================================================

def test_generate_run_id():
    from processing.lineage import generate_run_id
    run_id = generate_run_id()
    assert len(run_id) == 8


def test_log_collection():
    from processing.lineage import generate_run_id, log_collection, get_lineage_for_run
    run_id = generate_run_id()
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
    assert entry["source_system"] == "test_source"


def test_log_transformation():
    from processing.lineage import generate_run_id, log_transformation
    run_id = generate_run_id()
    entry = log_transformation(
        run_id=run_id,
        source_file="/tmp/test.json",
        destination_table="restaurants",
        records_in=42,
        records_out=40,
        transformations=["normalised", "geocoded"],
    )
    assert entry["event_type"] == "transformation"
    assert entry["records_out"] == 40


def test_create_record_lineage():
    from processing.lineage import create_record_lineage
    lineage = create_record_lineage(
        source_name="google_places",
        run_id="abc12345",
    )
    assert lineage["source"] == "google_places"
    assert lineage["run_id"] == "abc12345"


def test_get_lineage_for_run():
    from processing.lineage import generate_run_id, log_collection, get_lineage_for_run
    run_id = generate_run_id()
    log_collection(
        run_id=run_id,
        source_name="test",
        area_name="Test",
        records_collected=10,
        output_file="/tmp/test.json",
        collector_version="1.0",
        method="api",
    )
    entries = get_lineage_for_run(run_id)
    assert len(entries) >= 1
    assert entries[0]["run_id"] == run_id


# ==================================================================
# Base collector tests
# ==================================================================

def test_base_save_attaches_lineage():
    from collectors.base import BaseCollector

    class MockCollector(BaseCollector):
        def collect(self, area):
            return [{"name": "test"}]

    with TempDataDir() as tmpdir:
        collector = MockCollector("test_source", tmpdir, method="test")
        data = [{"name": "A"}, {"name": "B"}]
        filepath = collector.save_raw(data, "TestArea")

        with open(filepath) as f:
            saved = json.load(f)

        assert len(saved) == 2
        for record in saved:
            assert_lineage(record, "test_source")


def test_base_rate_limit():
    from collectors.base import BaseCollector
    import time

    class MockCollector(BaseCollector):
        def collect(self, area):
            return []

    with TempDataDir() as tmpdir:
        collector = MockCollector("test", tmpdir)
        start = time.time()
        collector.rate_limit(0.1, 0)
        elapsed = time.time() - start
        assert elapsed >= 0.1


# ==================================================================
# Google Places tests
# ==================================================================

def test_google_places_structure():
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
        "opening_hours": ["Monday: 11:00-22:00"],
        "types": ["restaurant", "food"],
        "reviews": [{"text": "Great food!", "rating": 5, "language": "en"}],
        "neighbourhood": "Shoreditch",
    }
    required_fields = [
        "google_place_id", "name", "address", "latitude",
        "longitude", "rating", "review_count", "types",
        "reviews", "neighbourhood",
    ]
    assert_record_fields(mock_detail, required_fields)
    assert "text" in mock_detail["reviews"][0]
    assert "rating" in mock_detail["reviews"][0]


def test_google_places_save_with_lineage():
    from collectors.google_places import GooglePlacesCollector

    with TempDataDir() as tmpdir:
        collector = GooglePlacesCollector()
        collector.raw_dir = tmpdir

        data = [
            {"name": "Test Restaurant", "rating": 4.5},
            {"name": "Another Place", "rating": 3.8},
        ]
        filepath = collector.save_raw(data, "TestArea")

        with open(filepath) as f:
            saved = json.load(f)

        assert len(saved) == 2
        for record in saved:
            assert_lineage(record, "google_places")


# ==================================================================
# FSA tests
# ==================================================================

def test_fsa_postcode_filter():
    from collectors.fsa import FSACollector
    collector = FSACollector()

    assert collector._postcode_matches("E1 6AB", "E1") is True
    assert collector._postcode_matches("E1 6AB", "E2") is False
    assert collector._postcode_matches("SE15 3AB", "SE15") is True
    assert collector._postcode_matches("SE15 3AB", "SW1") is False
    assert collector._postcode_matches("", "E1") is False
    assert collector._postcode_matches("E1 6AB", "") is False


def test_fsa_rating_parser():
    from collectors.fsa import FSACollector

    assert FSACollector._parse_rating("5") == 5
    assert FSACollector._parse_rating("0") == 0
    assert FSACollector._parse_rating("Exempt") is None
    assert FSACollector._parse_rating("AwaitingInspection") is None
    assert FSACollector._parse_rating(None) is None


def test_fsa_restaurant_types():
    from collectors.fsa import FSACollector
    collector = FSACollector()

    assert "restaurant/cafe/canteen" in collector.RESTAURANT_TYPES
    assert "takeaway/sandwich shop" in collector.RESTAURANT_TYPES
    assert "pub/bar/nightclub" not in collector.RESTAURANT_TYPES


# ==================================================================
# Companies House tests
# ==================================================================

def test_companies_house_distress_signals():
    from collectors.companies_house import CompaniesHouseCollector
    collector = CompaniesHouseCollector()

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
    assert len(signals) >= 3
    assert "Accounts overdue" in signals

    healthy = {
        "accounts_overdue": False,
        "confirmation_overdue": False,
        "status": "active",
        "officers": [{"name": "A", "appointed_on": "2020-01-01"}],
        "filing_summary": {"total_filings": 15},
    }
    signals = collector._calculate_distress(healthy)
    assert len(signals) == 0


def test_companies_house_format_address():
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
    assert ",," not in formatted


# ==================================================================
# Deliveroo tests
# ==================================================================

def test_deliveroo_is_restaurant_listing():
    from collectors.deliveroo import DeliverooCollector
    collector = DeliverooCollector()

    assert collector._is_restaurant_listing({"name": "Dishoom", "url": "/menu/london/shoreditch/dishoom"}) is True
    assert collector._is_restaurant_listing({"name": "Tesco", "url": "/menu/london/tesco"}) is False
    assert collector._is_restaurant_listing({"name": "Co-op", "url": "/menu/london/coop"}) is False


def test_deliveroo_valid_url():
    from collectors.deliveroo import DeliverooCollector
    collector = DeliverooCollector()

    assert collector._looks_like_valid_restaurant_url("https://deliveroo.co.uk/menu/london/shoreditch/dishoom") is True
    assert collector._looks_like_valid_restaurant_url("https://deliveroo.co.uk/menu/london/groceries/tesco") is False


def test_deliveroo_manual_loading():
    from collectors.deliveroo import DeliverooCollector

    with TempDataDir() as tmpdir:
        collector = DeliverooCollector()
        collector.raw_dir = tmpdir

        manual_data = [{"name": "Test Ramen", "menu_items": [{"name": "Tonkotsu", "price": 11.50}]}]
        manual_file = tmpdir / "testarea_manual.json"
        with open(manual_file, "w") as f:
            json.dump(manual_data, f)

        loaded = collector.load_manual_data("TestArea")
        assert len(loaded) == 1
        assert loaded[0]["name"] == "Test Ramen"


# ==================================================================
# Integration test
# ==================================================================

def test_end_to_end_collect_and_lineage():
    from collectors.base import BaseCollector
    from processing.lineage import get_lineage_for_run

    class MockCollector(BaseCollector):
        def collect(self, area):
            return [
                {"name": "Restaurant A", "rating": 4.5},
                {"name": "Restaurant B", "rating": 3.8},
            ]

    with TempDataDir() as tmpdir:
        collector = MockCollector("integration_test", tmpdir, method="test")
        run_id = collector.run_id

        records = collector.collect({"name": "TestArea"})
        filepath = collector.save_raw(records, "TestArea")

        with open(filepath) as f:
            saved = json.load(f)

        for r in saved:
            assert_lineage(r, "integration_test")

        entries = get_lineage_for_run(run_id)
        assert len(entries) >= 1
        assert entries[0]["source_system"] == "integration_test"
        assert entries[0]["records_collected"] == 2
