"""
FastAPI REST Layer
=================
Main application entry point.

Endpoints:
  GET  /api/health              — service health check
  GET  /api/restaurants         — filtered restaurant list
  GET  /api/restaurants/{id}    — single restaurant
  POST /api/query               — natural language query to agent
  GET  /api/demographics/{area} — census data for an area
  GET  /api/hygiene             — hygiene ratings
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.restaurants import router as restaurants_router
from api.routes.query import router as query_router
from api.routes.demographics import router as demographics_router

app = FastAPI(
    title="Restaurant Intelligence API",
    description="REST API for restaurant intelligence platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(restaurants_router, prefix="/api")
app.include_router(query_router, prefix="/api")
app.include_router(demographics_router, prefix="/api")


@app.get("/api/health")
def health():
    """Health check — verifies all database connections."""
    status = {"status": "ok", "version": "1.0.0", "databases": {}}

    # Check PostgreSQL
    try:
        from sqlalchemy import create_engine, text
        import os
        engine = create_engine(os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/restaurants"))
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM restaurants")).scalar()
        status["databases"]["postgresql"] = {"status": "ok", "restaurants": count}
    except Exception as e:
        status["databases"]["postgresql"] = {"status": "error", "detail": str(e)}
        status["status"] = "degraded"

    # Check MongoDB
    try:
        from pymongo import MongoClient
        client = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"), serverSelectionTimeoutMS=2000)
        client.server_info()
        db = client["restaurant_intelligence"]
        count = db["restaurants"].count_documents({})
        status["databases"]["mongodb"] = {"status": "ok", "restaurants": count}
    except Exception as e:
        status["databases"]["mongodb"] = {"status": "error", "detail": str(e)}
        status["status"] = "degraded"

    # Check ChromaDB
    try:
        import chromadb
        from config import CHROMA_DB_DIR, CHROMA_COLLECTION_NAME
        client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        collection = client.get_collection(CHROMA_COLLECTION_NAME)
        status["databases"]["chromadb"] = {"status": "ok", "documents": collection.count()}
    except Exception as e:
        status["databases"]["chromadb"] = {"status": "error", "detail": str(e)}
        status["status"] = "degraded"

    return status


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)