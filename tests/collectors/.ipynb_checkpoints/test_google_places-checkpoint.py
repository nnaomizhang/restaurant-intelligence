import sys
sys.path.append('/Users/naomi/restaurant-intelligence')

from collectors.config import TARGET_AREAS
from collectors.google_places import GooglePlacesCollector

collector = GooglePlacesCollector()
area = TARGET_AREAS[0]  # Shoreditch

def test_nearby_search_returns_results():
    listings = collector._nearby_search(area['lat'], area['lng'], area['radius_km'])
    assert len(listings) > 0

def test_nearby_search_pagination():
    listings = collector._nearby_search(area['lat'], area['lng'], area['radius_km'])
    assert len(listings) > 20, "Should return more than 1 page of results"

def test_place_details_returns_data():
    listings = collector._nearby_search(area['lat'], area['lng'], area['radius_km'])
    details = collector._place_details(listings[0]['place_id'])
    assert details is not None

def test_place_details_has_required_fields():
    listings = collector._nearby_search(area['lat'], area['lng'], area['radius_km'])
    details = collector._place_details(listings[0]['place_id'])
    assert details['name'] is not None
    assert details['address'] is not None
    assert details['rating'] is not None

def test_review_extraction():
    listings = collector._nearby_search(area['lat'], area['lng'], area['radius_km'])
    details = collector._place_details(listings[0]['place_id'])
    assert isinstance(details['reviews'], list)

def test_lineage_attached():
    import json
    import os
    files = os.listdir('data/raw/google_places/')
    assert len(files) > 0
    latest = sorted(files)[-1]
    with open(f'data/raw/google_places/{latest}') as f:
        data = json.load(f)
    assert '_lineage' in data[0]
    assert data[0]['_lineage']['source_name'] == 'google_places'