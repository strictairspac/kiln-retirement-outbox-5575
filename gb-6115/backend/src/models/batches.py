from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, String, Table, UniqueConstraint
from .base import metadata


# 正式退役批次台账。演练回放不落此表，正式与演练互不占号。
batches = Table(
    "retirement_batches", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("code", String(48), unique=True, nullable=False),
    Column("case_id", ForeignKey("cases.id"), nullable=True, index=True),
    Column("run_id", ForeignKey("runs.id"), nullable=True, index=True),
    Column("origin", String(24), nullable=False),
    Column("status", String(16), nullable=False, index=True),
    Column("title", String(120), nullable=False),
    Column("verdict", String(320), nullable=False),
    Column("numbers", JSON, nullable=False),
    Column("collisions", JSON, nullable=True),
    Column("archived", Integer, nullable=False, default=0),
    Column("created_by", String(48), nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("finished_at", BigInteger, nullable=True),
)

# 整批编号占位：炉号与证书号各占一行，唯一键跨批次生效。
# 退回或执行失败时整批删除，成功批次继续占用。
claims = Table(
    "retirement_number_claims", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("batch_id", ForeignKey("retirement_batches.id"), nullable=False, index=True),
    Column("number_kind", String(16), nullable=False),
    Column("number_code", String(24), nullable=False),
    UniqueConstraint("number_kind", "number_code", name="uq_retirement_number"),
)

# 只有交卷成功的正式批次才写收据；失败批次一张证书也不进档。
archive = Table(
    "retirement_certificate_archive", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("batch_id", ForeignKey("retirement_batches.id"), nullable=False, index=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, index=True),
    Column("asset", String(24), nullable=False),
    Column("certificate", String(24), nullable=False),
    Column("archived_at", Integer, nullable=False),
    UniqueConstraint("batch_id", "certificate", name="uq_archive_certificate"),
)
