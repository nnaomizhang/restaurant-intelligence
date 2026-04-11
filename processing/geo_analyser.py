"""
Geo Analyser
============
Generates GeoJSON for restaurant locations and neighbourhood boundaries.
Sets up PostGIS spatial queries for catchment modelling.

Outputs:
  - data/processed/restaurants.geojson
  - data/processed/neighbourhoods.geojson
  - data/processed/catchment_zones.geojson
"""

import json
import math
from pathlib import Path
from sqlalchemy import create_engine, text
from config import DATABASE_URL, MONGO_URL, PROCESSED_DIR

DB_URI = DATABASE_URL

# Neighbourhood centre points
NEIGHBOURHOOD_CENTRES = {
    "Shoreditch": {"lat": 51.5246, "lng": -0.0780},
    "Peckham": {"lat": 51.4738, "lng": -0.0690},
    "Hackney": {"lat": 51.5450, "lng": -0.0553},
}

# Approximate catchment radii in km
CATCHMENT_RADII = {
    "walk_5min": 0.4,
    "walk_10min": 0.8,
    "cycle_10min": 2.0,
    "drive_10min": 4.0,
    "deliveroo_zone": 3.0,
}


def generate_circle_polygon(lat: float, lng: float, radius_km: float, points: int = 64) -> list:
    """Generate a circle polygon as GeoJSON coordinates."""
    coords = []
    for i in range(points + 1):
        angle = (2 * math.pi * i) / points
        # Convert km to degrees (approximate)
        d_lat = (radius_km / 111.0) * math.cos(angle)
        d_lng = (radius_km / (111.0 * math.cos(math.radians(lat)))) * math.sin(angle)
        coords.append([lng + d_lng, lat + d_lat])
    return coords


def generate_restaurant_geojson(engine) -> dict:
    """Generate GeoJSON FeatureCollection for all restaurants."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT name, neighbourhood, address, postcode,
                   latitude, longitude, google_rating,
                   google_review_count, google_price_level,
                   business_type, menu_item_count
            FROM restaurants
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """)).fetchall()

    features = []
    for row in rows:
        r = dict(row._mapping)
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["longitude"], r["latitude"]]
            },
            "properties": {
                "name": r["name"],
                "neighbourhood": r["neighbourhood"],
                "address": r["address"],
                "postcode": r["postcode"],
                "google_rating": r["google_rating"],
                "review_count": r["google_review_count"],
                "price_level": r["google_price_level"],
                "business_type": r["business_type"],
                "on_deliveroo": bool(r["menu_item_count"] and r["menu_item_count"] > 0),
            }
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "total_restaurants": len(features),
            "description": "Restaurant locations for Shoreditch, Peckham and Hackney"
        }
    }


def generate_neighbourhood_geojson() -> dict:
    """Generate GeoJSON for neighbourhood boundary approximations."""
    features = []

    for name, centre in NEIGHBOURHOOD_CENTRES.items():
        # Approximate neighbourhood boundary as a circle
        coords = generate_circle_polygon(
            centre["lat"], centre["lng"], radius_km=1.5
        )
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords]
            },
            "properties": {
                "name": name,
                "centre_lat": centre["lat"],
                "centre_lng": centre["lng"],
                "radius_km": 1.5,
            }
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "description": "Approximate neighbourhood boundaries",
            "note": "Boundaries are circular approximations centred on neighbourhood midpoints"
        }
    }


def generate_catchment_geojson() -> dict:
    """Generate catchment zone GeoJSON for each neighbourhood."""
    features = []

    for neighbourhood, centre in NEIGHBOURHOOD_CENTRES.items():
        for zone_name, radius_km in CATCHMENT_RADII.items():
            coords = generate_circle_polygon(
                centre["lat"], centre["lng"], radius_km
            )
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords]
                },
                "properties": {
                    "neighbourhood": neighbourhood,
                    "zone": zone_name,
                    "radius_km": radius_km,
                    "description": f"{zone_name.replace('_', ' ')} catchment for {neighbourhood}"
                }
            }
            features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "description": "Catchment zones for each neighbourhood",
            "zones": list(CATCHMENT_RADII.keys())
        }
    }


def setup_postgis_spatial_columns(engine):
    """
    Add spatial analysis to PostgreSQL using calculated distances.
    Since PostGIS requires a separate extension, we implement
    spatial queries using Haversine formula in SQL.
    """
    print("  Setting up spatial analysis columns...")

    with engine.connect() as conn:
        # Add spatial score column if not exists
        try:
            conn.execute(text("""
                ALTER TABLE restaurants
                ADD COLUMN IF NOT EXISTS spatial_cluster TEXT,
                ADD COLUMN IF NOT EXISTS distance_to_centre_km FLOAT
            """))
            conn.commit()
        except Exception:
            conn.rollback()

        # Calculate distance to neighbourhood centre for each restaurant
        for neighbourhood, centre in NEIGHBOURHOOD_CENTRES.items():
            try:
                conn.execute(text("""
                    UPDATE restaurants
                    SET distance_to_centre_km = (
                        6371 * acos(
                            cos(radians(:centre_lat)) *
                            cos(radians(latitude)) *
                            cos(radians(longitude) - radians(:centre_lng)) +
                            sin(radians(:centre_lat)) *
                            sin(radians(latitude))
                        )
                    )
                    WHERE neighbourhood = :neighbourhood
                    AND latitude IS NOT NULL
                    AND longitude IS NOT NULL
                """), {
                    "centre_lat": centre["lat"],
                    "centre_lng": centre["lng"],
                    "neighbourhood": neighbourhood,
                })
                conn.commit()
                print(f"    Updated spatial data for {neighbourhood}")
            except Exception as e:
                conn.rollback()
                print(f"    Error updating {neighbourhood}: {e}")

        # Assign spatial clusters based on distance
        try:
            conn.execute(text("""
                UPDATE restaurants
                SET spatial_cluster = CASE
                    WHEN distance_to_centre_km < 0.5 THEN 'core'
                    WHEN distance_to_centre_km < 1.0 THEN 'inner'
                    WHEN distance_to_centre_km < 1.5 THEN 'outer'
                    ELSE 'fringe'
                END
                WHERE distance_to_centre_km IS NOT NULL
            """))
            conn.commit()
            print("    Spatial clusters assigned")
        except Exception as e:
            conn.rollback()
            print(f"    Error assigning clusters: {e}")


def run_geo_analysis():
    """Run full geo analysis pipeline."""
    print("\n" + "="*60)
    print("  GEO ANALYSER")
    print("="*60)

    engine = create_engine(DB_URI)
    output_dir = PROCESSED_DIR

    # Generate GeoJSON files
    print("\n  Generating restaurant GeoJSON...")
    restaurant_geojson = generate_restaurant_geojson(engine)
    path = output_dir / "restaurants.geojson"
    with open(path, "w") as f:
        json.dump(restaurant_geojson, f, indent=2)
    print(f"    Saved {len(restaurant_geojson['features'])} restaurants to {path.name}")

    print("\n  Generating neighbourhood boundary GeoJSON...")
    neighbourhood_geojson = generate_neighbourhood_geojson()
    path = output_dir / "neighbourhoods.geojson"
    with open(path, "w") as f:
        json.dump(neighbourhood_geojson, f, indent=2)
    print(f"    Saved {len(neighbourhood_geojson['features'])} neighbourhoods to {path.name}")

    print("\n  Generating catchment zone GeoJSON...")
    catchment_geojson = generate_catchment_geojson()
    path = output_dir / "catchment_zones.geojson"
    with open(path, "w") as f:
        json.dump(catchment_geojson, f, indent=2)
    print(f"    Saved {len(catchment_geojson['features'])} catchment zones to {path.name}")

    # Setup spatial columns in PostgreSQL
    print("\n  Setting up spatial analysis in PostgreSQL...")
    setup_postgis_spatial_columns(engine)

    # Verify spatial data
    print("\n  Spatial cluster distribution:")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT neighbourhood, spatial_cluster, COUNT(*) as count
            FROM restaurants
            WHERE spatial_cluster IS NOT NULL
            GROUP BY neighbourhood, spatial_cluster
            ORDER BY neighbourhood, spatial_cluster
        """)).fetchall()
        for row in rows:
            r = dict(row._mapping)
            print(f"    {r['neighbourhood']:<12} {r['spatial_cluster']:<8} {r['count']} restaurants")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    run_geo_analysis()