from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dharmiq.config.settings import get_settings
from dharmiq.core.errors import EvalError
from dharmiq.core.logging import setup_logging
from dharmiq.db.session import close_db, get_session_factory, init_db
from dharmiq.eval.baseline import (
    build_mvp_baseline,
    build_single_dataset_baseline,
    build_v06_baseline,
    merge_baseline_suite,
    write_baseline,
)
from dharmiq.eval.compare import (
    compare_against_baseline,
    compare_exit_code,
    format_delta_table,
    load_baseline_metrics,
    load_baseline_payload,
    resolve_baseline_path,
)
from dharmiq.eval.metadata import (
    collect_run_metadata,
    default_allowlist_path,
    default_v06_allowlist_path,
)
from dharmiq.eval.runner import run_eval_dataset
from dharmiq.eval.suite import run_mvp_suite, run_v06_suite
from dharmiq.eval.tools.allowlist import resolve_allowlist_cli_arg
from dharmiq.llm.openrouter_client import close_openrouter_client

SUITE_LABELS = {
    "mvp": "MVP",
    "v06": "v0.6",
}


def _print_aggregate_metrics(metrics: dict[str, float]) -> None:
    print("Aggregate metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value:.3f}" if isinstance(value, float) else f"  {key}: {value}")


def _resolve_suite_allowlist(suite_name: str, repo_root: Path, allowlist_path: Path | None) -> Path:
    if allowlist_path is not None:
        return allowlist_path
    if suite_name == "v06":
        return default_v06_allowlist_path(repo_root)
    return default_allowlist_path(repo_root)


async def _main_dataset(
    dataset_name: str,
    *,
    limit: int | None,
    write_baseline_flag: bool,
    yes: bool,
    allowlist_path: Path | None,
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
                resolved_allowlist = _resolve_suite_allowlist(
                    "mvp",
                    settings.repo_root,
                    allowlist_path,
                )
                metadata = await collect_run_metadata(
                    db,
                    settings=settings,
                    allowlist_path=resolved_allowlist,
                )
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
    suite_name: str,
    *,
    limit: int | None,
    write_baseline_flag: bool,
    compare_name: str | None,
    yes: bool,
    allowlist_path: Path | None,
) -> int:
    settings = get_settings()
    setup_logging(settings)
    await init_db(settings)
    factory = get_session_factory()
    exit_code = 0

    try:
        async with factory() as db:
            if suite_name == "v06":
                suite_summary = await run_v06_suite(db, settings=settings, limit=limit)
            else:
                suite_summary = await run_mvp_suite(db, settings=settings, limit=limit)

            resolved_allowlist = _resolve_suite_allowlist(
                suite_name,
                settings.repo_root,
                allowlist_path,
            )
            metadata = await collect_run_metadata(
                db,
                settings=settings,
                allowlist_path=resolved_allowlist,
            )
            runs_dir = settings.eval.resolve_runs_dir(settings.repo_root)

            label = SUITE_LABELS.get(suite_name, suite_name)
            print(f"{label} suite complete")
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
                baseline_metrics = load_baseline_metrics(baseline_path, suite=suite_name)
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
                if suite_name == "v06":
                    payload = build_v06_baseline(suite_summary=suite_summary, metadata=metadata)
                    baseline_path = resolve_baseline_path(runs_dir, "baseline")
                    existing = (
                        load_baseline_payload(baseline_path) if baseline_path.is_file() else None
                    )
                    payload = merge_baseline_suite(payload, existing=existing)
                else:
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
        choices=["mvp", "v06"],
        default=None,
        help="Run a named eval suite (mvp = six gating datasets; v06 = mvp + property/tax/cyber)",
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
        help="Compare run metrics against baseline (default name: baseline); requires --suite",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Overwrite existing baseline.json without prompting",
    )
    parser.add_argument(
        "--allowlist",
        default=None,
        help="Corpus allowlist YAML path or alias (central, v0.6, v06)",
    )
    args = parser.parse_args()

    if not args.dataset and not args.suite:
        parser.error("one of --dataset or --suite is required")
    if args.dataset and args.suite:
        parser.error("--dataset and --suite are mutually exclusive")
    if args.compare is not None and args.suite is None:
        parser.error("--compare requires --suite")

    settings = get_settings()
    allowlist_path: Path | None = None
    if args.allowlist is not None:
        allowlist_path = resolve_allowlist_cli_arg(
            args.allowlist,
            repo_root=settings.repo_root,
        )

    if args.suite is not None:
        raise SystemExit(
            asyncio.run(
                _main_suite(
                    args.suite,
                    limit=args.limit,
                    write_baseline_flag=args.write_baseline,
                    compare_name=args.compare,
                    yes=args.yes,
                    allowlist_path=allowlist_path,
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
                allowlist_path=allowlist_path,
            )
        )
    )


if __name__ == "__main__":
    main()
