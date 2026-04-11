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

    if not lat or not lng:
        return {}

    catchment = {"name": name, "zones": {}}

    with engine.connect() as conn:
        # Get all restaurants
        all_restaurants = conn.execute(text("""
            SELECT name, latitude, longitude, google_rating,
                   neighbourhood, menu_item_count
            FROM restaurants
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """)).fetchall()

        for mode, config in TRAVEL_SPEEDS.items():
            radius_km = get_radius_km(mode)

            # Find competitors within catchment
            competitors = []
            for r in all_restaurants:
                r = dict(r._mapping)
                if r["name"] == name:
                    continue
                dist = haversine_km(lat, lng, r["latitude"], r["longitude"])
                if dist <= radius_km:
                    competitors.append({
                        "name": r["name"],
                        "distance_km": round(dist, 3),
                        "rating": r["google_rating"],
                        "neighbourhood": r["neighbourhood"],
                        "on_deliveroo": bool(r["menu_item_count"] and r["menu_item_count"] > 0),
                    })

            catchment["zones"][mode] = {
                "radius_km": round(radius_km, 2),
                "competitor_count": len(competitors),
                "top_competitors": sorted(competitors, key=lambda x: x["distance_km"])[:5],
                "avg_competitor_rating": round(
                    sum(c["rating"] for c in competitors if c["rating"]) /
                    max(len([c for c in competitors if c["rating"]]), 1), 2
                ),
            }

    return catchment


def run_catchment_modelling():
    """Run catchment modelling for top restaurants in each neighbourhood."""
    print("\n" + "="*60)
    print("  CATCHMENT MODELLER")
    print("="*60)

    engine = create_engine(DB_URI)

    with engine.connect() as conn:
        # Get top 3 restaurants per neighbourhood
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
            print(f"    {mode:<20} {zone.get('competitor_count', 0)} competitors "
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