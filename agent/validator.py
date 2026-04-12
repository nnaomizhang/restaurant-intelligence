"""
Hallucination Validator
========================
Validates agent responses by checking that named restaurants
actually exist in the database.

Uses OpenAI to extract restaurant names intelligently —
far more reliable than regex pattern matching.
"""

import json
import re
from openai import OpenAI
from sqlalchemy import create_engine, text
from config import DATABASE_URL, OPENAI_API_KEY

DB_URI = DATABASE_URL

import unicodedata

def normalise_unicode(text: str) -> str:
    """Normalise unicode characters for matching — ü→u, é→e etc."""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower().strip()

def get_all_restaurant_names() -> set[str]:
    """Get all restaurant and company names from PostgreSQL, FSA and MongoDB."""
    engine = create_engine(DB_URI)
    names = set()

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT LOWER(name) FROM restaurants WHERE name IS NOT NULL")
        ).fetchall()
        for row in rows:
            names.add(row[0])
            names.add(normalise_unicode(row[0]))

        rows = conn.execute(
            text("SELECT LOWER(business_name) FROM hygiene_ratings WHERE business_name IS NOT NULL")
        ).fetchall()
        for row in rows:
            names.add(row[0])
            names.add(normalise_unicode(row[0]))

    try:
        from pymongo import MongoClient
        from config import MONGO_URL
        client = MongoClient(MONGO_URL)
        db = client["restaurant_intelligence"]
        for doc in db["companies_house"].find({}, {"name": 1}):
            name = doc.get("name", "")
            if name:
                names.add(name.lower())
                names.add(normalise_unicode(name))
    except Exception:
        pass

    return names


def extract_restaurant_mentions(text: str) -> list[str]:
    """
    Use OpenAI to extract restaurant names from agent response.
    Much more reliable than regex — the LLM understands context.
    """
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract only specific restaurant/business names from the text. "
                        "Return a JSON array of strings. "
                        "Do NOT include: field labels, metrics, demographic terms, "
                        "cuisine types, neighbourhood names, section headers, "
                        "or any text that is not a specific named restaurant. "
                        "Examples of what NOT to include: 'Demand Score', 'Economic Activity', "
                        "'Italian Cuisine', 'Young Professionals', 'Market Signals', "
                        "'Shoreditch', 'Peckham', 'Address', 'Status', 'Location'. "
                        "Return [] if no restaurant names found. "
                        "Return ONLY the JSON array, nothing else."
                    )
                },
                {
                    "role": "user",
                    "content": text[:2000]  # limit to avoid token costs
                }
            ],
            max_tokens=200,
        )

        raw = response.choices[0].message.content.strip()
        # Clean JSON fences if present
        raw = re.sub(r'```json|```', '', raw).strip()
        names = json.loads(raw)
        return [n for n in names if isinstance(n, str) and len(n) > 2]

    except Exception as e:
        # Fall back to empty list on error — don't fail validation
        return []


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
            mention_normalised = normalise_unicode(mention)
            
            matched = any(
                mention_lower in db_name or db_name in mention_lower or
                mention_normalised in db_name or db_name in mention_normalised
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

        # Flag suspicious ratings between 5.1 and 6.0
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
    1. **Dishoom Shoreditch** - Rating: 4.8
    2. **Aladin Brick Lane** - Rating: 4.8
    3. **Fake Restaurant XYZ** - Rating: 4.9

    ### Market Analysis
    - **Demand Score**: 0.812
    - **Economic Activity**: 63.9%
    - **Young Professionals (25-34 years)**: 28.0%
    - **Cuisine Gaps**: Italian, Mexican
    """
    result = validate_response(test_answer)
    print(f"Valid: {result['is_valid']}")
    print(f"Verified: {result['verified_restaurants']}")
    print(f"Unverified: {result['unverified_mentions']}")
    print(f"Issues: {result['issues']}")