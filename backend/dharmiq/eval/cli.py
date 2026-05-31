from __future__ import annotations

import argparse
import asyncio
import sys

from dharmiq.config.settings import get_settings
from dharmiq.core.errors import EvalError
from dharmiq.core.logging import setup_logging
from dharmiq.db.session import close_db, get_session_factory, init_db
from dharmiq.eval.runner import run_eval_dataset
from dharmiq.llm.openrouter_client import close_openrouter_client


async def _main(dataset_name: str) -> int:
    settings = get_settings()
    setup_logging(settings)
    await init_db(settings)
    factory = get_session_factory()

    try:
        async with factory() as db:
            summary = await run_eval_dataset(db, dataset_name, settings=settings)
    except EvalError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        if hint := exc.details.get("hint"):
            print(f"Hint: {hint}", file=sys.stderr)
        if corpus_dir := exc.details.get("corpus_dir"):
            print(f"Corpus dir: {corpus_dir}", file=sys.stderr)
        return 1
    finally:
        await close_openrouter_client()
        await close_db()

    print(f"Eval run {summary.run_id} complete for dataset '{summary.dataset_name}'")
    print(f"Questions: {summary.question_count}")
    print("Aggregate metrics:")
    for key, value in summary.aggregate_metrics.items():
        print(f"  {key}: {value:.3f}" if isinstance(value, float) else f"  {key}: {value}")
    print(f"Summary written to: {summary.output_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Dharmiq RAG evaluation dataset")
    parser.add_argument(
        "--dataset",
        required=True,
        help="Dataset name (filename stem under data/eval/datasets/, e.g. v1_fundamental_rights)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args.dataset)))


if __name__ == "__main__":
    main()
