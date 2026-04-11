"""
Catchment Modeller
==================
Models restaurant catchment areas using:
- Walking/cycling/driving time polygons (approximated)
- Population within catchment
- Competitor density within catchment
- Deliveroo delivery radius overlap

Since PostGIS is not available, uses Haversine distance
calculations in pure Python/SQL.
"""

import json
import math
from sqlalchemy import create_engine, text
from config import DATABASE_URL, MONGO_URL, PROCESSED_DIR

DB_URI = DATABASE_URL

# Average speeds for travel modes
TRAVEL_SPEEDS = {
    "walk_5min": {"speed_kmh": 5.0, "time_min": 5},
    "walk_10min": {"speed_kmh": 5.0, "time_min": 10},
    "cycle_10min": {"speed_kmh": 15.0, "time_min": 10},
    "drive_10min": {"speed_kmh": 30.0, "time_min": 10},
    "deliveroo_zone": {"speed_kmh": 20.0, "time_min": 9},
}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


def get_radius_km(mode: str) -> float:
    """Get catchment radius in km for a travel mode."""
    config = TRAVEL_SPEEDS[mode]
    return (config["speed_kmh"] * config["time_min"]) / 60


def model_catchment(engine, restaurant: dict) -> dict:
    """Model catchment zones for a single restaurant."""
    lat = restaurant.get("latitude")
    lng = restaurant.get("longitude")
    name = restaurant.get("name", "Unknown")
    business_type = restaurant.get("business_type", "")

    if not lat or not lng:
        return {}

    catchment = {"name": name, "business_type": business_type, "zones": {}}

    # Fetch all restaurants once outside the loop
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT name, latitude, longitude, google_rating,
                   neighbourhood, menu_item_count, business_type,
                   google_price_level
            FROM restaurants
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """)).fetchall()

    all_restaurants = [dict(r._mapping) for r in rows]
    
    print(f"    Loaded {len(all_restaurants)} restaurants for comparison")

    for mode in TRAVEL_SPEEDS:
        radius_km = get_radius_km(mode)
        competitors = []

        for r in all_restaurants:
            r_lat = r.get("latitude")
            r_lng = r.get("longitude")
            r_name = r.get("name", "")

            if r_name == name:
                continue
            if r_lat is None or r_lng is None:
                continue

            dist = haversine_km(lat, lng, float(r_lat), float(r_lng))
            if dist <= radius_km:
                competitors.append({
                    "name": r_name,
                    "distance_km": round(dist, 3),
                    "rating": r.get("google_rating"),
                    "neighbourhood": r.get("neighbourhood"),
                    "on_deliveroo": bool(r.get("menu_item_count") and r.get("menu_item_count") > 0),
                    "business_type": r.get("business_type"),
                    "price_level": r.get("google_price_level"),
                })

        same_type = [c for c in competitors if c["business_type"] == business_type]
        high_rated = [c for c in competitors if c["rating"] and c["rating"] >= 4.5]

        catchment["zones"][mode] = {
            "radius_km": round(radius_km, 2),
            "total_competitors": len(competitors),
            "same_type_competitors": len(same_type),
            "high_rated_competitors": len(high_rated),
            "nearest_competitors": sorted(competitors, key=lambda x: x["distance_km"])[:3],
            "avg_competitor_rating": round(
                sum(c["rating"] for c in competitors if c["rating"]) /
                max(len([c for c in competitors if c["rating"]]), 1), 2
            ),
            "competitive_intensity": "high" if len(competitors) > 100 else "medium" if len(competitors) > 30 else "low",
        }

    return catchment


def run_catchment_modelling():
    """Run catchment modelling for top restaurants in each neighbourhood."""
    print("\n" + "="*60)
    print("  CATCHMENT MODELLER")
    print("="*60)

    engine = create_engine(DB_URI)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT name, neighbourhood, latitude, longitude,
                   google_rating, menu_item_count
            FROM restaurants
            WHERE latitude IS NOT NULL
            AND google_rating IS NOT NULL
            ORDER BY google_rating DESC
            LIMIT 9
        """)).fetchall()

    restaurants = [dict(r._mapping) for r in rows]
    
    print(f"  First restaurant keys: {list(restaurants[0].keys())}")
    print(f"  First restaurant: {restaurants[0]}")
    results = {}

    print(f"\n  Modelling catchments for {len(restaurants)} restaurants...")

    for restaurant in restaurants:
        name = restaurant["name"]
        neighbourhood = restaurant["neighbourhood"]
        print(f"  Modelling: {name} ({neighbourhood})")

        catchment = model_catchment(engine, restaurant)
        results[name] = catchment

        # Print summary
        for mode in ["walk_5min", "walk_10min", "deliveroo_zone"]:
            zone = catchment.get("zones", {}).get(mode, {})
            print(f"    {mode:<20} {zone.get('total_competitors', 0)} competitors "
                  f"within {zone.get('radius_km', 0)}km")

    # Save results
    output_path = PROCESSED_DIR / "catchment_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n  Saved catchment results to {output_path}")
    print("="*60 + "\n")

    return results


if __name__ == "__main__":
    run_catchment_modelling()