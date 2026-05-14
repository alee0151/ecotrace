from typing import Optional

from pydantic import BaseModel


class CompanyAnalysisRequest(BaseModel):
    company_or_abn: str
    news_limit: int = 3
    max_llm_results: int = 10
    max_report_chunks: int = 3
    australia_only: bool = True
    force_refresh: bool = False
