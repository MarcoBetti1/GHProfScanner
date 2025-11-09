from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List

from .config import AppConfig
from .models import ProfileContext, RepoReport

_MAX_REPO_DOC_CHARS = 1800
_MAX_REPOS_IN_PROMPT = 8
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def enrich_repo_summaries(context: ProfileContext, config: AppConfig) -> None:
    provider = config.llm.provider.lower()
    api_key = os.getenv(config.llm.api_key_env) if provider == "openai" else None
    if provider == "openai" and api_key:
        try:
            from openai import OpenAI  # type: ignore

            client = OpenAI(api_key=api_key, organization=config.llm.organization)
            for report in context.repos:
                summary = _summarize_repo_with_openai(client, report, config)
                report.summary = summary or _fallback_repo_summary(report)
            return
        except Exception:  # pragma: no cover - fall back to heuristic summaries
            pass

    for report in context.repos:
        report.summary = _fallback_repo_summary(report)


def generate_summary(context: ProfileContext, config: AppConfig) -> str:
    prompt = _build_prompt(context)
    provider = config.llm.provider.lower()
    if provider == "openai":
        api_key = os.getenv(config.llm.api_key_env)
        if not api_key:
            return _fallback_summary(context, missing_key=config.llm.api_key_env)
        try:
            from openai import OpenAI  # type: ignore

            client = OpenAI(api_key=api_key, organization=config.llm.organization)
            response = client.responses.create(
                model=config.llm.model,
                input=[
                    {
                        "role": "system",
                        "content": "You craft crisp, professional GitHub profile spotlights for technical readers. Highlight language strengths, project domains, and practical outcomes without hype.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                max_output_tokens=min(config.llm.max_output_tokens, 600),
                temperature=config.llm.temperature,
            )
            if response.output:
                text = response.output[0].content[0].text.strip()
                cleaned = _post_process_spotlight(text)
                return cleaned or _fallback_summary(context)
            return _fallback_summary(context)
        except Exception as exc:  # pragma: no cover
            return _fallback_summary(context, error=str(exc))
    return _fallback_summary(context)


def _build_prompt(context: ProfileContext) -> str:
    lines: List[str] = []
    lines.append(f"Handle: {context.username}")
    lines.append(f"Profile: {context.profile_url}")
    if context.contributions.yearly_counts:
        lines.append("Contribution totals (year: commits):")
        for year, count in context.contributions.yearly_counts.items():
            lines.append(f"- {year}: {count}")
    language_focus = _aggregate_language_focus(context)
    if language_focus:
        lines.append(f"Primary languages: {language_focus}")
    lines.append(f"Repositories analysed: {len(context.repos)}")
    lines.append("Repository overviews:")
    for report in context.repos[:_MAX_REPOS_IN_PROMPT]:
        lines.append(_format_repo_for_prompt(report))
    lines.append(
        "Write a single paragraph (4-5 sentences) highlighting language strengths, project domains, and measurable outcomes. "
        "Avoid greetings, exclamation marks, emojis, bullet lists, and promotional phrases."
    )
    return "\n".join(lines)


def _format_repo_for_prompt(report: RepoReport) -> str:
    metrics = report.metrics
    summary_text = _condense_repo_summary(report.summary or _fallback_repo_summary(report))
    stat_line = f"stars={metrics.stars}, forks={metrics.forks}, issues={metrics.open_issues}, watchers={metrics.watchers}"
    language_line = _format_language_breakdown(metrics.languages)
    topics = ", ".join(report.metrics.topics[:6]) if report.metrics.topics else ""
    sections = [f"- {metrics.name}: {summary_text}", f"  Stats: {stat_line}"]
    if language_line:
        sections.append(f"  Languages: {language_line}")
    if topics:
        sections.append(f"  Topics: {topics}")
    sections.append(f"  Link: {metrics.html_url}")
    return "\n".join(sections)


def _prepare_highlight_line(report: RepoReport) -> str:
    first_sentence = _select_sentences(report.summary or _fallback_repo_summary(report), max_sentences=1, max_chars=160)
    if first_sentence:
        return f"{report.metrics.name}: {first_sentence}"
    return report.metrics.name


def _fallback_summary(context: ProfileContext, missing_key: str | None = None, error: str | None = None) -> str:
    reason_bits = []
    if missing_key:
        reason_bits.append(f"missing {missing_key}")
    if error:
        reason_bits.append(f"LLM error: {error}")

    total_repos = len(context.repos)
    language_focus = _aggregate_language_focus(context)
    highlight_lines = [_prepare_highlight_line(report) for report in context.repos[:3]]

    parts: List[str] = []
    parts.append(f"{context.username} maintains {total_repos} public repositories.")
    if language_focus:
        parts.append(f"Primary languages: {language_focus}.")
    if context.contributions.yearly_counts:
        recent_year, commits = max(context.contributions.yearly_counts.items())
        parts.append(f"Most active in {recent_year} with {commits} commits.")
    if highlight_lines:
        parts.append("Highlights: " + "; ".join(highlight_lines) + ".")
    if reason_bits:
        parts.append("(LLM summary unavailable: " + ", ".join(reason_bits) + ")")
    return _post_process_spotlight(" ".join(parts))


def _aggregate_language_focus(context: ProfileContext) -> str:
    counter: Counter[str] = Counter()
    for report in context.repos:
        for name, count in report.metrics.languages.items():
            counter[name] += count
    if not counter:
        return ""
    total = sum(counter.values())
    top_three = counter.most_common(3)
    parts = []
    for name, count in top_three:
        pct = round((count / total) * 100) if total else 0
        parts.append(f"{name} {pct}%")
    return ", ".join(parts)


def _summarize_repo_with_openai(client: object, report: RepoReport, config: AppConfig) -> str:
    prompt = _build_repo_summary_prompt(report)
    try:
        response = client.responses.create(
            model=config.llm.model,
            input=[
                {
                    "role": "system",
                    "content": "You summarise GitHub repositories for experienced developers using two factual sentences.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_output_tokens=min(300, config.llm.max_output_tokens),
            temperature=min(0.7, max(0.1, config.llm.temperature)),
        )
        if response.output:
            text = response.output[0].content[0].text.strip()
            return _condense_repo_summary(text)
    except Exception:  # pragma: no cover - fallback below handles errors
        pass
    return ""


def _build_repo_summary_prompt(report: RepoReport) -> str:
    metrics = report.metrics
    language_line = _format_language_breakdown(metrics.languages) or "unknown"
    topics = ", ".join(metrics.topics[:6]) if metrics.topics else "n/a"
    description = metrics.description or "No GitHub description provided."
    doc_excerpt = _prepare_repo_source_text(report)
    lines = [
        "Summarize the GitHub repository below in two sentences for a technical audience.",
        "Explain the project's purpose, notable capabilities, and target users.",
        "Avoid marketing adjectives, emojis, and hype.",
        "",
        f"Repository: {metrics.full_name}",
        f"Description: {description}",
        f"Tech stack: {language_line}",
        f"Topics: {topics}",
    ]
    if doc_excerpt:
        lines.append("Documentation excerpt:")
        lines.append(doc_excerpt)
    return "\n".join(lines)


def _prepare_repo_source_text(report: RepoReport) -> str:
    if not report.docs.files:
        return ""
    sorted_docs = sorted(report.docs.files.items(), key=lambda item: _doc_priority(item[0]))
    pieces: List[str] = []
    total = 0
    for _, raw in sorted_docs:
        if not raw:
            continue
        collapsed = _normalise_whitespace(raw)
        if not collapsed:
            continue
        remaining = _MAX_REPO_DOC_CHARS - total
        if remaining <= 0:
            break
        if len(collapsed) > remaining:
            pieces.append(collapsed[:remaining])
            total += remaining
            break
        pieces.append(collapsed)
        total += len(collapsed)
    return " ".join(pieces)


def _doc_priority(path: str) -> tuple[int, int]:
    name = Path(path).name.lower()
    if name.startswith("readme"):
        return (0, len(path))
    if any(token in name for token in ("overview", "introduction", "summary", "guide")):
        return (1, len(path))
    if name.endswith(".md"):
        return (2, len(path))
    return (3, len(path))


def _fallback_repo_summary(report: RepoReport) -> str:
    metrics = report.metrics
    description = (metrics.description or "").strip()
    doc_text = _prepare_repo_source_text(report)
    combined = " ".join(part for part in (description, doc_text) if part)
    primary = _select_sentences(combined, max_sentences=2, max_chars=320)
    language_info = _format_language_breakdown(metrics.languages)
    focus_parts: List[str] = []
    if language_info:
        focus_parts.append(f"Tech stack: {language_info}.")
    if metrics.topics:
        focus_parts.append("Domains: " + ", ".join(metrics.topics[:4]) + ".")
    summary = " ".join(part for part in (primary, " ".join(focus_parts)) if part)
    summary = summary.strip()
    if summary and summary[-1] not in ".!?":
        summary += "."
    condensed = _condense_repo_summary(summary)
    return condensed or f"{metrics.name} repository overview unavailable."


def _format_language_breakdown(languages: Dict[str, int], max_items: int = 3) -> str:
    if not languages:
        return ""
    total = sum(languages.values())
    sorted_items = sorted(languages.items(), key=lambda item: item[1], reverse=True)
    if max_items:
        sorted_items = sorted_items[:max_items]
    parts = []
    for name, count in sorted_items:
        if total:
            pct = round((count / total) * 100)
            parts.append(f"{name} {pct}%")
        else:
            parts.append(name)
    return ", ".join(parts)


def _select_sentences(text: str, max_sentences: int, max_chars: int) -> str:
    cleaned = _normalise_whitespace(text)
    if not cleaned:
        return ""
    sentences = _SENTENCE_SPLIT.split(cleaned)
    picked: List[str] = []
    total_chars = 0
    for sentence in sentences:
        if not sentence:
            continue
        picked.append(sentence)
        total_chars += len(sentence)
        if len(picked) >= max_sentences or total_chars >= max_chars:
            break
    return " ".join(picked).strip()


def _normalise_whitespace(text: str) -> str:
    return " ".join(text.strip().split())


def _post_process_spotlight(text: str) -> str:
    if not text:
        return ""
    stripped_lines: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("#", "-", "*", "+")):
            continue
        line = line.replace("**", "")
        stripped_lines.append(line)
    combined = " ".join(stripped_lines)
    combined = _normalise_whitespace(combined)
    ascii_only = combined.encode("ascii", "ignore").decode("ascii")
    if not ascii_only:
        return ""
    sentences = _SENTENCE_SPLIT.split(ascii_only)
    filtered: List[str] = []
    banned_phrases = (
        "meet ",
        "making waves",
        "developer to watch",
        "passionate developer",
        "thrilling",
        "exciting",
        "definitely",
        "keep an eye",
        "great things",
        "on the horizon",
        "pushing the boundaries",
    )
    for sentence in sentences:
        candidate = sentence.strip()
        if not candidate:
            continue
        lower = candidate.lower()
        if any(phrase in lower for phrase in banned_phrases):
            continue
        if candidate.endswith("!"):
            candidate = candidate.rstrip("!").rstrip()
        filtered.append(candidate)
    if not filtered:
        filtered = [ascii_only]
    limited = filtered[:5]
    return " ".join(limited)


def _condense_repo_summary(text: str) -> str:
    cleaned = _normalise_whitespace(text)
    if not cleaned:
        return ""
    condensed = _select_sentences(cleaned, max_sentences=2, max_chars=360)
    if condensed:
        if condensed[-1] not in ".!?":
            condensed += "."
        return condensed
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned
