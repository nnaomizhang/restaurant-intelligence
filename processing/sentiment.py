"""
Sentiment Analyser
==================
Analyses sentiment of restaurant reviews using transformers.
Groups results by cuisine type for cuisine-specific NLP.

Uses: cardiffnlp/twitter-roberta-base-sentiment-latest
A lightweight model that runs locally without API calls.
"""

import json
import re
from pathlib import Path
from collections import defaultdict

from transformers import pipeline
from sqlalchemy import create_engine, text

from config import DATABASE_URL, MONGO_URL, PROCESSED_DIR, LOGS_DIR

DB_URI = DATABASE_URL

# Cuisine keywords for classification
CUISINE_KEYWORDS = {
    "Indian": ["indian", "curry", "tandoor", "biryani", "masala", "tikka", "naan", "dal", "samosa"],
    "Chinese": ["chinese", "dim sum", "dumpling", "noodle", "wok", "szechuan", "cantonese"],
    "Italian": ["italian", "pizza", "pasta", "risotto", "tiramisu", "gelato", "trattoria"],
    "Japanese": ["japanese", "sushi", "ramen", "tempura", "izakaya", "miso", "udon", "sashimi"],
    "Thai": ["thai", "pad thai", "green curry", "tom yum", "satay", "thai basil"],
    "Mexican": ["mexican", "taco", "burrito", "guacamole", "enchilada", "quesadilla"],
    "American": ["burger", "bbq", "wings", "fried chicken", "hot dog", "diner"],
    "Mediterranean": ["mediterranean", "greek", "falafel", "hummus", "mezze", "lebanese"],
    "African": ["african", "west african", "nigerian", "ethiopian", "jollof"],
    "British": ["british", "pie", "fish and chips", "roast", "pub food", "english breakfast"],
}


def classify_cuisine(name: str, types: list) -> str:
    """Classify restaurant cuisine from name and Google types."""
    text_to_check = (name + " " + " ".join(types or [])).lower()
    for cuisine, keywords in CUISINE_KEYWORDS.items():
        if any(kw in text_to_check for kw in keywords):
            return cuisine
    return "Other"


def load_reviews_from_db() -> list[dict]:
    """Load all restaurant reviews from MongoDB via processed files."""
    reviews = []
    folder = PROCESSED_DIR / "google_places"
    if not folder.exists():
        return reviews

    for filepath in folder.glob("*.json"):
        with open(filepath, encoding="utf-8") as f:
            records = json.load(f)

        for restaurant in records:
            name = restaurant.get("name", "")
            neighbourhood = restaurant.get("neighbourhood", "")
            types = restaurant.get("types", [])
            cuisine = classify_cuisine(name, types)

            for review in restaurant.get("reviews", []):
                text = review.get("text", "").strip()
                if text and len(text) > 20:
                    reviews.append({
                        "restaurant_name": name,
                        "neighbourhood": neighbourhood,
                        "cuisine": cuisine,
                        "review_text": text[:512],
                        "review_rating": review.get("rating"),
                    })

    return reviews


def run_sentiment_analysis() -> dict:
    """
    Run sentiment analysis on all reviews.
    Returns results grouped by cuisine and neighbourhood.
    """
    print("\n" + "="*60)
    print("  SENTIMENT ANALYSIS")
    print("="*60)

    print("  Loading sentiment model...")
    sentiment_pipeline = pipeline(
        "sentiment-analysis",
        model="cardiffnlp/twitter-roberta-base-sentiment-latest",
        max_length=512,
        truncation=True,
    )

    reviews = load_reviews_from_db()
    print(f"  Loaded {len(reviews)} reviews")

    if not reviews:
        print("  No reviews found")
        return {}

    # Run sentiment analysis in batches
    batch_size = 32
    texts = [r["review_text"] for r in reviews]
    results = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        batch_results = sentiment_pipeline(batch)
        results.extend(batch_results)
        print(f"  Processed {min(i+batch_size, len(texts))}/{len(texts)} reviews")

    # Attach sentiment to reviews
    for review, sentiment in zip(reviews, results):
        label = sentiment["label"].lower()
        score = sentiment["score"]

        if "positive" in label:
            review["sentiment"] = "positive"
            review["sentiment_score"] = score
        elif "negative" in label:
            review["sentiment"] = "negative"
            review["sentiment_score"] = -score
        else:
            review["sentiment"] = "neutral"
            review["sentiment_score"] = 0.0

    # Aggregate by cuisine
    cuisine_sentiment = defaultdict(lambda: {
        "positive": 0, "negative": 0, "neutral": 0,
        "total": 0, "avg_score": 0.0, "scores": []
    })

    neighbourhood_sentiment = defaultdict(lambda: {
        "positive": 0, "negative": 0, "neutral": 0,
        "total": 0, "avg_score": 0.0, "scores": []
    })

    for review in reviews:
        cuisine = review["cuisine"]
        neighbourhood = review["neighbourhood"]
        sentiment = review["sentiment"]
        score = review["sentiment_score"]

        cuisine_sentiment[cuisine][sentiment] += 1
        cuisine_sentiment[cuisine]["total"] += 1
        cuisine_sentiment[cuisine]["scores"].append(score)

        neighbourhood_sentiment[neighbourhood][sentiment] += 1
        neighbourhood_sentiment[neighbourhood]["total"] += 1
        neighbourhood_sentiment[neighbourhood]["scores"].append(score)

    # Calculate averages
    for data in list(cuisine_sentiment.values()) + list(neighbourhood_sentiment.values()):
        if data["scores"]:
            data["avg_score"] = round(sum(data["scores"]) / len(data["scores"]), 3)
        del data["scores"]

    output = {
        "by_cuisine": dict(cuisine_sentiment),
        "by_neighbourhood": dict(neighbourhood_sentiment),
        "total_reviews": len(reviews),
        "reviews": reviews,
    }

    # Save results
    output_path = PROCESSED_DIR / "sentiment_results.json"
    save_output = {
        "by_cuisine": output["by_cuisine"],
        "by_neighbourhood": output["by_neighbourhood"],
        "total_reviews": output["total_reviews"],
    }
    with open(output_path, "w") as f:
        json.dump(save_output, f, indent=2)

    print(f"\n  Results by cuisine:")
    for cuisine, data in sorted(cuisine_sentiment.items(), key=lambda x: -x[1]["avg_score"]):
        print(f"    {cuisine:<15} avg_score: {data['avg_score']:>6.3f} | "
              f"+{data['positive']} -{data['negative']} ={data['neutral']}")

    print(f"\n  Results by neighbourhood:")
    for area, data in neighbourhood_sentiment.items():
        print(f"    {area:<15} avg_score: {data['avg_score']:>6.3f} | "
              f"+{data['positive']} -{data['negative']} ={data['neutral']}")

    print(f"\n  Saved to {output_path}")
    print("="*60 + "\n")

    return output


if __name__ == "__main__":
    run_sentiment_analysis()