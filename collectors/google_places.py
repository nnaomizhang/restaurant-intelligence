import os
import requests
import json
from dotenv import load_dotenv
from processing.lineage import add_lineage
from ingestion.config import NEIGHBOURHOODS

load_dotenv()

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
URL = "https://places.googleapis.com/v1/places:searchNearby"

def get_restaurants(lat: float, lng: float, neighbourhood: str) -> list[dict]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.rating,places.formattedAddress,places.location,places.priceLevel,places.userRatingCount,places.id,places.types"
    }

    all_restaurants = {}
    radii = [500, 1000, 1500]

    for radius in radii:
        body = {
            "includedTypes": ["restaurant"],
            "maxResultCount": 20,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": lat,
                        "longitude": lng
                    },
                    "radius": float(radius)
                }
            }
        }

        response = requests.post(URL, headers=headers, json=body)
        data = response.json()

        for place in data.get("places", []):
            place_id = place.get("id")
            if place_id in all_restaurants:
                continue

            record = {
                "name": place.get("displayName", {}).get("text"),
                "place_id": place_id,
                "rating": place.get("rating"),
                "total_ratings": place.get("userRatingCount"),
                "address": place.get("formattedAddress"),
                "neighbourhood": neighbourhood,
                "lat": place.get("location", {}).get("latitude"),
                "lng": place.get("location", {}).get("longitude"),
                "price_level": place.get("priceLevel"),
                "types": place.get("types", [])
            }
            record = add_lineage(
                record,
                source="google_places",
                version="1.1",
                raw_file_path=f"data/raw/google_places_{neighbourhood.lower()}.json"
            )
            all_restaurants[place_id] = record

    return list(all_restaurants.values())

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
    