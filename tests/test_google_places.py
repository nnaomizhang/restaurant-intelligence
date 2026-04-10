import sys
sys.path.append('/Users/naomi/restaurant-intelligence')

from dotenv import load_dotenv
load_dotenv('/Users/naomi/restaurant-intelligence/.env')

from ingestion.google_places import get_restaurants

def test_returns_results():
    results = get_restaurants(51.5231, -0.0784, "Shoreditch")
    assert len(results) > 0

def test_restaurant_has_name():
    results = get_restaurants(51.5231, -0.0784, "Shoreditch")
    assert results[0]["name"] is not None

def test_restaurant_has_rating():
    results = get_restaurants(51.5231, -0.0784, "Shoreditch")
    assert results[0]["rating"] is not None

def test_restaurant_has_address():
    results = get_restaurants(51.5231, -0.0784, "Shoreditch")
    assert results[0]["address"] is not None

def test_lineage_exists():
    results = get_restaurants(51.5231, -0.0784, "Shoreditch")
    assert "lineage" in results[0]

def test_lineage_has_source():
    results = get_restaurants(51.5231, -0.0784, "Shoreditch")
    assert results[0]["lineage"]["source_name"] == "google_places"

def test_lineage_has_timestamp():
    results = get_restaurants(51.5231, -0.0784, "Shoreditch")
    assert results[0]["lineage"]["collection_timestamp"] is not None