from pydantic import BaseModel, Field, field_validator

from src.utils.serial import canonical_json


class CaseInput(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=420)
    payload: dict

    @field_validator("title")
    @classmethod
    def check_title(cls, title):
        if len(title.strip()) < 2:
            raise ValueError("请输入至少两个字符的名称")
        return title.strip()

    @field_validator("payload")
    @classmethod
    def check_size(cls, payload):
        if len(canonical_json(payload)) > 750_000:
            raise ValueError("样本数据不能超过 750 KB")
        return payload


class CaseEntry(CaseInput):
    id: int
    code: str
    created_by: str


class BatchEntry(BaseModel):
    id: int
    code: str
    case_id: int | None
    run_id: int | None
    origin: str
    status: str
    title: str
    verdict: str
    numbers: list[dict]
    collisions: list[dict] | None
    archived: int
    created_by: str
    created_at: int
    finished_at: int | None


class CaseResult(BaseModel):
    accepted: bool
    case: CaseEntry | None
    batch_id: int | None
    verdict: str
