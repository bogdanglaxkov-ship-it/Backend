from typing import Optional
from pydantic import BaseModel, Field


class TenderDocument(BaseModel):
    name: str
    url: str


class TenderOut(BaseModel):
    """Тендер в формате, который ожидает фронтенд (см. frontend/lib/api.ts -> Tender)."""

    id: str
    title: str
    price: Optional[float] = None
    region: Optional[str] = None
    district: Optional[str] = None
    organization: Optional[str] = None
    city: Optional[str] = None
    keyword: Optional[str] = None
    status: str = "active"
    url: Optional[str] = None
    deadline: Optional[str] = None
    published_at: Optional[str] = None
    participants: Optional[int] = None
    contact: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[list[str]] = None
    documents: Optional[list[TenderDocument]] = None


class TenderSearchResponse(BaseModel):
    total_count: int
    items: list[TenderOut] = Field(default_factory=list)
    results: list[TenderOut] = Field(default_factory=list)
