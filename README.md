# Restaurant Intelligence Platform 👨🏻‍🍳

Strategic market intelligence for London's restaurant scene — Shoreditch, Peckham and Hackney. Ask natural language questions across restaurant ratings, hygiene, company financials, delivery menus, transport accessibility and neighbourhood demographics.

Built for MSIN0166 Data Engineering Individual Coursework


---

## What it does

- Ingests data from 6 sources: Google Places, FSA, Companies House, Deliveroo, ONS Census, TfL
- Cleans, normalises and fuzzy-matches 2,518 records across sources
- Runs NLP sentiment analysis on 14,820+ reviews using RoBERTa
- Exposes a LangGraph ReAct agent (GPT-4o) with 13 specialist tools
- Validates every agent response for hallucinations — 20/20 test queries passing
- Serves a FastAPI REST layer with 10+ endpoints including SSE streaming
- Renders a 7-tab Streamlit dashboard for strategic restaurant investment analysis
- Runs fully in Docker Compose with persistent volumes and auto data loading


---

## Prerequisites

- Python 3.11+
- Docker Desktop
- Google Chrome (for Deliveroo scraping)
- API keys: Google Places, Companies House, OpenAI

---

## Quick start (recommended)

All processed data and embeddings are included in the repository — no data collection needed.

**1. Clone the repository**

```bash
git clone https://github.com/nnaomizhang/restaurant-intelligence.git
cd restaurant-intelligence
```

**2. Create `.env` in the project root**

GOOGLE_PLACES_API_KEY=your_key
COMPANIES_HOUSE_API_KEY=your_key
OPENAI_API_KEY=your_key
DATABASE_URL=postgresql://user:password@localhost:5432/restaurants
MONGO_URL=mongodb://localhost:27017

---

**3. Start Docker**

```bash
docker-compose up --build -d
```

The entrypoint automatically loads all processed data into PostgreSQL and MongoDB on first start. This takes ~2 minutes.

**4. Open the app**

- Frontend: http://localhost:8501
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health

That's it. No data collection required.

---

## Running locally (without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start databases
docker-compose up -d postgres mongodb

# Set env vars
export DATABASE_URL="postgresql://user:password@localhost:5432/restaurants"
export MONGO_URL="mongodb://localhost:27017"

# Load data
python -m processing.postgres_loader
python -m processing.mongo_loader
python -m collectors.tfl_enricher
python -m processing.hours_analyser
python -m processing.geo_analyser

# Terminal 1 — API
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend
streamlit run app/main.py
```

---

## Recollecting data (optional)

The repository includes all pre-collected data. Only run collectors if you want to refresh the data:

> Note: Deliveroo scraping requires Google Chrome. ONS Census CSV files must be downloaded manually from [Nomis](https://www.nomisweb.co.uk/).

> **ONS Census data:** Download the national LSOA CSV files from [Nomis](https://www.nomisweb.co.uk/) (Census 2021, LSOA level) and place them in `raw/ons_downloads/`:
> - `census2021-ts007a-lsoa.csv` — age
> - `census2021-ts021-lsoa.csv` — ethnicity  
> - `census2021-ts066-lsoa.csv` — economic activity
> - `census2021-ts003-lsoa.csv` — household composition
> - `census2021-ts006-lsoa.csv` — population density
>
> Then run the splitter to extract Shoreditch, Peckham and Hackney:
> ```bash
> python split_ons_lsoa_files.py
> ```
> This creates the per-area CSV files that `collectors/ons_census.py` expects.

> **Deliveroo scraping:** Requires Google Chrome installed on your machine.

```bash
# Requires Google Chrome for Deliveroo scraping
python run_collectors.py

# Then rerun processing pipeline
python -m processing.cleaner
python -m processing.matcher
python -m processing.postgres_loader
python -m processing.mongo_loader
python -m processing.embeddings
python -m processing.sentiment
python -m processing.demand_mapper
python -m processing.hours_analyser
python -m collectors.tfl_enricher
python -m processing.geo_analyser
python -m processing.catchment_modeller
```

---

## Tests

```bash
pytest tests/ -v
```

18 tests covering collectors, lineage and data completeness.

---

## Data sources

| Source | Method | Coverage |
|--------|--------|----------|
| Google Places | API | 1,225 restaurants, 14,820+ reviews |
| FSA | API | 1,724 hygiene ratings |
| Companies House | API | 90 companies |
| Deliveroo | Selenium scraping | 150 restaurants, 2,000+ menu items |
| ONS Census 2021 | CSV (Nomis) | 491 LSOAs |
| TfL | API | 959 stations |

---

## Architecture

7-layer pipeline:

1. **External sources** — Google Places, FSA, Companies House, Deliveroo, ONS, TfL
2. **Data ingestion** — Python collectors with lineage logging and PII sanitisation
3. **Data stores** — PostgreSQL (7 tables), MongoDB (6 collections), ChromaDB (1,216 embeddings)
4. **Agent** — LangGraph ReAct + GPT-4o, 13 tools, LLM hallucination validator, MCP server
5. **FastAPI** — 10+ REST endpoints with SSE streaming, Pydantic schemas, error handling
6. **Docker** — 5 containers with persistent volumes, auto-loading entrypoint
7. **Streamlit** — 7 tabs: chat, restaurants, hygiene, demographics, sentiment, market, location

---

## Agent tools (13)

| Tool | Purpose |
|------|---------|
| `search_restaurants` | Filter by neighbourhood, rating, cuisine |
| `get_hygiene_rating` | FSA hygiene data |
| `search_reviews` | ChromaDB semantic search |
| `get_demographics` | ONS census data |
| `get_menu_items` | Deliveroo menus and prices |
| `get_company_info` | Companies House financials |
| `compare_neighbourhoods` | Cross-area comparison |
| `get_top_restaurants` | Ranked list with filters |
| `get_sentiment_analysis` | RoBERTa NLP scores |
| `get_demand_analysis` | Demand scores + cuisine gaps |
| `get_catchment_analysis` | Competitor density per zone |
| `get_transport_accessibility` | TfL station proximity |
| `get_trading_patterns` | Opening hours segmentation |

---

## Validation

20 queries tested (10 standard + 10 investor-focused). All 20 passed hallucination validation using LLM-based restaurant name extraction and database verification. Results: `logs/agent_validation_results.json`.

---

## Key files

| File | Purpose |
|------|---------|
| `run_collectors.py` | Run all data collectors |
| `config.py` | Central configuration |
| `collectors/` | One collector per data source |
| `processing/` | Cleaning, matching, loading, analysis |
| `agent/tools.py` | 13 LangChain agent tools |
| `agent/validator.py` | LLM hallucination validator |
| `api/main.py` | FastAPI entry point |
| `app/main.py` | Streamlit 7-tab frontend |
| `mcp_server/server.py` | MCP server (3 tools) |
| `docker-compose.yml` | 5-service Docker setup |
| `docker-entrypoint.sh` | Auto-loads data on start |
| `logs/agent_validation_results.json` | 20/20 validation results |
| `logs/data_lineage.jsonl` | 741 W3C PROV lineage events |
| `docs/security.md` | Security and privacy documentation |
