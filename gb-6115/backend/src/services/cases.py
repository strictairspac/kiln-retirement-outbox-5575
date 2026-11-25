from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import insert, select

from src.domain import registry
from src.domain.inputs import origin, parse
from src.models.cases import cases
from .audit import record


def get(db, case_id):
    entry = db.execute(select(cases).where(cases.c.id == case_id)).mappings().first()
    if entry is None:
        raise HTTPException(404, "资料不存在")
    return dict(entry)


def list_entries(db):
    return [dict(row) for row in db.execute(select(cases).order_by(cases.c.id.desc()).limit(100)).mappings()]


def create(db, data, actor):
    """登记资料。带来源的正式批次先整批占号，撞号则整批退回且不落资料。"""
    try:
        source = origin(data.payload)
        parse(data.payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if source is not None:
        try:
            result = registry.register(db, data.title, data.description, data.payload, source, actor)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not result["accepted"]:
            record(db, "reject_batch", actor, "batch", result["batch_id"])
            return {"accepted": False, "case": None, "batch_id": result["batch_id"], "verdict": result["verdict"]}
        entry = get(db, result["case_id"])
        record(db, "create_case", actor, "case", result["case_id"])
        record(db, "claim_batch", actor, "batch", result["batch_id"])
        return {"accepted": True, "case": entry, "batch_id": result["batch_id"], "verdict": result["verdict"]}

    entry = db.execute(insert(cases).values(
        **data.model_dump(), code=f"CASE-{uuid4().hex[:12].upper()}", created_by=actor,
    ))
    case_id = entry.inserted_primary_key[0]
    record(db, "create_case", actor, "case", case_id)
    return {"accepted": True, "case": get(db, case_id), "batch_id": None, "verdict": "演练资料已保存，回放不占用正式编号。"}


def ledger(db):
    return registry.ledger(db)
