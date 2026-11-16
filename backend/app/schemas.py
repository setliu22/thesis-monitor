import re
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from .financials import METRICS


class CompanyInput(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)

    @field_validator("ticker")
    @classmethod
    def valid_ticker(cls, v):
        v = v.strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", v):
            raise ValueError("Enter a valid US stock ticker")
        return v


class ThesisInput(BaseModel):
    body: str = Field(min_length=1, max_length=12000)

    @field_validator("body")
    @classmethod
    def nonempty(cls, v):
        if not v.strip():
            raise ValueError("Write a thesis before saving")
        return v.strip()


class RuleInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    metric: str
    operator: Literal["lt", "lte", "gt", "gte"]
    threshold: Decimal = Field(allow_inf_nan=False, max_digits=24, decimal_places=8)
    period_kind: Literal["quarter", "annual"] = "quarter"
    enabled: bool = True

    @field_validator("metric")
    @classmethod
    def known_metric(cls, v):
        if v not in METRICS:
            raise ValueError("Unsupported financial metric")
        return v

    @field_validator("name")
    @classmethod
    def nonempty(cls, v):
        if not v.strip():
            raise ValueError("Rule name required")
        return v.strip()


class AnalysisInput(BaseModel):
    filing_id: int = Field(gt=0)
