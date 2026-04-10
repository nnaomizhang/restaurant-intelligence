import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
from processing.lineage import add_lineage
from ingestion.config import NEIGHBOURHOODS

load_dotenv()

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
BASE_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

def get_restaurants(lat: float, lng: float, neighbourhood: str) -> list[dict]:
    restaurants = []
    params = {
        "location": f"{lat},{lng}",
        "radius": 1000,
        "type": "restaurant",
        "key": API_KEY
    }

    while True:
        response = requests.get(BASE_URL, params=params)
        data = response.json()

        for place in data.get("results", []):
            record = {
                "name": place.get("name"),
                "place_id": place.get("place_id"),
                "rating": place.get("rating"),
                "total_ratings": place.get("user_ratings_total"),
                "address": place.get("vicinity"),
                "neighbourhood": neighbourhood,
                "lat": place.get("geometry", {}).get("location", {}).get("lat"),
                "lng": place.get("geometry", {}).get("location", {}).get("lng"),
                "price_level": place.get("price_level"),
                "types": place.get("types", [])
            }
            record = add_lineage(
                record,
                source="google_places",
                version="1.0",
                raw_file_path=f"data/raw/google_places_{neighbourhood.lower()}.json"
            )
            restaurants.append(record)

        next_page = data.get("next_page_token")
        if not next_page:
            break

        params["pagetoken"] = next_page

    return restaurants

def save_raw(data: list[dict], neighbourhood: str):
    os.makedirs("data/raw", exist_ok=True)
    path = f"data/raw/google_places_{neighbourhood.lower()}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(data)} records to {path}")

def run():
    for area in NEIGHBOURHOODS:
        print(f"Collecting Google Places data for {area['name']}...")
        restaurants = get_restaurants(area["lat"], area["lng"], area["name"])
        save_raw(restaurants, area["name"])
        print(f"Found {len(restaurants)} restaurants in {area['name']}")

if __name__ == "__main__":
    run()