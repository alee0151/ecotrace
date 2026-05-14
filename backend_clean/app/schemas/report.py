from typing import Any, Dict, Optional

from pydantic import BaseModel


class SendReportEmailRequest(BaseModel):
    email: str
    query_id: str


class GenerateReportRequest(BaseModel):
    query_id: str
    analysis_payload: Optional[Dict[str, Any]] = None


class SendPersistedReportEmailRequest(BaseModel):
    email: str
