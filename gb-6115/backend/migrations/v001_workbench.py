from src.models import audit, batches, cases, reviews, runs, users  # Register the tables.
from src.models.base import metadata


def upgrade(connection):
    # 版本 1 为增量且完全声明式。
    metadata.create_all(connection)
