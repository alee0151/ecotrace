from typing import Optional

from pydantic import BaseModel


class CreateUserRequest(BaseModel):
    email: str
    user_type: str = "consumer"


class RequestEmailVerificationRequest(BaseModel):
    email: str
    return_to: Optional[str] = "/app/search"


class ConfirmEmailVerificationRequest(BaseModel):
    token: str
