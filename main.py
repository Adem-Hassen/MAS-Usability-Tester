from __future__ import annotations

import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import argparse
import os
import time
from pathlib import Path

# Ensure project root is on sys.path regardless of working directory
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.logging_config import setup_logging
from config.settings import settings
from core.graph import run_evaluation
from monitoring.logger import get_logger

logger = get_logger(__name__)

W = 68  # console width for report boxes


# =============================================================================
# Argument parsing
# =============================================================================

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="MAS-Usability-Tester — multi-agent UI accessibility evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--html",
        metavar=("PATH", "CONTEXT"),
        nargs="+",
        action="append",
        help=(
            "HTML file path, followed by an optional context description. "
            "Repeat for multiple pages: --html page1.html 'Login' --html page2.html 'Checkout'"
        ),
    )
    mode.add_argument(
        "--folder",
        metavar="DIR",
        help="Directory — all *.html files inside are evaluated in parallel.",
    )

    p.add_argument(
        "--output-dir",
        metavar="DIR",
        default=None,
        help=f"Override output directory (default: {settings.output_dir})",
    )
    p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=settings.log_level,
        help="Logging verbosity (default: %(default)s)",
    )
    p.add_argument(
        "--log-format",
        choices=["console", "json"],
        default=settings.log_format,
        help="Log output format (default: %(default)s)",
    )
    return p


# =============================================================================
# Page resolution
# =============================================================================

def _resolve_pages_from_html(html_args: list[list[str]]) -> list[dict]:
    """Convert --html PATH [CONTEXT] args into page dicts."""
    pages = []
    for entry in html_args:
        raw_path = entry[0]
        context  = " ".join(entry[1:]).strip() if len(entry) > 1 else _infer_context(raw_path)
        abs_path = Path(raw_path).resolve()
        if not abs_path.exists():
            _fatal(f"File not found: {abs_path}")
        pages.append({"html_path": str(abs_path), "ui_context": context})
    return pages


def _resolve_pages_from_folder(folder: str) -> list[dict]:
    """Scan a folder for *.html files and build page dicts."""
    d = Path(folder).resolve()
    if not d.exists() or not d.is_dir():
        _fatal(f"Folder not found: {d}")
    files = sorted(d.glob("*.html"))
    if not files:
        _fatal(f"No .html files found in: {d}")
    return [
        {"html_path": str(f), "ui_context": _infer_context(str(f))}
        for f in files
    ]


def _infer_context(path: str) -> str:
    """Derive a human-readable context from the filename."""
    stem = Path(path).stem.replace("_", " ").replace("-", " ")
    return stem.title() + " — web UI"


def _fatal(msg: str) -> None:
    print(f"\n[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


# =============================================================================
# Console output
# =============================================================================

def _print_header(pages: list[dict]) -> None:
    n = len(pages)
    print(f"\n{'═' * W}")
    print(f"  MAS-Usability-Tester  —  {n} page(s) queued for evaluation")
    print(f"{'═' * W}")
    for i, p in enumerate(pages, 1):
        name = Path(p["html_path"]).name
        ctx  = p["ui_context"]
        print(f"  {i}. {name:<30}  {ctx}")
    print(f"{'─' * W}")
    print(f"  Output dir   : {settings.output_dir}/")
    print(f"  LLM (supv)   : {settings.supervisor_llm_model}")
    print(f"  LLM (persona): {settings.persona_llm_model}")
    print(f"  LLM (rec)    : {settings.recommender_llm_model}")
    print(f"  Concurrency  : {getattr(settings, 'llm_max_concurrent_calls', 5)} parallel LLM calls max")
    print(f"  Personas/pg  : up to {settings.max_num_personas}")
    print(f"  Max steps    : {settings.persona_max_steps}")
    print(f"{'═' * W}\n")


def _print_report(report, idx: int, total: int, elapsed: float) -> None:
    """Pretty-print a single DiagnosticReport to the console."""
    bar = "─" * W

    print(f"\n{'═' * W}")
    if total > 1:
        print(f"  REPORT {idx}/{total}")
    print(f"{'═' * W}")

    if not report:
        print("  Status : FAILED — no report produced")
        print(f"{'═' * W}")
        return

    score = report.overall_score
    if sys.stdout.isatty():
        if score >= 7:
            colour = "\033[92m"
        elif score >= 4:
            colour = "\033[93m"
        else:
            colour = "\033[91m"
        score_s = f"{colour}{score:.1f}/10\033[0m"
    else:
        score_s = f"{score:.1f}/10"

    sev = report.severity_breakdown

    print(f"  File         : {Path(report.html_source_path).name}")
    print(f"  Context      : {report.ui_context}")
    print(f"  Score        : {score_s}")
    print(bar)
    print(f"  Issues found : {report.total_issues_found}  "
          f"(critical={sev.critical}  high={sev.high}  "
          f"medium={sev.medium}  low={sev.low})")
    print(f"  Resolved     : {report.issues_resolved_count}")
    print(f"  Remaining    : {report.issues_remaining_count}")
    if getattr(report, "regressions_introduced", 0):
        print(f"  Regressions  : {report.regressions_introduced}  "
              f"← new issues introduced by patches")
    print(f"  Patches      : {report.total_patches_applied} applied")
    print(f"  Corr. loops  : {report.correction_loop_count}")
    print(f"  Verification : {'✓ PASSED' if report.verification_passed else '✗ FAILED'}")
    print(f"  Elapsed      : {elapsed:.0f}s (estimated)")
    print(bar)

    if report.executive_summary:
        print("  Executive summary:")
        for line in report.executive_summary.strip().splitlines():
            print(f"    {line}")
        print(bar)

    if report.top_recommendations:
        print("  Top recommendations:")
        for i, rec in enumerate(report.top_recommendations, 1):
            words  = rec.split()
            prefix = f"    {i}. "
            indent = " " * len(prefix)
            line   = prefix
            for word in words:
                if len(line) + len(word) + 1 > W:
                    print(line.rstrip())
                    line = indent + word + " "
                else:
                    line += word + " "
            if line.strip():
                print(line.rstrip())
        print(bar)

    artefact_dir = Path(settings.output_dir) / Path(report.html_source_path).stem
    print(f"  Artefacts    : {artefact_dir}/")
    print(f"{'═' * W}")


def _print_summary(reports: list, n_pages: int, total_elapsed: float) -> int:
    """Print the run summary and return the exit code (0 = all OK, 1 = failures)."""
    succeeded = [r for r in reports if r]
    failed    = n_pages - len(succeeded)

    print(f"\n{'═' * W}")
    print(f"  RUN SUMMARY")
    print(f"{'─' * W}")
    print(f"  Pages evaluated  : {n_pages}")
    print(f"  Reports produced : {len(succeeded)}")
    if failed:
        print(f"  Failed           : {failed}")
    print(f"  Total elapsed    : {total_elapsed:.0f}s")

    if succeeded:
        avg_score       = sum(r.overall_score         for r in succeeded) / len(succeeded)
        total_issues    = sum(r.total_issues_found    for r in succeeded)
        total_resolved  = sum(r.issues_resolved_count for r in succeeded)
        total_remaining = sum(r.issues_remaining_count for r in succeeded)
        print(f"{'─' * W}")
        print(f"  Avg score        : {avg_score:.1f}/10")
        print(f"  Total issues     : {total_issues}")
        print(f"  Total resolved   : {total_resolved}")
        print(f"  Total remaining  : {total_remaining}")

    print(f"{'═' * W}\n")
    return 1 if failed else 0


# =============================================================================
# Entry point
# =============================================================================

def main() -> None:
    args = _build_parser().parse_args()

    # Apply output-dir override before anything reads settings
    if args.output_dir:
        os.environ["OUTPUT_DIR"] = args.output_dir

    setup_logging(log_level=args.log_level, log_format=args.log_format)

    # Resolve pages
    if args.folder:
        pages = _resolve_pages_from_folder(args.folder)
    else:
        pages = _resolve_pages_from_html(args.html)

    n = len(pages)
    _print_header(pages)

    t_start = time.monotonic()

    try:
        result = run_evaluation(pages)
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Run cancelled by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        logger.error("main.exception", error=str(exc))
        print(f"\n[FATAL] Pipeline crashed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    total_elapsed = time.monotonic() - t_start

    # Surface any pipeline-level error
    if result.get("pipeline_error"):
        print(f"\n[ERROR] Pipeline error: {result['pipeline_error']}", file=sys.stderr)
        print("  Run with --log-level DEBUG for details.", file=sys.stderr)
        sys.exit(1)

    reports = result.get("reports", [])

    # Print individual reports
    per_page_elapsed = total_elapsed / max(len(reports), 1)
    for idx, report in enumerate(reports, 1):
        _print_report(report, idx, len(reports), per_page_elapsed)

    # Warn if fewer reports than pages
    if len(reports) < n:
        missing = n - len(reports)
        print(
            f"\n[WARNING] {missing} page(s) produced no report. "
            f"Run with --log-level DEBUG for details.",
            file=sys.stderr,
        )

    exit_code = _print_summary(reports, n, total_elapsed)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()