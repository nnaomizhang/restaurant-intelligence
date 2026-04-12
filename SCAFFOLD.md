# Project Scaffold

Delete anything not needed. All files listed here exist in the repository.

```
restaurant-intelligence/
│
├── .env                          # API keys — never committed
├── .gitignore
├── config.py                     # Central config, loads .env
├── run_collectors.py             # Run all collectors (--force, --source flags)
├── docker-compose.yml            # 5 services: app, api, postgres, mongodb, mcp
├── Dockerfile                    # python:3.11-slim base
├── docker-entrypoint.sh          # Auto-loads data on container start
├── requirements.txt
├── README.md
├── SCAFFOLD.md                   # This file
├── start.sh                      # Full system startup helper
├── split_ons_lsoa_files.py       # Splitter to extract Shoreditch, Peckham and Hackney
│
├── collectors/                   # Data collection layer
│   ├── base.py                   # BaseCollector with lineage, rate limiting
│   ├── google_places.py          # Places API (New), 20 search terms, dedup
│   ├── fsa.py                    # FSA API + XML fallback
│   ├── companies_house.py        # SIC codes, officers, filing history, distress signals
│   ├── deliveroo.py              # Selenium scraper, 50 cap/area, menu extraction
│   ├── ons_census.py             # CSV merger for TS006/007A/021/066/003
│   └── tfl_enricher.py           # TfL API, nearest station per restaurant
│
├── processing/                   # Data processing pipeline
│   ├── cleaner.py                # Normalise, hotel filter, PII sanitisation
│   ├── matcher.py                # Fuzzy entity matching across sources
│   ├── mongo_loader.py           # Upsert to MongoDB collections
│   ├── postgres_loader.py        # Load 7 PostgreSQL tables
│   ├── embeddings.py             # ChromaDB via sentence-transformers
│   ├── sentiment.py              # RoBERTa sentiment, weighted by review count
│   ├── demand_mapper.py          # Demand scores + cuisine gap analysis
│   ├── hours_analyser.py         # Opening hours → trading pattern classification
│   ├── geo_analyser.py           # GeoJSON + Haversine spatial clusters
│   ├── catchment_modeller.py     # Competitor density per zone
│   └── lineage.py                # W3C PROV-style lineage logging
│
├── agent/                        # LLM agent layer
│   ├── agent.py                  # LangGraph ReAct + GPT-4o + conversation history
│   ├── tools.py                  # 13 LangChain tools (SQL, vector, TfL, sentiment...)
│   ├── validator.py              # LLM-based hallucination checker
│   └── logger.py                 # Query logging to JSONL + agent.log
│
├── api/                          # FastAPI REST layer
│   ├── main.py                   # App entry, CORS, health check with DB status
│   ├── schemas.py                # Pydantic models for all requests/responses
│   └── routes/
│       ├── __init__.py
│       ├── restaurants.py        # GET /restaurants, /hygiene, /companies, /lineage, /reviews
│       ├── query.py              # POST /query (SSE streaming + history)
│       └── demographics.py      # GET /demographics/{neighbourhood}
│
├── app/
│   └── main.py                   # Streamlit 7-tab frontend
│                                 # Tab 1: Strategic chat
│                                 # Tab 2: Restaurant explorer
│                                 # Tab 3: Hygiene intelligence
│                                 # Tab 4: Demographics
│                                 # Tab 5: Sentiment analysis
│                                 # Tab 6: Market opportunity
│                                 # Tab 7: Location analysis (postcode)
│
├── mcp_server/
│   └── server.py                 # MCP server: restaurant_query, review_search, market_analysis
│
├── tests/
│   ├── test_collectors.py        # 18 tests — collectors, lineage, data completeness
│   └── test_data_completeness.py
│
├── data/
│   ├── raw/                      # Raw collected data (JSON files)
│   │   ├── google_places/        # shoreditch.json, peckham.json, hackney.json
│   │   ├── fsa/
│   │   ├── companies_house/
│   │   ├── deliveroo/
│   │   └── ons_downloads/        # Original CSV files from Nomis
│   │   └── ons_census/           # New CSV files created from split_ons_lsoa_files.py
│   │
│   └── processed/                # Cleaned and processed data
│       ├── google_places/
│       ├── fsa/
│       ├── companies_house/
│       ├── deliveroo/
│       ├── ons_census/
│       ├── master/               # Fuzzy-matched unified records
│       ├── sentiment_results.json
│       ├── demand_scores.json
│       ├── catchment_results.json
│       ├── tfl_stations.json
│       ├── restaurants.geojson
│       ├── neighbourhoods.geojson
│       └── catchment_zones.geojson
│
├── logs/
│   ├── agent.log                 # Agent reasoning logs
│   ├── queries.jsonl             # Every query + answer + latency
│   ├── data_lineage.jsonl        # 741 W3C PROV collection/transformation events
│   └── agent_validation_results.json  # 20/20 validation test results
│
├── docs/
│   └── security.md               # API key management, PII sanitisation policy
│
└── chroma_db/                    # ChromaDB persistent storage
    ├── chroma.sqlite3            # Collection metadata
    └── {uuid}/                   # restaurant_reviews collection (UUID-named)
```
