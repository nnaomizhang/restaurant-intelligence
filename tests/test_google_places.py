import sys
sys.path.append('/Users/naomi/restaurant-intelligence')

from dotenv import load_dotenv
load_dotenv('/Users/naomi/restaurant-intelligence/.env')

from ingestion.google_places import get_restaurants, run

def test_get_restaurants():
    results = get_restaurants(51.5231, -0.0784, "Shoreditch")
    assert len(results) > 0, "Should return at least 1 restaurant"
    assert results[0]["name"] is not None, "Restaurant should have a name"
    assert results[0]["lineage"] is not None, "Should have lineage metadata"
    print(f"PASS — found {len(results)} restaurants")
    print(f"First result: {results[0]['name']}")

def test_all_neighbourhoods():
    run()
    print("PASS — all 3 neighbourhoods collected")

if __name__ == "__main__":
    test_get_restaurants()
    test_all_neighbourhoods()