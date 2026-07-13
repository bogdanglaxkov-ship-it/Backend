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


class LotDocument(BaseModel):
    """Документ лота — демо-данные (в БД документы пока не хранятся)."""

    id: str
    name: str
    description: str


class LotDetail(BaseModel):
    """Богатая карточка лота для страницы /tenders/{id}.
    Реальные поля (id/title/price/region/status/url) берутся из TenderDB,
    остальное — детерминированно сгенерированные демо-данные (сид = tender id),
    поэтому одна и та же карточка выглядит одинаково при каждом заходе.
    """

    id: str
    title: str
    description: str
    lot_number: str
    type: str
    category: str
    subcategory: str
    customer: str
    customer_rating: int
    region: Optional[str] = None
    deadline_text: str
    status_label: str
    purchase_method: str
    trade_type: str
    amount: float
    quantity: int
    price_per_unit: float
    margin_percent: float
    profit: float
    competition: int
    dumping_percent: float
    source_url: Optional[str] = None
    documents: list[LotDocument] = Field(default_factory=list)
    shared_documents: list[LotDocument] = Field(default_factory=list)
