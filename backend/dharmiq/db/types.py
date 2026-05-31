from __future__ import annotations

from pgvector import Vector as PgVector
from pgvector.sqlalchemy import Vector as SAVector


class AsyncPgVector(SAVector):
    """pgvector column type that binds Python vectors for asyncpg."""

    cache_ok = True

    def bind_processor(self, dialect):
        if dialect.name == "postgresql":
            def process(value):
                if value is None:
                    return None
                if not isinstance(value, PgVector):
                    return PgVector(value)
                return value

            return process
        return super().bind_processor(dialect)
