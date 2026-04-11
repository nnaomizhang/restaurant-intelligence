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
    return {
        "status": "ok",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)