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

from config import DATABASE_URL, MONGO_URL, PROCESSED_DIR, CHROMA_DB_DIR, CHROMA_COLLECTION_NAME

DB_URI = DATABASE_URL
MONGO_URI = MONGO_URL


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

# ==================================================================
# Tool 9 — Sentiment analysis
# ==================================================================

@tool
def get_sentiment_analysis(neighbourhood: str = "", cuisine: str = "") -> str:
    """
    Get sentiment analysis results for restaurants by neighbourhood or cuisine.
    Returns positive/negative/neutral review counts and average sentiment score.
    Use this when asked about customer satisfaction or review sentiment.
    """
    import json
    from config import DATABASE_URL, MONGO_URL, PROCESSED_DIR

    sentiment_path = PROCESSED_DIR / "sentiment_results.json"
    if not sentiment_path.exists():
        return json.dumps({"error": "Sentiment analysis not yet run"})

    with open(sentiment_path) as f:
        data = json.load(f)

    result = {}

    if neighbourhood:
        area_data = data.get("by_neighbourhood", {})
        matching = {k: v for k, v in area_data.items()
                   if neighbourhood.lower() in k.lower()}
        result["by_neighbourhood"] = matching

    if cuisine:
        cuisine_data = data.get("by_cuisine", {})
        matching = {k: v for k, v in cuisine_data.items()
                   if cuisine.lower() in k.lower()}
        result["by_cuisine"] = matching

    if not neighbourhood and not cuisine:
        result = {
            "by_neighbourhood": data.get("by_neighbourhood", {}),
            "by_cuisine": data.get("by_cuisine", {}),
            "total_reviews": data.get("total_reviews", 0),
        }

    return json.dumps(result)


# ==================================================================
# Tool 10 — Demand analysis
# ==================================================================

@tool
def get_demand_analysis(neighbourhood: str = "") -> str:
    """
    Get market demand scores for neighbourhoods.
    Returns demand score, supply score, opportunity score and key metrics.
    Use this for market analysis or investment opportunity questions.
    """
    import json
    from config import DATABASE_URL, MONGO_URL, PROCESSED_DIR

    demand_path = PROCESSED_DIR / "demand_scores.json"
    if not demand_path.exists():
        return json.dumps({"error": "Demand analysis not yet run"})

    with open(demand_path) as f:
        data = json.load(f)

    if neighbourhood:
        matching = {k: v for k, v in data.items()
                   if neighbourhood.lower() in k.lower()}
        return json.dumps(matching)

    return json.dumps(data)


# ==================================================================
# Tool 11 — Catchment analysis
# ==================================================================

@tool
def get_catchment_analysis(restaurant_name: str) -> str:
    """
    Get catchment zone analysis for a specific restaurant.
    Returns competitor counts within walking, cycling and delivery zones.
    Use this for competitive positioning questions.
    """
    import json
    from config import DATABASE_URL, MONGO_URL, PROCESSED_DIR

    catchment_path = PROCESSED_DIR / "catchment_results.json"
    if not catchment_path.exists():
        return json.dumps({"error": "Catchment analysis not yet run"})

    with open(catchment_path) as f:
        data = json.load(f)

    matching = {k: v for k, v in data.items()
               if restaurant_name.lower() in k.lower()}

    if not matching:
        return json.dumps({"error": f"No catchment data found for {restaurant_name}"})

    return json.dumps(matching)

# ==================================================================
# Tool 12 — Transport accessibility
# ==================================================================

@tool
def get_transport_accessibility(neighbourhood: str = "", min_score: float = 0.0) -> str:
    """
    Get transport accessibility scores for restaurants.
    Returns nearest TfL station, distance and transport score.
    Use this when asked about accessibility, footfall potential,
    or transport links for restaurants.
    """
    engine = get_pg()
    conditions = ["nearest_station IS NOT NULL"]
    params = {"limit": 20}

    if neighbourhood:
        conditions.append("neighbourhood ILIKE :neighbourhood")
        params["neighbourhood"] = f"%{neighbourhood}%"

    if min_score > 0:
        conditions.append("transport_score >= :min_score")
        params["min_score"] = min_score

    sql = f"""
        SELECT name, neighbourhood, nearest_station,
               nearest_station_distance_km, nearest_station_lines,
               transport_score, google_rating
        FROM restaurants
        WHERE {" AND ".join(conditions)}
        ORDER BY transport_score DESC
        LIMIT :limit
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    results = [dict(row._mapping) for row in rows]
    return json.dumps(results, default=str)

# ==================================================================
# Tool 13 — Opening hours and trading pattern analysis
# ==================================================================

@tool
def get_trading_patterns(neighbourhood: str = "", pattern: str = "") -> str:
    """
    Get restaurant trading patterns and opening hours analysis.
    Patterns: standard, family_restaurant, breakfast_cafe, all_day_dining,
    late_night, business_dining, dinner_restaurant.
    Use this when asked about opening times, target demographics,
    working professionals, families, or late night dining.
    """
    engine = get_pg()
    conditions = ["trading_pattern IS NOT NULL"]
    params = {"limit": 20}

    if neighbourhood:
        conditions.append("neighbourhood ILIKE :neighbourhood")
        params["neighbourhood"] = f"%{neighbourhood}%"

    if pattern:
        conditions.append("trading_pattern ILIKE :pattern")
        params["pattern"] = f"%{pattern}%"

    sql = f"""
        SELECT name, neighbourhood, trading_pattern, customer_segments,
               days_open, avg_open_time, avg_close_time,
               open_weekends, open_weekdays, google_rating
        FROM restaurants
        WHERE {" AND ".join(conditions)}
        ORDER BY google_rating DESC NULLS LAST
        LIMIT :limit
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    results = [dict(row._mapping) for row in rows]

    # Also get pattern summary
    summary_sql = """
        SELECT trading_pattern, COUNT(*) as count,
               AVG(google_rating) as avg_rating
        FROM restaurants
        WHERE trading_pattern IS NOT NULL
    """
    summary_params = {}
    if neighbourhood:
        summary_sql += " AND neighbourhood ILIKE :neighbourhood"
        summary_params["neighbourhood"] = f"%{neighbourhood}%"
    summary_sql += " GROUP BY trading_pattern ORDER BY count DESC"

    with engine.connect() as conn:
        summary_rows = conn.execute(text(summary_sql), summary_params).fetchall()

    summary = [dict(row._mapping) for row in summary_rows]

    return json.dumps({
        "summary": summary,
        "restaurants": results,
    }, default=str)

ALL_TOOLS = [
    search_restaurants,
    get_hygiene_rating,
    search_reviews,
    get_demographics,
    get_menu_items,
    get_company_info,
    compare_neighbourhoods,
    get_top_restaurants,
    get_sentiment_analysis,
    get_demand_analysis,
    get_catchment_analysis,
    get_transport_accessibility,
    get_trading_patterns,
]

