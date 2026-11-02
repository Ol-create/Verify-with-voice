# app/routes/admin/schemas.py
"""Request and response bodies for the admin API."""
import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

CompanyStatus = Literal["pending", "active", "suspended"]


class CredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime.datetime | None
    last_used_at: datetime.datetime | None
    revoked_at: datetime.datetime | None


class CompanySummary(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None
    status: CompanyStatus
    created_at: datetime.datetime | None
    user_count: int
    active_key_count: int


class CompanyPage(BaseModel):
    items: list[CompanySummary]
    total: int
    page: int
    page_size: int


class Usage(BaseModel):
    since: datetime.datetime
    verifications: int
    verifications_succeeded: int
    enrollments_completed: int


class CompanyDetail(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None
    status: CompanyStatus
    created_at: datetime.datetime | None
    user_count: int
    credentials: list[CredentialOut]
    usage_this_month: Usage


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    status: CompanyStatus = "active"

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name can't be empty")
        return value


class CompanyUpdate(BaseModel):
    """Only the fields sent are changed. Send "email": null to clear the email."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    status: CompanyStatus | None = None

    @field_validator("name", "status")
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError("Can't be empty")
        return value

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name can't be empty")
        return value


class CompanyCreated(BaseModel):
    company: CompanyDetail
    api_key: str = Field(description="Shown once. Only its hash is stored.")
    api_secret: str = Field(description="Shown once. Only its hash is stored.")


class CredentialCreate(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=64, description="A label, e.g. \"production\"")

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name can't be empty")
        return value


class CredentialCreated(BaseModel):
    credential: CredentialOut
    api_key: str = Field(description="Shown once. Only its hash is stored.")
    api_secret: str = Field(description="Shown once. Only its hash is stored.")
