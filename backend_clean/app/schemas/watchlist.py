from typing import Any, Dict, Optional

from pydantic import BaseModel


class AddCompanyWatchlistRequest(BaseModel):
    user_id: str
    company_id: Optional[str] = None
    query_id: Optional[str] = None
    company_name: str
    abn: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    risk_score: Optional[int] = None
    risk_level: Optional[str] = None
    alerts_enabled: bool = True
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class UpdateCompanyWatchlistRequest(BaseModel):
    alerts_enabled: Optional[bool] = None
    notes: Optional[str] = None
    risk_score: Optional[int] = None
    risk_level: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
