from typing import Optional

from pydantic import BaseModel


class SearchRequest(BaseModel):
    user_id: Optional[str] = None
    barcode: Optional[str] = None
    brand: Optional[str] = None
    company_or_abn: Optional[str] = None
