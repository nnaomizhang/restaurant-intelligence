"""
Restaurant endpoints.
"""

import os
import logging
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import create_engine, text
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)

DB_URI = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/restaurants")


def serialise(row: dict) -> dict:
    """Convert non-JSON-serialisable types to strings."""
    result = {}
    for k, v in row.items():
        if hasattr(v, 'isoformat'):
            result[k] = v.isoformat()
        elif isinstance(v, list):
            result[k] = v
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
    cuisine: Optional[str] = Query(None),
    trading_pattern: Optional[str] = Query(None),
    on_deliveroo: Optional[bool] = Query(None),
    limit: int = Query(200, le=500),
):
    """Get filtered list of restaurants."""
    try:
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

        if cuisine:
            conditions.append("business_type ILIKE :cuisine")
            params["cuisine"] = f"%{cuisine}%"

        if trading_pattern:
            conditions.append("trading_pattern = :trading_pattern")
            params["trading_pattern"] = trading_pattern

        if on_deliveroo is not None:
            if on_deliveroo:
                conditions.append("menu_item_count > 0")
            else:
                conditions.append("(menu_item_count = 0 OR menu_item_count IS NULL)")

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

    except Exception as e:
        logger.error(f"Error fetching restaurants: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/restaurants/{google_place_id}")
def get_restaurant(google_place_id: str):
    """Get single restaurant by Google Place ID."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM restaurants WHERE google_place_id = :id"),
                {"id": google_place_id}
            ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Restaurant not found")

        return serialise(dict(row._mapping))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching restaurant {google_place_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/restaurants/{google_place_id}/reviews")
def get_restaurant_reviews(google_place_id: str, limit: int = Query(20, le=100)):
    """Get reviews for a specific restaurant."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT review_text, review_rating, review_date, review_language
                FROM reviews
                WHERE google_place_id = :id
                ORDER BY review_rating DESC
                LIMIT :limit
            """), {"id": google_place_id, "limit": limit}).fetchall()

        return [dict(row._mapping) for row in rows]

    except Exception as e:
        logger.error(f"Error fetching reviews for {google_place_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/hygiene")
def get_hygiene(
    neighbourhood: Optional[str] = Query(None),
    min_rating: Optional[int] = Query(None),
    limit: int = Query(50, le=500),
):
    """Get FSA hygiene ratings."""
    try:
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

    except Exception as e:
        logger.error(f"Error fetching hygiene ratings: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/companies")
def get_companies(
    neighbourhood: Optional[str] = Query(None),
    distressed_only: Optional[bool] = Query(None),
    limit: int = Query(30, le=100),
):
    """Get Companies House data."""
    try:
        engine = get_engine()
        conditions = ["1=1"]
        params = {"limit": limit}

        if neighbourhood:
            conditions.append("neighbourhood ILIKE :neighbourhood")
            params["neighbourhood"] = f"%{neighbourhood}%"

        if distressed_only:
            conditions.append("(accounts_overdue = TRUE OR array_length(distress_signals, 1) > 0)")

        where = " AND ".join(conditions)
        sql = f"""
            SELECT company_number, name, status, incorporation_date,
                   registered_address, postcode, sic_codes,
                   accounts_overdue, distress_signals, officer_count, neighbourhood
            FROM companies
            WHERE {where}
            ORDER BY name
            LIMIT :limit
        """

        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()

        return [serialise(dict(row._mapping)) for row in rows]

    except Exception as e:
        logger.error(f"Error fetching companies: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/lineage")
def get_lineage(
    event_type: Optional[str] = Query(None),
    source_system: Optional[str] = Query(None),
    limit: int = Query(500, le=2500),
):
    """Get data lineage events."""
    try:
        engine = get_engine()
        conditions = ["1=1"]
        params = {"limit": limit}

        if event_type:
            conditions.append("event_type = :event_type")
            params["event_type"] = event_type

        if source_system:
            conditions.append("source_system = :source_system")
            params["source_system"] = source_system

        where = " AND ".join(conditions)
        sql = f"""
            SELECT event_type, run_id, timestamp, agent, source_system,
                   area, records_collected, records_out,
                   destination_table, transformations
            FROM data_lineage
            WHERE {where}
            ORDER BY timestamp DESC
            LIMIT :limit
        """

        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()

        return [serialise(dict(row._mapping)) for row in rows]

    except Exception as e:
        logger.error(f"Error fetching lineage: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")