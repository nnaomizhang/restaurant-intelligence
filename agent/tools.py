"""
Agent Tools
===========
Eight tools the agent can call to retrieve restaurant data.
Each tool queries PostgreSQL, MongoDB, or ChromaDB.
"""

from langchain.tools import tool
from sqlalchemy import create_engine, text
from pymongo import MongoClient
import chromadb
import json

from config import PROCESSED_DIR, CHROMA_DB_DIR, CHROMA_COLLECTION_NAME

DB_URI = "postgresql://user:password@localhost:5432/restaurants"
MONGO_URI = "mongodb://localhost:27017"


def get_pg():
    return create_engine(DB_URI)


def get_mongo():
    client = MongoClient(MONGO_URI)
    return client["restaurant_intelligence"]


def get_chroma():
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    return client.get_collection(CHROMA_COLLECTION_NAME)


# ==================================================================
# Tool 1 — Search restaurants
# ==================================================================

@tool
def search_restaurants(neighbourhood: str = "", min_rating: float = 0.0, limit: int = 10) -> str:
    """
    Search for restaurants by neighbourhood and minimum rating.
    Returns name, rating, hygiene rating, address and sources matched.
    Use this for general restaurant queries.
    """
    engine = get_pg()
    conditions = ["1=1"]
    params = {"limit": limit}

    if neighbourhood:
        conditions.append("neighbourhood ILIKE :neighbourhood")
        params["neighbourhood"] = f"%{neighbourhood}%"

    if min_rating > 0:
        conditions.append("google_rating >= :min_rating")
        params["min_rating"] = min_rating

    sql = f"""
        SELECT name, neighbourhood, address, postcode,
               google_rating, google_review_count, google_price_level,
               business_type, company_status, menu_item_count,
               sources_matched
        FROM restaurants
        WHERE {" AND ".join(conditions)}
        ORDER BY google_rating DESC NULLS LAST
        LIMIT :limit
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    results = [dict(row._mapping) for row in rows]
    return json.dumps(results, default=str)


# ==================================================================
# Tool 2 — Get hygiene rating
# ==================================================================

@tool
def get_hygiene_rating(restaurant_name: str, neighbourhood: str = "") -> str:
    """
    Get FSA hygiene rating for a specific restaurant.
    Returns rating (0-5), inspection date, and sub-scores.
    Use this when asked about food safety or hygiene.
    """
    engine = get_pg()
    params = {"name": f"%{restaurant_name}%"}
    conditions = ["business_name ILIKE :name"]

    if neighbourhood:
        conditions.append("neighbourhood ILIKE :neighbourhood")
        params["neighbourhood"] = f"%{neighbourhood}%"

    sql = f"""
        SELECT business_name, address, postcode, neighbourhood,
               rating_value, rating_date, business_type,
               score_hygiene, score_structural, score_management
        FROM hygiene_ratings
        WHERE {" AND ".join(conditions)}
        ORDER BY rating_value DESC
        LIMIT 5
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    results = [dict(row._mapping) for row in rows]
    return json.dumps(results, default=str)


# ==================================================================
# Tool 3 — Semantic search reviews
# ==================================================================

@tool
def search_reviews(query: str, neighbourhood: str = "", n_results: int = 5) -> str:
    """
    Semantically search restaurant reviews and descriptions.
    Use this for queries like 'find cosy Italian restaurants' or
    'restaurants with great atmosphere'.
    """
    collection = get_chroma()

    where = {"neighbourhood": {"$in": ["Shoreditch", "Peckham", "Hackney"]}}
    if neighbourhood:
        where = {"neighbourhood": neighbourhood}

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where if neighbourhood else None,
    )

    output = []
    for i, meta in enumerate(results["metadatas"][0]):
        output.append({
            "name": meta.get("name"),
            "neighbourhood": meta.get("neighbourhood"),
            "google_rating": meta.get("google_rating"),
            "hygiene_rating": meta.get("hygiene_rating"),
            "postcode": meta.get("postcode"),
            "relevance_score": round(1 - results["distances"][0][i], 3) if results.get("distances") else None,
        })

    return json.dumps(output)


# ==================================================================
# Tool 4 — Get demographics
# ==================================================================

@tool
def get_demographics(neighbourhood: str) -> str:
    """
    Get demographic data for a neighbourhood.
    Returns population, age distribution, economic activity,
    and household composition. Use this for market analysis questions.
    """
    engine = get_pg()

    with engine.connect() as conn:
        rows = conn.execute(text("""
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
        """), {"neighbourhood": f"%{neighbourhood}%"}).fetchall()

    results = [dict(row._mapping) for row in rows]
    return json.dumps(results, default=str)


# ==================================================================
# Tool 5 — Get menu items
# ==================================================================

@tool
def get_menu_items(restaurant_name: str, neighbourhood: str = "") -> str:
    """
    Get menu items for a restaurant from Deliveroo data.
    Returns dish names, prices, categories and dietary tags.
    Use this when asked about what a restaurant serves or pricing.
    """
    engine = get_pg()
    params = {"name": f"%{restaurant_name}%"}
    conditions = ["restaurant_name ILIKE :name"]

    if neighbourhood:
        conditions.append("neighbourhood ILIKE :neighbourhood")
        params["neighbourhood"] = f"%{neighbourhood}%"

    sql = f"""
        SELECT restaurant_name, neighbourhood, item_name,
               item_price, item_category, item_description,
               is_popular, dietary_tags
        FROM menu_items
        WHERE {" AND ".join(conditions)}
        ORDER BY item_price ASC
        LIMIT 20
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    results = [dict(row._mapping) for row in rows]
    return json.dumps(results, default=str)


# ==================================================================
# Tool 6 — Get company information
# ==================================================================

@tool
def get_company_info(restaurant_name: str, neighbourhood: str = "") -> str:
    """
    Get Companies House registration data for a restaurant.
    Returns company status, incorporation date, and distress signals.
    Use this for questions about business health or legitimacy.
    """
    db = get_mongo()
    query = {"name": {"$regex": restaurant_name, "$options": "i"}}

    if neighbourhood:
        query["neighbourhood"] = {"$regex": neighbourhood, "$options": "i"}

    records = list(db["companies_house"].find(query, {"_id": 0}).limit(5))
    return json.dumps(records, default=str)


# ==================================================================
# Tool 7 — Compare neighbourhoods
# ==================================================================

@tool
def compare_neighbourhoods(metric: str = "restaurants") -> str:
    """
    Compare Shoreditch, Peckham and Hackney across a metric.
    Metric can be: restaurants, hygiene, demographics, menu_prices.
    Use this for comparative analysis questions.
    """
    engine = get_pg()
    neighbourhoods = ["Shoreditch", "Peckham", "Hackney"]
    results = {}

    for area in neighbourhoods:
        if metric == "restaurants":
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT
                        COUNT(*) as total,
                        AVG(google_rating) as avg_rating,
                        AVG(google_price_level) as avg_price_level,
                        COUNT(CASE WHEN menu_item_count > 0 THEN 1 END) as on_deliveroo
                    FROM restaurants
                    WHERE neighbourhood = :area
                """), {"area": area}).fetchone()
            results[area] = dict(row._mapping) if row else {}

        elif metric == "hygiene":
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT
                        COUNT(*) as total,
                        AVG(rating_value) as avg_hygiene_rating,
                        COUNT(CASE WHEN rating_value = 5 THEN 1 END) as five_star_count,
                        COUNT(CASE WHEN rating_value < 3 THEN 1 END) as low_rating_count
                    FROM hygiene_ratings
                    WHERE neighbourhood = :area
                """), {"area": area}).fetchone()
            results[area] = dict(row._mapping) if row else {}

        elif metric == "demographics":
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT
                        SUM(total_population) as total_population,
                        AVG(age_25_34_pct) as avg_age_25_34,
                        AVG(economically_active_pct) as avg_economically_active,
                        AVG(household_single_pct) as avg_single_households
                    FROM demographics
                    WHERE neighbourhood = :area
                """), {"area": area}).fetchone()
            results[area] = dict(row._mapping) if row else {}

        elif metric == "menu_prices":
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT
                        COUNT(*) as total_items,
                        AVG(item_price) as avg_price,
                        MIN(item_price) as min_price,
                        MAX(item_price) as max_price
                    FROM menu_items
                    WHERE neighbourhood = :area
                """), {"area": area}).fetchone()
            results[area] = dict(row._mapping) if row else {}

    return json.dumps(results, default=str)


# ==================================================================
# Tool 8 — Get top rated restaurants
# ==================================================================

@tool
def get_top_restaurants(neighbourhood: str = "", category: str = "", limit: int = 5) -> str:
    """
    Get top rated restaurants optionally filtered by neighbourhood
    and business category. Returns ranked list with key metrics.
    Use this for 'best restaurant' type questions.
    """
    engine = get_pg()
    conditions = ["google_rating IS NOT NULL"]
    params = {"limit": limit}

    if neighbourhood:
        conditions.append("neighbourhood ILIKE :neighbourhood")
        params["neighbourhood"] = f"%{neighbourhood}%"

    if category:
        conditions.append("business_type ILIKE :category")
        params["category"] = f"%{category}%"

    sql = f"""
        SELECT name, neighbourhood, address, postcode,
               google_rating, google_review_count,
               google_price_level, business_type,
               company_status, menu_item_count
        FROM restaurants
        WHERE {" AND ".join(conditions)}
        ORDER BY google_rating DESC, google_review_count DESC
        LIMIT :limit
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    results = [dict(row._mapping) for row in rows]
    return json.dumps(results, default=str)


# All tools list
ALL_TOOLS = [
    search_restaurants,
    get_hygiene_rating,
    search_reviews,
    get_demographics,
    get_menu_items,
    get_company_info,
    compare_neighbourhoods,
    get_top_restaurants,
]