from __future__ import annotations

import argparse
import asyncio
import sys

from dharmiq.config.settings import get_settings
from dharmiq.core.errors import EvalError
from dharmiq.core.logging import setup_logging
from dharmiq.db.session import close_db, get_session_factory, init_db
from dharmiq.eval.baseline import (
    build_mvp_baseline,
    build_single_dataset_baseline,
    write_baseline,
)
from dharmiq.eval.compare import (
    compare_against_baseline,
    compare_exit_code,
    format_delta_table,
    load_baseline_metrics,
    resolve_baseline_path,
)
from dharmiq.eval.metadata import collect_run_metadata
from dharmiq.eval.runner import run_eval_dataset
from dharmiq.eval.suite import run_mvp_suite
from dharmiq.llm.openrouter_client import close_openrouter_client


def _print_aggregate_metrics(metrics: dict[str, float]) -> None:
    print("Aggregate metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value:.3f}" if isinstance(value, float) else f"  {key}: {value}")


async def _main_dataset(
    dataset_name: str,
    *,
    limit: int | None,
    write_baseline_flag: bool,
    yes: bool,
) -> int:
    settings = get_settings()
    setup_logging(settings)
    await init_db(settings)
    factory = get_session_factory()

    try:
        async with factory() as db:
            summary = await run_eval_dataset(
                db,
                dataset_name,
                settings=settings,
                limit=limit,
            )
            if write_baseline_flag:
                metadata = await collect_run_metadata(db, settings=settings)
                payload = build_single_dataset_baseline(
                    dataset_name=summary.dataset_name,
                    aggregate_metrics=summary.aggregate_metrics,
                    metadata=metadata,
                    model=summary.model,
                )
                runs_dir = settings.eval.resolve_runs_dir(settings.repo_root)
                baseline_path = write_baseline(payload, runs_dir=runs_dir, yes=yes)
                print(f"Baseline written to: {baseline_path}")
    except EvalError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        if hint := exc.details.get("hint"):
            print(f"Hint: {hint}", file=sys.stderr)
        if corpus_dir := exc.details.get("corpus_dir"):
            print(f"Corpus dir: {corpus_dir}", file=sys.stderr)
        return 1
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await close_openrouter_client()
        await close_db()

    print(f"Eval run {summary.run_id} complete for dataset '{summary.dataset_name}'")
    print(f"Questions: {summary.question_count}")
    _print_aggregate_metrics(summary.aggregate_metrics)
    print(f"Summary written to: {summary.output_path}")
    return 0


async def _main_suite(
    *,
    limit: int | None,
    write_baseline_flag: bool,
    compare_name: str | None,
    yes: bool,
) -> int:
    settings = get_settings()
    setup_logging(settings)
    await init_db(settings)
    factory = get_session_factory()
    exit_code = 0

    try:
        async with factory() as db:
            suite_summary = await run_mvp_suite(db, settings=settings, limit=limit)
            metadata = await collect_run_metadata(db, settings=settings)
            runs_dir = settings.eval.resolve_runs_dir(settings.repo_root)

            print("MVP suite complete")
            print(f"Total questions evaluated: {suite_summary.total_questions}")
            _print_aggregate_metrics(suite_summary.aggregate_metrics)

            for outcome in suite_summary.outcomes:
                if outcome.summary is not None:
                    print(
                        f"  {outcome.dataset_name}: "
                        f"{outcome.summary.question_count} questions "
                        f"→ {outcome.summary.output_path}"
                    )
                else:
                    print(f"  {outcome.dataset_name}: FAILED — {outcome.error}", file=sys.stderr)

            if compare_name is not None:
                baseline_path = resolve_baseline_path(runs_dir, compare_name)
                if not baseline_path.is_file():
                    print(f"Error: baseline not found at {baseline_path}", file=sys.stderr)
                    return 1
                baseline_metrics = load_baseline_metrics(baseline_path)
                print()
                print(format_delta_table(suite_summary.aggregate_metrics, baseline_metrics))
                regressions, target_violations = compare_against_baseline(
                    suite_summary.aggregate_metrics,
                    baseline_metrics,
                )
                if regressions:
                    print("\nRegressions:", file=sys.stderr)
                    for item in regressions:
                        print(f"  - {item}", file=sys.stderr)
                if target_violations:
                    print("\nTarget violations:", file=sys.stderr)
                    for item in target_violations:
                        print(f"  - {item}", file=sys.stderr)
                exit_code = compare_exit_code(
                    suite_summary.aggregate_metrics,
                    baseline_metrics,
                )

            if write_baseline_flag:
                payload = build_mvp_baseline(suite_summary=suite_summary, metadata=metadata)
                baseline_path = write_baseline(payload, runs_dir=runs_dir, yes=yes)
                print(f"Baseline written to: {baseline_path}")
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await close_openrouter_client()
        await close_db()

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Dharmiq RAG evaluation datasets")
    parser.add_argument(
        "--dataset",
        default=None,
        help="Dataset name (filename stem under data/eval/datasets/, e.g. v1_fundamental_rights)",
    )
    parser.add_argument(
        "--suite",
        choices=["mvp"],
        default=None,
        help="Run a named eval suite (mvp = all gating datasets)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Evaluate only the first N questions per dataset (spike runs)",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write data/eval/runs/baseline.json from this run",
    )
    parser.add_argument(
        "--compare",
        nargs="?",
        const="baseline",
        default=None,
        metavar="NAME",
        help="Compare run metrics against baseline (default name: baseline); requires --suite mvp",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Overwrite existing baseline.json without prompting",
    )
    args = parser.parse_args()

    if not args.dataset and not args.suite:
        parser.error("one of --dataset or --suite is required")
    if args.dataset and args.suite:
        parser.error("--dataset and --suite are mutually exclusive")
    if args.compare is not None and args.suite != "mvp":
        parser.error("--compare requires --suite mvp")

    if args.suite == "mvp":
        raise SystemExit(
            asyncio.run(
                _main_suite(
                    limit=args.limit,
                    write_baseline_flag=args.write_baseline,
                    compare_name=args.compare,
                    yes=args.yes,
                )
            )
        )

    raise SystemExit(
        asyncio.run(
            _main_dataset(
                args.dataset,
                limit=args.limit,
                write_baseline_flag=args.write_baseline,
                yes=args.yes,
            )
        )
    )


if __name__ == "__main__":
    main()
