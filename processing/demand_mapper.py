"""
Demand Mapper
=============
Scores restaurant market demand per neighbourhood using:
- Population density
- Age demographics (25-34 key dining demographic)
- Economic activity
- Restaurant density (supply vs demand gap)
- Deliveroo presence (delivery demand)
- Review volume (engagement)
- Sentiment scores
"""

import json
from sqlalchemy import create_engine, text
from pathlib import Path
from config import DATABASE_URL, MONGO_URL, PROCESSED_DIR

DB_URI = DATABASE_URL


def get_engine():
    return create_engine(DB_URI)


def calculate_demand_scores() -> dict:
    """Calculate demand scores for each neighbourhood."""
    engine = get_engine()
    neighbourhoods = ["Shoreditch", "Peckham", "Hackney"]
    scores = {}

    for area in neighbourhoods:
        with engine.connect() as conn:
            # Restaurant metrics
            rest = conn.execute(text("""
                SELECT
                    COUNT(*) as total_restaurants,
                    AVG(google_rating) as avg_rating,
                    SUM(google_review_count) as total_reviews,
                    COUNT(CASE WHEN menu_item_count > 0 THEN 1 END) as on_deliveroo,
                    AVG(google_price_level) as avg_price_level
                FROM restaurants
                WHERE neighbourhood = :area
                AND google_rating IS NOT NULL
            """), {"area": area}).fetchone()

            # Demographics
            demo = conn.execute(text("""
                SELECT
                    SUM(total_population) as population,
                    AVG(population_density) as density,
                    AVG(age_25_34_pct) as age_25_34,
                    AVG(economically_active_pct) as econ_active,
                    AVG(household_single_pct) as single_household
                FROM demographics
                WHERE neighbourhood = :area
            """), {"area": area}).fetchone()

            # Hygiene
            hygiene = conn.execute(text("""
                SELECT AVG(rating_value) as avg_hygiene
                FROM hygiene_ratings
                WHERE neighbourhood = :area
                AND rating_value IS NOT NULL
            """), {"area": area}).fetchone()

        r = dict(rest._mapping) if rest else {}
        d = dict(demo._mapping) if demo else {}
        h = dict(hygiene._mapping) if hygiene else {}

        # Load sentiment
        sentiment_score = 0.5
        sentiment_path = PROCESSED_DIR / "sentiment_results.json"
        if sentiment_path.exists():
            with open(sentiment_path) as f:
                sentiment_data = json.load(f)
            area_sentiment = sentiment_data.get("by_neighbourhood", {}).get(area, {})
            sentiment_score = area_sentiment.get("avg_score", 0.5)

        # Normalise scores 0-1
        def safe(val, default=0):
            return float(val) if val is not None else default

        population = safe(d.get("population"), 200000)
        density = safe(d.get("density"), 10000)
        age_25_34 = safe(d.get("age_25_34"), 20)
        econ_active = safe(d.get("econ_active"), 60)
        single_hh = safe(d.get("single_household"), 30)

        total_restaurants = safe(r.get("total_restaurants"), 100)
        avg_rating = safe(r.get("avg_rating"), 4.0)
        total_reviews = safe(r.get("total_reviews"), 1000)
        on_deliveroo = safe(r.get("on_deliveroo"), 5)
        avg_price = safe(r.get("avg_price_level"), 2.0)
        avg_hygiene = safe(h.get("avg_hygiene"), 4.0)

        # Demand indicators
        demand_components = {
            "population_score": min(population / 400000, 1.0),
            "density_score": min(density / 25000, 1.0),
            "young_professional_score": min(age_25_34 / 35, 1.0),
            "economic_activity_score": min(econ_active / 80, 1.0),
            "single_household_score": min(single_hh / 50, 1.0),
            "review_volume_score": min(total_reviews / 500000, 1.0),
            "delivery_demand_score": min(on_deliveroo / 20, 1.0),
            "sentiment_score": max(0, min(sentiment_score, 1.0)),
        }

        # Weighted demand score
        demand_score = (
            demand_components["population_score"] * 0.15 +
            demand_components["density_score"] * 0.15 +
            demand_components["young_professional_score"] * 0.20 +
            demand_components["economic_activity_score"] * 0.15 +
            demand_components["single_household_score"] * 0.10 +
            demand_components["review_volume_score"] * 0.10 +
            demand_components["delivery_demand_score"] * 0.05 +
            demand_components["sentiment_score"] * 0.10
        )

        # Cuisine gap analysis — what cuisines are underrepresented?
        sentiment_path = PROCESSED_DIR / "sentiment_results.json"
        cuisine_gaps = {}
        if sentiment_path.exists():
            with open(sentiment_path) as f:
                sent_data = json.load(f)
            cuisine_data = sent_data.get("by_cuisine", {})
            for cuisine, cdata in cuisine_data.items():
                if cuisine == "Other":
                    continue
                positive_rate = cdata.get("positive", 0) / max(cdata.get("total", 1), 1)
                # High positive sentiment + low review count = underserved demand
                gap_score = round(positive_rate * (1 - min(cdata.get("total", 0) / 100, 1)), 3)
                cuisine_gaps[cuisine] = {
                    "positive_rate": round(positive_rate, 3),
                    "review_count": cdata.get("total", 0),
                    "gap_score": gap_score,
                    "reliable": cdata.get("reliable", False),
                }

        # Market signals — meaningful indicators for investors
        market_signals = []
        if age_25_34 > 25:
            market_signals.append(f"Strong 25-34 demographic ({round(age_25_34, 1)}%) — high dining out propensity")
        if econ_active > 65:
            market_signals.append(f"High economic activity ({round(econ_active, 1)}%) — discretionary spending capacity")
        if single_hh > 35:
            market_signals.append(f"High single household rate ({round(single_hh, 1)}%) — frequent restaurant users")
        if sentiment_score > 0.7:
            market_signals.append(f"Strong review sentiment ({round(sentiment_score, 3)}) — positive dining culture")
        if on_deliveroo < 10:
            market_signals.append(f"Low Deliveroo penetration ({int(on_deliveroo)} restaurants) — delivery market opportunity")
        if avg_rating > 4.3:
            market_signals.append(f"High average rating ({avg_rating}) — quality-conscious market")

        scores[area] = {
            "demand_score": round(demand_score, 3),
            "market_signals": market_signals,
            "cuisine_gaps": cuisine_gaps,
            "demand_components": {k: round(v, 3) for k, v in demand_components.items()},
            "raw_metrics": {
                "population": int(population),
                "total_restaurants": int(total_restaurants),
                "avg_rating": round(avg_rating, 2),
                "total_reviews": int(total_reviews),
                "on_deliveroo": int(on_deliveroo),
                "avg_hygiene": round(avg_hygiene, 2),
                "sentiment": round(sentiment_score, 3),
                "age_25_34_pct": round(age_25_34, 1),
                "econ_active_pct": round(econ_active, 1),
                "single_household_pct": round(single_hh, 1),
            }
        }

    # Save results
    output_path = PROCESSED_DIR / "demand_scores.json"
    with open(output_path, "w") as f:
        json.dump(scores, f, indent=2)

    print(f"\n{'='*60}")
    print("  DEMAND MAPPER RESULTS")
    print("="*60)
    for area, data in scores.items():
        print(f"\n  {area}:")
        print(f"    Demand score:      {data['demand_score']:.3f}")
        print(f"    Market signals:    {len(data['market_signals'])}")
        for signal in data['market_signals']:
            print(f"      - {signal}")
        print(f"    Cuisine gaps:")
        gaps = sorted(data['cuisine_gaps'].items(), key=lambda x: -x[1]['gap_score'])
        for cuisine, gap in gaps[:3]:
            print(f"      {cuisine}: gap_score={gap['gap_score']}, reliable={gap['reliable']}")

    return scores


if __name__ == "__main__":
    calculate_demand_scores()