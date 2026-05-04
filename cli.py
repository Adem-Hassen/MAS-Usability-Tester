# cli.py

import argparse
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from core.graph import run_evaluation
from config.settings import settings
from monitoring.logger import get_logger

logger = get_logger("cli")

def main():
    parser = argparse.ArgumentParser(description="MAS Usability Tester - Batch CLI")
    parser.add_argument("paths", nargs="+", help="Paths to HTML files or directories to evaluate")
    parser.add_argument("--output", "-o", default="cli_results", help="Output directory for reports")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--loops", type=int, default=1, help="Max correction loops per page")
    parser.add_argument("--personas", type=int, default=3, help="Number of personas per page")
    
    args = parser.parse_args()

    # Override settings
    settings.output_dir = args.output
    settings.persona_headless = args.headless
    settings.max_correction_loops = args.loops
    settings.max_num_personas = args.personas

    input_paths = []
    for p in args.paths:
        path = Path(p)
        if path.is_dir():
            input_paths.extend(list(path.glob("*.html")))
        elif path.is_file() and path.suffix == ".html":
            input_paths.append(path)

    if not input_paths:
        print("Error: No valid HTML files found at provided paths.")
        sys.exit(1)

    print(f"--- MAS Usability Tester CLI ---")
    print(f"Processing {len(input_paths)} files...")
    print(f"Output directory: {args.output}")
    print(f"Headless: {args.headless}")
    print(f"--------------------------------")

    for i, path in enumerate(input_paths, 1):
        print(f"[{i}/{len(input_paths)}] Evaluating: {path.name}...", end="", flush=True)
        try:
            # We don't have a stream_callback in CLI (or we could print events)
            # Just run the graph synchronously
            final_state = run_evaluation(
                html_source_path=str(path),
                ui_context=f"CLI Batch processing of {path.name}",
                persona_count=args.personas
            )
            
            report = final_state.get("reports", [])
            score = report[-1].overall_score if report else "n/a"
            print(f" DONE (Score: {score})")
            
        except Exception as e:
            print(f" FAILED")
            logger.error(f"cli.execution_failed", file=path.name, error=str(e))

    print(f"\nBatch processing complete. Reports saved to {args.output}/")

if __name__ == "__main__":
    main()
