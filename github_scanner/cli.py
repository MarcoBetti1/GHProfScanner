from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import AppConfig, load_config
from .llm import enrich_repo_summaries, generate_summary
from .report import write_report
from .scraper import collect_profile


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-scanner",
        description="Generate an LLM-powered summary for a GitHub profile.",
    )
    parser.add_argument("profile", help="GitHub profile URL, e.g. https://github.com/octocat")
    parser.add_argument("--config", type=Path, help="Path to settings YAML file", default=None)
    parser.add_argument("--docs-only", dest="docs_only", action="store_true", help="Restrict analysis to documentation files")
    parser.add_argument("--no-docs-only", dest="docs_only", action="store_false", help="Disable documentation-only restriction")
    parser.add_argument("--owned-only", dest="owned_only", action="store_true", help="Only include repositories owned by the profile")
    parser.add_argument("--no-owned-only", dest="owned_only", action="store_false", help="Include public repositories beyond owned ones")
    parser.add_argument("--output-dir", dest="output_dir", type=Path, help="Directory for the generated report")
    parser.set_defaults(docs_only=None, owned_only=None)
    return parser


def app(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.docs_only is not None:
        config.modes.docs_only = args.docs_only
    if args.owned_only is not None:
        config.modes.owned_repos_only = args.owned_only
    if args.output_dir:
        config.output.directory = args.output_dir

    try:
        profile = collect_profile(args.profile, config)
        enrich_repo_summaries(profile, config)
        summary = generate_summary(profile, config)
        report_path = write_report(profile, summary, config)
    except Exception as exc:  # pragma: no cover
        parser.error(str(exc))
        return

    print(f"Report generated: {report_path}")


if __name__ == "__main__":  # pragma: no cover
    app(sys.argv[1:])
