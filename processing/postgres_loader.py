"""
PostgreSQL Loader
=================
Loads structured data into PostgreSQL tables.

Tables:
  - restaurants     : Master restaurant records
  - hygiene_ratings : FSA hygiene data
  - demographics    : ONS census data
  - menu_items      : Deliveroo menu items
"""

import json
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from config import DATABASE_URL, MONGO_URL, PROCESSED_DIR
from processing.lineage import log_transformation, generate_run_id


# ==================================================================
# Connection
# ==================================================================

def get_engine(uri: str = DATABASE_URL):
    return create_engine(uri)


# ==================================================================
# Schema creation
# ==================================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS restaurants (
    id                  SERIAL PRIMARY KEY,
    name                TEXT,
    name_normalised     TEXT,
    neighbourhood       TEXT,
    address             TEXT,
    postcode            TEXT,
    latitude            FLOAT,
    longitude           FLOAT,
    google_place_id     TEXT UNIQUE,
    google_rating       FLOAT,
    google_review_count INTEGER,
    google_price_level  INTEGER,
    business_type       TEXT,
    company_number      TEXT,
    company_status      TEXT,
    incorporation_date  TEXT,
    accounts_overdue    BOOLEAN,
    deliveroo_rating    FLOAT,
    delivery_fee        FLOAT,
    menu_item_count     INTEGER,
    sources_matched     TEXT[],
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hygiene_ratings (
    id                  SERIAL PRIMARY KEY,
    fsa_id              TEXT UNIQUE,
    business_name       TEXT,
    address             TEXT,
    postcode            TEXT,
    neighbourhood       TEXT,
    rating_value        INTEGER,
    rating_date         TEXT,
    score_hygiene       TEXT,
    score_structural    TEXT,
    score_management    TEXT,
    business_type       TEXT,
    latitude            FLOAT,
    longitude           FLOAT,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS demographics (
    id                  SERIAL PRIMARY KEY,
    neighbourhood       TEXT,
    lsoa_code           TEXT,
    lsoa_name           TEXT,
    total_population    FLOAT,
    population_density  FLOAT,
    age_25_34_pct       FLOAT,
    age_35_49_pct       FLOAT,
    economically_active_pct FLOAT,
    household_single_pct FLOAT,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS menu_items (
    id                  SERIAL PRIMARY KEY,
    restaurant_name     TEXT,
    neighbourhood       TEXT,
    item_name           TEXT,
    item_price          FLOAT,
    item_category       TEXT,
    item_description    TEXT,
    is_popular          BOOLEAN,
    dietary_tags        TEXT[],
    created_at          TIMESTAMP DEFAULT NOW()
);
"""


def create_schema(engine):
    with engine.connect() as conn:
        conn.execute(text(SCHEMA_SQL))
        conn.commit()
    print("  Schema created")


# ==================================================================
# Loaders
# ==================================================================

def load_processed(source: str, area_name: str) -> list[dict]:
    folder = PROCESSED_DIR / source
    if not folder.exists():
        return []
    slug = area_name.lower().replace(" ", "_").replace("-", "_")
    files = sorted(
        [f for f in folder.glob(f"{slug}*.json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    if not files:
        return []
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)


def load_restaurants(engine, area_name: str) -> int:
    records = load_processed("master", area_name)
    if not records:
        return 0

    inserted = 0
    with engine.connect() as conn:
        for r in records:
            try:
                conn.execute(text("""
                    INSERT INTO restaurants (
                        name, name_normalised, neighbourhood, address, postcode,
                        latitude, longitude, google_place_id, google_rating,
                        google_review_count, google_price_level, business_type,
                        company_number, company_status, incorporation_date,
                        accounts_overdue, deliveroo_rating, delivery_fee,
                        menu_item_count, sources_matched
                    ) VALUES (
                        :name, :name_normalised, :neighbourhood, :address, :postcode,
                        :latitude, :longitude, :google_place_id, :google_rating,
                        :google_review_count, :google_price_level, :business_type,
                        :company_number, :company_status, :incorporation_date,
                        :accounts_overdue, :deliveroo_rating, :delivery_fee,
                        :menu_item_count, :sources_matched
                    )
                    ON CONFLICT (google_place_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        google_rating = EXCLUDED.google_rating,
                        sources_matched = EXCLUDED.sources_matched
                """), {
                    "name": r.get("name"),
                    "name_normalised": r.get("name_normalised"),
                    "neighbourhood": r.get("neighbourhood"),
                    "address": r.get("address"),
                    "postcode": r.get("postcode"),
                    "latitude": r.get("latitude"),
                    "longitude": r.get("longitude"),
                    "google_place_id": r.get("google_place_id"),
                    "google_rating": r.get("google_rating"),
                    "google_review_count": r.get("google_review_count"),
                    "google_price_level": r.get("google_price_level"),
                    "business_type": r.get("business_type"),
                    "company_number": r.get("company_number"),
                    "company_status": r.get("company_status"),
                    "incorporation_date": r.get("incorporation_date"),
                    "accounts_overdue": r.get("accounts_overdue"),
                    "deliveroo_rating": r.get("deliveroo_rating"),
                    "delivery_fee": r.get("delivery_fee"),
                    "menu_item_count": r.get("menu_item_count", 0),
                    "sources_matched": r.get("sources_matched", []),
                })
                inserted += 1
            except Exception as e:
                continue
        conn.commit()
    return inserted


def load_hygiene(engine, area_name: str) -> int:
    records = load_processed("fsa", area_name)
    if not records:
        return 0

    inserted = 0
    with engine.connect() as conn:
        for r in records:
            try:
                conn.execute(text("""
                    INSERT INTO hygiene_ratings (
                        fsa_id, business_name, address, postcode, neighbourhood,
                        rating_value, rating_date, score_hygiene, score_structural,
                        score_management, business_type, latitude, longitude
                    ) VALUES (
                        :fsa_id, :business_name, :address, :postcode, :neighbourhood,
                        :rating_value, :rating_date, :score_hygiene, :score_structural,
                        :score_management, :business_type, :latitude, :longitude
                    )
                    ON CONFLICT (fsa_id) DO UPDATE SET
                        rating_value = EXCLUDED.rating_value,
                        rating_date = EXCLUDED.rating_date
                """), {
                    "fsa_id": r.get("fsa_id"),
                    "business_name": r.get("name"),
                    "address": r.get("address"),
                    "postcode": r.get("postcode"),
                    "neighbourhood": r.get("neighbourhood"),
                    "rating_value": r.get("rating_value"),
                    "rating_date": r.get("rating_date"),
                    "score_hygiene": str(r.get("score_hygiene")) if r.get("score_hygiene") else None,
                    "score_structural": str(r.get("score_structural")) if r.get("score_structural") else None,
                    "score_management": str(r.get("score_management")) if r.get("score_management") else None,
                    "business_type": r.get("business_type"),
                    "latitude": float(r.get("latitude")) if r.get("latitude") else None,
                    "longitude": float(r.get("longitude")) if r.get("longitude") else None,
                })
                inserted += 1
            except Exception as e:
                continue
        conn.commit()
    return inserted


def load_demographics(engine, area_name: str) -> int:
    records = load_processed("ons_census", area_name)
    if not records:
        return 0

    inserted = 0
    with engine.connect() as conn:
        for r in records:
            try:
                conn.execute(text("""
                    INSERT INTO demographics (
                        neighbourhood, lsoa_code, lsoa_name, total_population,
                        population_density, age_25_34_pct, age_35_49_pct,
                        economically_active_pct, household_single_pct
                    ) VALUES (
                        :neighbourhood, :lsoa_code, :lsoa_name, :total_population,
                        :population_density, :age_25_34_pct, :age_35_49_pct,
                        :economically_active_pct, :household_single_pct
                    )
                """), {
                    "neighbourhood": r.get("neighbourhood"),
                    "lsoa_code": r.get("lsoa_code"),
                    "lsoa_name": r.get("lsoa_name"),
                    "total_population": r.get("total_population"),
                    "population_density": r.get("population_density"),
                    "age_25_34_pct": r.get("age_25_34_pct"),
                    "age_35_49_pct": r.get("age_35_49_pct"),
                    "economically_active_pct": r.get("economically_active_pct"),
                    "household_single_pct": r.get("household_single_pct"),
                })
                inserted += 1
            except Exception as e:
                continue
        conn.commit()
    return inserted


def load_menu_items(engine, area_name: str) -> int:
    records = load_processed("deliveroo", area_name)
    if not records:
        return 0

    inserted = 0
    with engine.connect() as conn:
        for r in records:
            items = r.get("menu_items", [])
            for item in items:
                try:
                    conn.execute(text("""
                        INSERT INTO menu_items (
                            restaurant_name, neighbourhood, item_name,
                            item_price, item_category, item_description,
                            is_popular, dietary_tags
                        ) VALUES (
                            :restaurant_name, :neighbourhood, :item_name,
                            :item_price, :item_category, :item_description,
                            :is_popular, :dietary_tags
                        )
                    """), {
                        "restaurant_name": r.get("name"),
                        "neighbourhood": r.get("neighbourhood"),
                        "item_name": item.get("name"),
                        "item_price": item.get("price"),
                        "item_category": item.get("category"),
                        "item_description": item.get("description"),
                        "is_popular": item.get("is_popular", False),
                        "dietary_tags": item.get("dietary_tags", []),
                    })
                    inserted += 1
                except Exception as e:
                    continue
        conn.commit()
    return inserted


# ==================================================================
# Main runner
# ==================================================================

def run_postgres_loading(uri: str = DATABASE_URL):
    from config import DATABASE_URL, MONGO_URL, TARGET_AREAS

    print(f"\n{'='*60}")
    print(f"  PHASE 4 — STEP 4: POSTGRESQL LOADING")
    print(f"{'='*60}")

    try:
        engine = get_engine(uri)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"  Connected to PostgreSQL\n")
    except Exception as e:
        print(f"  ERROR: Cannot connect to PostgreSQL: {e}")
        print(f"  Make sure Docker is running: docker-compose up -d postgres")
        return

    create_schema(engine)

    loaders = [
        ("restaurants", load_restaurants),
        ("hygiene_ratings", load_hygiene),
        ("demographics", load_demographics),
        ("menu_items", load_menu_items),
    ]

    total = 0
    for table, loader in loaders:
        print(f"\n--- {table} ---")
        for area in TARGET_AREAS:
            run_id = generate_run_id()
            count = loader(engine, area["name"])
            total += count
            print(f"  {area['name']}: {count} records")

            log_transformation(
                run_id=run_id,
                source_file=f"processed/{table}/{area['name']}",
                destination_table=f"postgresql/{table}",
                records_in=count,
                records_out=count,
                transformations=["loaded_to_postgresql"],
            )

    print(f"\n{'='*60}")
    print(f"  DONE: {total} total records loaded")
    print(f"{'='*60}\n")

    # Table counts
    print("  Table counts:")
    with engine.connect() as conn:
        for table, _ in loaders:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"  {table:<25} {count:>6} rows")


if __name__ == "__main__":
    run_postgres_loading()