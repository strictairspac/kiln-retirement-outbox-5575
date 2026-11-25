from time import time
from uuid import uuid4

from sqlalchemy import and_, delete, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from src.domain.inputs import parse
from src.models.batches import archive, batches, claims
from src.models.cases import cases
from src.models.runs import runs

HELD = "held"
REJECTED = "rejected"
SUCCEEDED = "succeeded"
FAILED = "failed"

LABELS = {HELD: "已占号", REJECTED: "整批退回", SUCCEEDED: "已交卷", FAILED: "执行失败"}
KIND_LABEL = {"asset": "炉号", "certificate": "证书号"}


class BatchError(ValueError):
    """正式批次判定失败，执行批次随之失败。"""


class BatchInterrupted(BatchError):
    """正式批次执行中断：整批回滚，执行批次与批次台账都记为失败。"""


def number_pairs(requests):
    pairs = [("asset", request.asset) for request in requests]
    pairs += [("certificate", request.certificate) for request in requests]
    return sorted(pairs)


def number_objects(pairs):
    return [{"number_kind": kind, "number_code": code} for kind, code in pairs]


def _holders(db, pairs, batch_id):
    """查询待占编号当前由哪个其他正式批次持有。"""
    if not pairs:
        return {}
    condition = or_(*[
        and_(claims.c.number_kind == kind, claims.c.number_code == code) for kind, code in pairs
    ])
    rows = db.execute(
        select(
            claims.c.number_kind, claims.c.number_code,
            batches.c.id.label("holder_id"), batches.c.code.label("holder_code"),
            batches.c.title.label("holder_title"), batches.c.origin.label("holder_origin"),
            batches.c.status.label("holder_status"),
        )
        .join(batches, batches.c.id == claims.c.batch_id)
        .where(claims.c.batch_id != batch_id, condition)
    ).mappings().all()
    return {(row["number_kind"], row["number_code"]): dict(row) for row in rows}


def _claim_all(db, batch_id, pairs):
    """整批占号：任一编号撞号则本批一个号也不留（保存点整体回滚）。"""
    for _ in range(4):
        taken = _holders(db, pairs, batch_id)
        if taken:
            return taken
        try:
            with db.begin_nested():
                rows = [{"batch_id": batch_id, "number_kind": kind, "number_code": code} for kind, code in pairs]
                db.execute(insert(claims), rows)
            return {}
        except IntegrityError:
            # 并发登记撞上同一编号，等对方落定后重新判定。
            continue
    taken = _holders(db, pairs, batch_id)
    if taken:
        return taken
    raise BatchError("编号登记并发冲突，请重试", 409)


def _rejection_verdict(taken):
    """点名撞号编号与占用批次；超长时至少完整保留第一条，其余用条数概述。"""
    items = sorted(taken.values(), key=lambda item: (item["number_kind"] != "asset", item["number_code"]))
    parts = []
    for index, item in enumerate(items):
        title = (item["holder_title"] or "")[:24]
        phrase = (f"{KIND_LABEL.get(item['number_kind'], item['number_kind'])} {item['number_code']} "
                  f"已被批次 {item['holder_code']}（{item.get('holder_origin') or '—'}·{title}）占用")
        remaining = len(items) - index
        suffix = f"；另有 {remaining - 1} 个编号同样被占用" if remaining > 1 else ""
        if index and len("整批退回：" + "；".join(parts + [phrase]) + suffix + "。") > 320:
            parts.append(f"另有 {remaining} 个编号被其他批次占用")
            break
        parts.append(phrase)
    return ("整批退回：" + "；".join(parts) + "。")[:320]


def _held_verdict(pairs):
    names = "、".join(f"{KIND_LABEL[kind]} {code}" for kind, code in pairs[:2])
    suffix = f" 等 {len(pairs)} 个编号" if len(pairs) > 2 else ""
    return f"整批已占号：{names}{suffix}由本批持有，交卷前其他批次无法登记这些编号。"


def register(db, title, description, payload, origin, actor, case_code=None, batch_code=None):
    """登记正式退役批次。整批占号成功才落资料；任一编号撞号则整批退回且不留号。"""
    requests, _ = parse(payload)
    pairs = number_pairs(requests)
    now = int(time())
    batch_id = db.execute(insert(batches).values(
        code=batch_code or f"FRM-{uuid4().hex[:12].upper()}", case_id=None, run_id=None, origin=origin,
        status=HELD, title=title, numbers=[], collisions=None, archived=0,
        created_by=actor, created_at=now, finished_at=None, verdict="正在登记编号。",
    )).inserted_primary_key[0]

    taken = _claim_all(db, batch_id, pairs)
    if taken:
        verdict = _rejection_verdict(taken)
        db.execute(update(batches).where(batches.c.id == batch_id).values(
            status=REJECTED, verdict=verdict, numbers=number_objects(pairs),
            collisions=list(taken.values()), finished_at=now,
        ))
        return {"accepted": False, "batch_id": batch_id, "verdict": verdict}

    case_id = db.execute(insert(cases).values(
        code=case_code or f"CASE-{uuid4().hex[:12].upper()}", title=title, description=description,
        payload=payload, created_by=actor,
    )).inserted_primary_key[0]
    verdict = _held_verdict(pairs)
    db.execute(update(batches).where(batches.c.id == batch_id).values(
        case_id=case_id, verdict=verdict, numbers=number_objects(pairs), collisions=None,
    ))
    return {"accepted": True, "batch_id": batch_id, "case_id": case_id, "verdict": verdict}


def held_batch(db, case_id, lock=False):
    statement = select(batches).where(batches.c.case_id == case_id)
    if lock:
        statement = statement.with_for_update()
    return db.execute(statement).mappings().first()


def bind_run(db, case_id, run_id):
    db.execute(update(batches).where(batches.c.case_id == case_id, batches.c.run_id.is_(None)).values(run_id=run_id))


def _interruption(requests):
    """只有事件前失败才整项回滚；收据写入后断联属于可补领，不算失败。"""
    for request in requests:
        if request.failed_stage == "before_enqueue":
            return f"炉号 {request.asset} 的退役登记在投递前中断"
    return None


def _release(db, batch_id):
    db.execute(delete(claims).where(claims.c.batch_id == batch_id))


def execute(db, case_id, run_id):
    """执行正式批次：成功则进档并继续占号，中断则抛出 BatchInterrupted 由事务整批回滚。"""
    row = db.execute(
        select(batches).where(batches.c.case_id == case_id).with_for_update()
    ).mappings().first()
    if row is None:
        raise BatchError("该资料没有对应的正式退役批次")
    if row["status"] != HELD:
        raise BatchError(f"正式批次当前为{LABELS.get(row['status'], row['status'])}，不能再次执行")
    requests, _ = parse(_payload_of(db, case_id))
    reason = _interruption(requests)
    if reason is not None:
        raise BatchInterrupted(f"{reason}（整批 {len(requests) * 2} 个编号已释放，0 张证书进档）")

    now = int(time())
    db.execute(insert(archive), [
        {"batch_id": row["id"], "run_id": run_id, "asset": request.asset,
         "certificate": request.certificate, "archived_at": now + position}
        for position, request in enumerate(requests)
    ])
    verdict = f"交卷完成：{len(requests)} 张证书进档，整批 {len(requests) * 2} 个编号继续占用。"
    db.execute(update(batches).where(batches.c.id == row["id"]).values(
        status=SUCCEEDED, archived=len(requests), finished_at=now, run_id=run_id, verdict=verdict,
    ))
    return {
        "summary": verdict,
        "metrics": {"进档证书": len(requests), "占用编号": len(requests) * 2, "释放编号": 0},
        "rows": [{"炉体": request.asset, "退役证书": request.certificate, "进档": "已进档"}
                 for request in requests],
    }


def abandon(db, run_id, reason):
    """执行失败后清账：释放整批编号并记失败判定，一张证书也不进档。"""
    case_id = db.scalar(select(runs.c.case_id).where(runs.c.id == run_id))
    if case_id is None:
        return None
    row = db.execute(
        select(batches).where(batches.c.case_id == case_id, batches.c.status == HELD).with_for_update()
    ).mappings().first()
    if row is None:
        return None
    _release(db, row["id"])
    total = len(row["numbers"] or [])
    verdict = f"执行失败：{reason}；0 张证书进档，整批 {total} 个编号已释放。"
    db.execute(update(batches).where(batches.c.id == row["id"]).values(
        status=FAILED, run_id=run_id, archived=0, finished_at=int(time()), verdict=verdict[:320],
    ))
    return verdict


def _payload_of(db, case_id):
    payload = db.scalar(select(cases.c.payload).where(cases.c.id == case_id))
    if payload is None:
        raise BatchError("正式批次关联的资料不存在")
    return payload


def ledger(db, limit=100):
    rows = db.execute(
        select(batches).order_by(batches.c.id.desc()).limit(limit)
    ).mappings().all()
    return [dict(row) for row in rows]
