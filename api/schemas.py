"""
Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel
from typing import Optional


class RestaurantResponse(BaseModel):
    name: Optional[str] = None
    neighbourhood: Optional[str] = None
    address: Optional[str] = None
    postcode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    google_rating: Optional[float] = None
    google_review_count: Optional[int] = None
    google_price_level: Optional[int] = None
    hygiene_rating: Optional[int] = None
    business_type: Optional[str] = None
    company_status: Optional[str] = None
    sources_matched: Optional[list] = None

    class Config:
        arbitrary_types_allowed = True


class QueryRequest(BaseModel):
    question: str
    neighbourhood: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    sources: Optional[list] = None


class DemographicResponse(BaseModel):
    neighbourhood: str
    total_population: Optional[float] = None
    population_density: Optional[float] = None
    age_25_34_pct: Optional[float] = None
    economically_active_pct: Optional[float] = None