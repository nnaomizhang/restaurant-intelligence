"""
Centralised configuration for the Restaurant Intelligence Platform.
All modules import paths, API keys, and constants from here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
LOGS_DIR = ROOT_DIR / "logs"
DB_PATH = ROOT_DIR / "restaurant_intel.db"

for d in [RAW_DIR, PROCESSED_DIR, LOGS_DIR,
          RAW_DIR / "deliveroo", RAW_DIR / "google_places",
          RAW_DIR / "fsa", RAW_DIR / "companies_house",
          RAW_DIR / "planning", RAW_DIR / "ons_census"]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv(Path(__file__).resolve().parent / ".env")

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
COMPANIES_HOUSE_API_KEY = os.getenv("COMPANIES_HOUSE_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# Target areas — edit these for your chosen neighbourhoods
# ---------------------------------------------------------------------------
TARGET_AREAS = [
    {
        "name": "Shoreditch",
        "postcode_prefix": "E1",
        "lat": 51.5246,
        "lng": -0.0780,
        "radius_km": 1.5,
        "local_authority": "Tower Hamlets",
        "deliveroo_slug": "london/shoreditch",
    },
    {
        "name": "Peckham",
        "postcode_prefix": "SE15",
        "lat": 51.4738,
        "lng": -0.0690,
        "radius_km": 1.5,
        "local_authority": "Southwark",
        "deliveroo_slug": "london/peckham",
    },
    {
        "name": "Hackney",
        "postcode_prefix": "E8",
        "lat": 51.5450,
        "lng": -0.0553,
        "radius_km": 1.5,
        "local_authority": "Hackney",
        "deliveroo_slug": "london/hackney",
    },
]

# ---------------------------------------------------------------------------
# Model / DB settings
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHROMA_COLLECTION_NAME = "restaurant_reviews"
CHROMA_DB_DIR = str(ROOT_DIR / "chroma_db")
LLM_MODEL = "gpt-4o"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/restaurants")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")