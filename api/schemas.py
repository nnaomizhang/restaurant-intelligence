"""
Pydantic schemas for request/response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


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
    business_type: Optional[str] = None
    company_number: Optional[str] = None
    company_status: Optional[str] = None
    deliveroo_rating: Optional[float] = None
    menu_item_count: Optional[int] = None
    sources_matched: Optional[List[str]] = None
    nearest_station: Optional[str] = None
    nearest_station_distance_km: Optional[float] = None
    transport_score: Optional[float] = None
    trading_pattern: Optional[str] = None
    days_open: Optional[int] = None
    avg_open_time: Optional[str] = None
    avg_close_time: Optional[str] = None
    open_weekends: Optional[bool] = None

    class Config:
        arbitrary_types_allowed = True


class ReviewResponse(BaseModel):
    restaurant_name: Optional[str] = None
    neighbourhood: Optional[str] = None
    review_text: Optional[str] = None
    review_rating: Optional[int] = None
    review_date: Optional[str] = None
    review_language: Optional[str] = None


class CompanyResponse(BaseModel):
    company_number: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    incorporation_date: Optional[str] = None
    registered_address: Optional[str] = None
    postcode: Optional[str] = None
    sic_codes: Optional[List[str]] = None
    accounts_overdue: Optional[bool] = None
    distress_signals: Optional[List[str]] = None
    officer_count: Optional[int] = None
    neighbourhood: Optional[str] = None


class QueryRequest(BaseModel):
    question: str
    neighbourhood: Optional[str] = None
    history: Optional[List[dict]] = Field(default_factory=list)


class QueryResponse(BaseModel):
    answer: str
    latency_ms: Optional[int] = None
    validation: Optional[dict] = None
    sources: Optional[List[str]] = None


class DemographicResponse(BaseModel):
    neighbourhood: str
    lsoa_count: Optional[int] = None
    total_population: Optional[float] = None
    avg_population_density: Optional[float] = None
    avg_age_25_34_pct: Optional[float] = None
    avg_age_35_49_pct: Optional[float] = None
    avg_economically_active_pct: Optional[float] = None
    avg_household_single_pct: Optional[float] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    databases: Optional[dict] = None