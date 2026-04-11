from config import DATABASE_URL, MONGO_URL
"""
Demographics endpoint — ONS census data.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import create_engine, text
from typing import Optional

router = APIRouter()

DB_URI = DATABASE_URL


def get_engine():
    return create_engine(DB_URI)


@router.get("/demographics/{neighbourhood}")
def get_demographics(neighbourhood: str):
    """Get demographic summary for a neighbourhood."""
    engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    neighbourhood,
                    COUNT(*) as lsoa_count,
                    SUM(total_population) as total_population,
                    AVG(population_density) as avg_population_density,
                    AVG(age_25_34_pct) as avg_age_25_34_pct,
                    AVG(age_35_49_pct) as avg_age_35_49_pct,
                    AVG(economically_active_pct) as avg_economically_active_pct,
                    AVG(household_single_pct) as avg_household_single_pct
                FROM demographics
                WHERE neighbourhood ILIKE :neighbourhood
                GROUP BY neighbourhood
            """),
            {"neighbourhood": f"%{neighbourhood}%"}
        ).fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No demographics found for {neighbourhood}"
        )

    return [dict(row._mapping) for row in rows]


@router.get("/demographics")
def get_all_demographics():
    """Get demographic summary for all neighbourhoods."""
    engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    neighbourhood,
                    COUNT(*) as lsoa_count,
                    SUM(total_population) as total_population,
                    AVG(population_density) as avg_population_density,
                    AVG(age_25_34_pct) as avg_age_25_34_pct,
                    AVG(economically_active_pct) as avg_economically_active_pct
                FROM demographics
                GROUP BY neighbourhood
                ORDER BY neighbourhood
            """)
        ).fetchall()

    return [dict(row._mapping) for row in rows]