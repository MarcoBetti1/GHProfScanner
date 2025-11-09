from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .config import AppConfig
from .models import ProfileContext, RepoMetrics, RepoReport


def write_report(context: ProfileContext, summary: str, config: AppConfig) -> Path:
    output_dir = config.output.directory
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{context.username}-summary.md"
    report_path = output_dir / filename
    report_path.write_text(_render_markdown(context, summary), encoding="utf-8")
    return report_path


def _render_markdown(context: ProfileContext, summary: str) -> str:
    lines: List[str] = []
    lines.append(f"# GitHub Profile Summary: {context.username}")
    lines.append("")
    lines.append(f"Generated on: {context.generated_at.isoformat()}")
    lines.append(f"Profile: {context.profile_url}")
    lines.append("")
    lines.append("## Spotlight")
    lines.append(summary.strip())
    lines.append("")
    if context.contributions.yearly_counts:
        lines.append("## Contribution Stats")
        for year, count in context.contributions.yearly_counts.items():
            lines.append(f"- {year}: {count} contributions")
        lines.append("")
    lines.append("## Public Repositories")
    if not context.repos:
        lines.append("No repositories found under the current mode settings.")
        return "\n".join(lines)

    for report in context.repos:
        lines.extend(_render_repo(report))
        lines.append("")
    return "\n".join(lines)


def _render_repo(report: RepoReport) -> List[str]:
    metrics = report.metrics
    summary_text = (report.summary or "Summary unavailable.").strip()
    lines = [f"### {metrics.name}"]
    lines.append(summary_text)
    lines.append("")
    lines.extend(_render_repo_details(metrics))
    return lines


def _render_repo_details(metrics: RepoMetrics) -> List[str]:
    rows: List[tuple[str, str]] = []
    rows.append(("Repository", metrics.full_name))
    rows.append(("Link", metrics.html_url))
    rows.append(
        (
            "Stats",
            "stars {stars}, forks {forks}, issues {issues}, watchers {watchers}".format(
                stars=metrics.stars,
                forks=metrics.forks,
                issues=metrics.open_issues,
                watchers=metrics.watchers,
            ),
        )
    )
    language_summary = _format_language_summary(metrics.languages)
    if language_summary:
        rows.append(("Tech stack", language_summary))
    if metrics.topics:
        rows.append(("Domains", ", ".join(metrics.topics[:6])))
    if metrics.popular_branches:
        rows.append(("Branches", ", ".join(metrics.popular_branches)))

    table_lines = ["| Field | Details |", "| --- | --- |"]
    for label, value in rows:
        table_lines.append(f"| {label} | {value} |")
    return table_lines


def _format_language_summary(languages: Dict[str, int], limit: int = 4) -> str:
    if not languages:
        return ""
    total = sum(languages.values())
    if not total:
        return ""
    sorted_items = sorted(languages.items(), key=lambda item: item[1], reverse=True)[:limit]
    parts = []
    for name, count in sorted_items:
        pct = round((count / total) * 100)
        parts.append(f"{name} {pct}%")
    return ", ".join(parts)
