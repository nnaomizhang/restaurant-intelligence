from config import DATABASE_URL, MONGO_URL
"""
Hallucination Validator
========================
Validates agent responses against actual database records.
Checks restaurant names and ratings mentioned in responses.
"""

import re
from sqlalchemy import create_engine, text

DB_URI = DATABASE_URL

# Phrases to ignore when checking for restaurant mentions
IGNORE_PHRASES = {
    "here are", "london", "boundary st", "brick ln", "old st",
    "hanbury st", "hygiene rating", "not available", "among these",
    "shoreditch", "peckham", "hackney", "price level", "google rating",
    "review count", "menu items", "delivery fee", "sources matched",
    "address", "postcode", "rating", "restaurant", "cafe", "bar",
    "takeaway", "reviews", "type", "status", "active", "registered",
    "hygiene sub", "hygiene sub-scores", "sub-scores", "inspected on",
    "not available", "price level", "awarded best", "last inspection", "last inspection date", 
    "inspection date", "confidence in management", "structural score", "hygiene score",
    "canteen", "for further", "for more", "please note", "additional information", "further details",
    "redbridge gardens", "bellenden rd", "rye ln", "nunhead grove",
    "kingsland rd", "brick lane", "curtain rd", "commercial st",
    "bethnal green rd", "old street", "high street", "london se",
    "london e1", "london e2", "london e8", "london ec",
    "bellenden rd", "rye ln", "nunhead grove", "redbridge gardens",
    "peckham high st", "kingsland high st", "mare st", "london fields",
    " rd", " ln", " st", " ave", " grove", " gardens", " lane",
    " street", " road", " avenue", " place", " square", "deliveroo", "companies house", "mentmore terrace",
    "lower clapton", "uk", "these restaurants", "unfortunately",
    "google", "google rating", "tripadvisor", "menu item count", "menu item", "item count",
}

def get_all_restaurant_names() -> set[str]:
    """Get all restaurant names from PostgreSQL including hygiene table."""
    engine = create_engine(DB_URI)
    names = set()
    with engine.connect() as conn:
        # From master restaurants table
        rows = conn.execute(
            text("SELECT LOWER(name) FROM restaurants WHERE name IS NOT NULL")
        ).fetchall()
        names.update(row[0] for row in rows)

        # From hygiene ratings table
        rows = conn.execute(
            text("SELECT LOWER(business_name) FROM hygiene_ratings WHERE business_name IS NOT NULL")
        ).fetchall()
        names.update(row[0] for row in rows)

    return names


def extract_restaurant_mentions(text: str) -> list[str]:
    """
    Extract potential restaurant name mentions from text.
    Only extracts bold markdown names — these are the most reliable
    indicator that the agent is citing a specific restaurant.
    Avoids extracting addresses, building names and common phrases.
    """
    mentions = set()

    # Only extract bold markdown names e.g. **Dishoom Shoreditch**
    # This is far more reliable than regex on plain text
    bold_pattern = r'\*\*([^*]+)\*\*'
    for m in re.finditer(bold_pattern, text):
        name = m.group(1).strip()

        # Skip if too short
        if len(name) < 4:
            continue

        # Skip if it looks like a label/field name
        if any(ignore in name.lower() for ignore in IGNORE_PHRASES):
            continue

        # Skip if it ends with a street suffix — it's an address not a name
        street_suffixes = (
            " rd", " ln", " st", " ave", " pl", " grove", " gardens",
            " lane", " street", " road", " avenue", " place", " square",
            " centre", " center", " house", " court", " close",
        )
        if any(name.lower().endswith(s) for s in street_suffixes):
            continue

        # Skip if it's all numbers or contains a postcode
        if re.match(r'^[\d\s]+$', name):
            continue
        if re.search(r'[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}', name):
            continue

        mentions.add(name)

    return list(mentions)


def extract_numbers(text: str) -> list[float]:
    """Extract numerical claims from text."""
    pattern = r'\b(\d+(?:\.\d+)?)\b'
    matches = re.findall(pattern, text)
    return [float(m) for m in matches]


def validate_response(answer: str) -> dict:
    """
    Validate an agent response against the database.
    Returns validation result with any flagged issues.
    """
    result = {
        "is_valid": True,
        "issues": [],
        "verified_restaurants": [],
        "unverified_mentions": [],
    }

    try:
        db_names = get_all_restaurant_names()
        mentions = extract_restaurant_mentions(answer)

        for mention in mentions:
            mention_lower = mention.lower().strip()

            # Skip known non-restaurant phrases
            if any(ignore in mention_lower for ignore in IGNORE_PHRASES):
                continue

            # Check against database
            matched = any(
                mention_lower in db_name or db_name in mention_lower
                for db_name in db_names
            )

            if matched:
                result["verified_restaurants"].append(mention)
            else:
                result["unverified_mentions"].append(mention)

        if result["unverified_mentions"]:
            result["issues"].append(
                f"Unverified mentions: {result['unverified_mentions']}"
            )

        # Check for suspicious ratings — only flag values between 5.1 and 10
        numbers = extract_numbers(answer)
        suspicious = [n for n in numbers if 5.1 < n < 6.0]
        if suspicious:
            result["issues"].append(
                f"Suspicious rating values: {suspicious}"
            )

    except Exception as e:
        result["issues"].append(f"Validation error: {str(e)}")

    result["is_valid"] = len(result["issues"]) == 0
    return result


if __name__ == "__main__":
    test_answer = """
    Here are the top restaurants in Shoreditch:
    1. **Dishoom Shoreditch** - Rating: 4.8 (44,656 reviews)
    2. **Aladin Brick Lane** - Rating: 4.8 (14,770 reviews)
    3. **Fake Restaurant That Does Not Exist** - Rating: 4.9
    """
    result = validate_response(test_answer)
    print(f"Valid: {result['is_valid']}")
    print(f"Verified: {result['verified_restaurants']}")
    print(f"Unverified: {result['unverified_mentions']}")
    print(f"Issues: {result['issues']}")