#!/bin/sh
set -e

cd /app/backend

alembic upgrade head

python -c "
import asyncio
from dharmiq.agents.checkpoint import get_checkpointer, close_checkpointer

async def main() -> None:
    await get_checkpointer()
    await close_checkpointer()

asyncio.run(main())
"

exec "$@"
