"""
TfL Station Enricher
====================
Finds the nearest TfL station for each restaurant using
the TfL Unified API (no API key required for basic use).

Adds to each restaurant:
  - nearest_station: name of closest TfL station
  - nearest_station_distance_km: distance in km
  - nearest_station_lines: tube/rail lines serving it
  - transport_score: 0-1 score based on proximity and lines
"""

import json
import math
import requests
from pathlib import Path
from sqlalchemy import create_engine, text
from config import DATABASE_URL, MONGO_URL, PROCESSED_DIR

DB_URI = DATABASE_URL

TFL_API = "https://api.tfl.gov.uk"

# Cache stations to avoid repeated API calls
_STATIONS_CACHE = None


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlng/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


def get_tfl_stations() -> list[dict]:
    """Fetch all TfL stations from the API."""
    global _STATIONS_CACHE
    if _STATIONS_CACHE:
        return _STATIONS_CACHE

    # Check local cache file
    cache_path = PROCESSED_DIR / "tfl_stations.json"
    if cache_path.exists():
        with open(cache_path) as f:
            _STATIONS_CACHE = json.load(f)
        print(f"  Loaded {len(_STATIONS_CACHE)} stations from cache")
        return _STATIONS_CACHE

    print("  Fetching TfL stations from API...")
    stations = []

    # Fetch stoppoints for tube, overground, elizabeth line, dlr
    modes = ["tube", "overground", "elizabeth-line", "dlr", "national-rail"]

    for mode in modes:
        try:
            url = f"{TFL_API}/StopPoint/Mode/{mode}"
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                for stop in data.get("stopPoints", []):
                    lat = stop.get("lat")
                    lng = stop.get("lon")
                    name = stop.get("commonName", "")
                    if lat and lng and name:
                        lines = [
                            line.get("name", "")
                            for line in stop.get("lines", [])
                            if line.get("name")
                        ]
                        stations.append({
                            "name": name,
                            "lat": lat,
                            "lng": lng,
                            "lines": lines,
                            "mode": mode,
                        })
        except Exception as e:
            print(f"  Error fetching {mode}: {e}")

    # Deduplicate by name
    seen = set()
    unique = []
    for s in stations:
        if s["name"] not in seen:
            seen.add(s["name"])
            unique.append(s)

    _STATIONS_CACHE = unique

    # Save cache
    with open(cache_path, "w") as f:
        json.dump(unique, f, indent=2)

    print(f"  Fetched {len(unique)} unique TfL stations")
    return unique


def find_nearest_station(lat: float, lng: float, stations: list[dict]) -> dict:
    """Find the nearest TfL station to a given coordinate."""
    best = None
    best_dist = float("inf")

    for station in stations:
        dist = haversine_km(lat, lng, station["lat"], station["lng"])
        if dist < best_dist:
            best_dist = dist
            best = station

    if not best:
        return {}

    # Transport score — closer and more lines = higher score
    proximity_score = max(0, 1 - (best_dist / 2.0))
    line_score = min(len(best.get("lines", [])) / 5, 1.0)
    transport_score = round((proximity_score * 0.7 + line_score * 0.3), 3)

    return {
        "nearest_station": best["name"],
        "nearest_station_distance_km": round(best_dist, 3),
        "nearest_station_lines": best.get("lines", []),
        "nearest_station_mode": best.get("mode", ""),
        "transport_score": transport_score,
    }


def enrich_restaurants_with_tfl():
    """Add TfL nearest station data to all restaurants in PostgreSQL."""
    print("\n" + "="*60)
    print("  TFL STATION ENRICHMENT")
    print("="*60)

    engine = create_engine(DB_URI)

    # Add TfL columns if not exist
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                ALTER TABLE restaurants
                ADD COLUMN IF NOT EXISTS nearest_station TEXT,
                ADD COLUMN IF NOT EXISTS nearest_station_distance_km FLOAT,
                ADD COLUMN IF NOT EXISTS nearest_station_lines TEXT[],
                ADD COLUMN IF NOT EXISTS transport_score FLOAT
            """))
            conn.commit()
            print("  Added TfL columns to restaurants table")
        except Exception as e:
            conn.rollback()
            print(f"  Columns may already exist: {e}")

    # Get all restaurants with coordinates
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, name, latitude, longitude, neighbourhood
            FROM restaurants
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """)).fetchall()

    restaurants = [dict(r._mapping) for r in rows]
    print(f"  Enriching {len(restaurants)} restaurants...")

    stations = get_tfl_stations()
    if not stations:
        print("  No stations found — check TfL API")
        return

    enriched = 0
    with engine.connect() as conn:
        for r in restaurants:
            tfl = find_nearest_station(r["latitude"], r["longitude"], stations)
            if tfl:
                conn.execute(text("""
                    UPDATE restaurants
                    SET nearest_station = :station,
                        nearest_station_distance_km = :dist,
                        nearest_station_lines = :lines,
                        transport_score = :score
                    WHERE id = :id
                """), {
                    "station": tfl["nearest_station"],
                    "dist": tfl["nearest_station_distance_km"],
                    "lines": tfl["nearest_station_lines"],
                    "score": tfl["transport_score"],
                    "id": r["id"],
                })
                enriched += 1

        conn.commit()

    print(f"  Enriched {enriched} restaurants with TfL data")

    # Show sample results
    print("\n  Sample results:")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT name, neighbourhood, nearest_station,
                   nearest_station_distance_km, transport_score
            FROM restaurants
            WHERE nearest_station IS NOT NULL
            AND google_rating IS NOT NULL
            ORDER BY google_rating DESC
            LIMIT 5
        """)).fetchall()
        for row in rows:
            r = dict(row._mapping)
            print(f"    {r['name'][:30]:<30} → {r['nearest_station']:<30} "
                  f"({r['nearest_station_distance_km']:.2f}km) "
                  f"score: {r['transport_score']:.2f}")

    print("="*60 + "\n")


if __name__ == "__main__":
    enrich_restaurants_with_tfl()