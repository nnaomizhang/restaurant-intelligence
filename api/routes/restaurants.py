"""
Restaurant endpoints.
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import create_engine, text
from typing import Optional

router = APIRouter()

import os
DB_URI = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/restaurants")

def serialise(row: dict) -> dict:
    """Convert non-JSON-serialisable types to strings."""
    result = {}
    for k, v in row.items():
        if hasattr(v, 'isoformat'):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result

def get_engine():
    return create_engine(DB_URI)


@router.get("/restaurants")
def get_restaurants(
    neighbourhood: Optional[str] = Query(None),
    min_rating: Optional[float] = Query(None),
    max_price_level: Optional[int] = Query(None),
    hygiene_min: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
):
    """Get filtered list of restaurants."""
    engine = get_engine()

    conditions = ["1=1"]
    params = {"limit": limit}

    if neighbourhood:
        conditions.append("neighbourhood ILIKE :neighbourhood")
        params["neighbourhood"] = f"%{neighbourhood}%"

    if min_rating:
        conditions.append("google_rating >= :min_rating")
        params["min_rating"] = min_rating

    if max_price_level:
        conditions.append("google_price_level <= :max_price_level")
        params["max_price_level"] = max_price_level

    if hygiene_min:
        conditions.append("google_rating >= :hygiene_min")
        params["hygiene_min"] = hygiene_min

    where = " AND ".join(conditions)
    sql = f"""
        SELECT name, neighbourhood, address, postcode,
               latitude, longitude, google_rating,
               google_review_count, google_price_level,
               business_type, company_number, company_status,
               deliveroo_rating, delivery_fee, menu_item_count,
               sources_matched, created_at,
               nearest_station, nearest_station_distance_km,
               nearest_station_lines, transport_score,
               spatial_cluster, distance_to_centre_km,
               trading_pattern, customer_segments, days_open,
               avg_open_time, avg_close_time, open_weekends, open_weekdays
        FROM restaurants
        WHERE {where}
        ORDER BY google_rating DESC NULLS LAST
        LIMIT :limit
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    return [serialise(dict(row._mapping)) for row in rows]


@router.get("/restaurants/{google_place_id}")
def get_restaurant(google_place_id: str):
    """Get single restaurant by Google Place ID."""
    engine = get_engine()

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM restaurants WHERE google_place_id = :id"),
            {"id": google_place_id}
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    return serialise(dict(row._mapping))


@router.get("/hygiene")
def get_hygiene(
    neighbourhood: Optional[str] = Query(None),
    min_rating: Optional[int] = Query(None),
    limit: int = Query(50, le=500),
):
    """Get hygiene ratings."""
    engine = get_engine()

    conditions = ["1=1"]
    params = {"limit": limit}

    if neighbourhood:
        conditions.append("neighbourhood ILIKE :neighbourhood")
        params["neighbourhood"] = f"%{neighbourhood}%"

    if min_rating is not None:
        conditions.append("rating_value >= :min_rating")
        params["min_rating"] = min_rating

    where = " AND ".join(conditions)
    sql = f"""
        SELECT business_name, address, postcode, neighbourhood,
               rating_value, rating_date, business_type,
               score_hygiene, score_structural, score_management
        FROM hygiene_ratings
        WHERE {where}
        ORDER BY rating_value DESC NULLS LAST
        LIMIT :limit
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    return [serialise(dict(row._mapping)) for row in rows]