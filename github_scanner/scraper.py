from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from tenacity import RetryError

from .config import AppConfig
from .github_api import (
    GitHubSession,
    guess_username_from_profile,
    list_directory_contents,
    list_repo_branches,
    list_user_repos,
    retrieve_file,
    get_repo_languages,
)
from .models import ContributionStats, ProfileContext, RepoDocumentation, RepoMetrics, RepoReport

_DOC_HINTS = {"readme", "contributing", "docs", "documentation", "guide"}
_DOC_EXTENSIONS = (".md", ".rst", ".txt")
_MAX_DOC_BYTES = 120_000
_MAX_DOC_FILES = 8


def collect_profile(profile_url: str, config: AppConfig) -> ProfileContext:
    username = guess_username_from_profile(profile_url)
    session = GitHubSession.create()
    api_available = True
    try:
        try:
            repos = list_user_repos(session, username=username, owned_only=config.modes.owned_repos_only)
        except RetryError as error:
            root_exc = error.last_attempt.exception() if hasattr(error, "last_attempt") else None
            message = str(root_exc or error)
            if root_exc and isinstance(root_exc, requests.HTTPError) and "rate limit" in message.lower():
                api_available = False
                repos = _scrape_user_repos(username)
            elif "rate limit" in message.lower():
                api_available = False
                repos = _scrape_user_repos(username)
            else:
                raise
        except requests.HTTPError as error:
            if "rate limit" in str(error).lower():
                api_available = False
                repos = _scrape_user_repos(username)
            else:
                raise

        repo_reports = [
            _build_repo_report(session if api_available else None, repo, config, api_available) for repo in repos
        ]
    finally:
        session.close()

    contributions = _fetch_contributions(username)

    return ProfileContext(
        username=username,
        profile_url=profile_url,
        contributions=contributions,
        repos=repo_reports,
        generated_at=date.today(),
    )


def _build_repo_report(
    session: GitHubSession | None,
    repo_payload: Dict[str, Any],
    config: AppConfig,
    api_available: bool,
) -> RepoReport:
    metrics = RepoMetrics(
        name=repo_payload.get("name", ""),
        full_name=repo_payload.get("full_name", ""),
        html_url=repo_payload.get("html_url", ""),
        description=repo_payload.get("description"),
        stars=int(repo_payload.get("stargazers_count", 0)),
        forks=int(repo_payload.get("forks_count", 0)),
        open_issues=int(repo_payload.get("open_issues_count", 0)),
        watchers=int(repo_payload.get("watchers_count", 0)),
        default_branch=str(repo_payload.get("default_branch", "main")),
        topics=repo_payload.get("topics", []),
    )

    owner, repo_name = metrics.full_name.split("/") if "/" in metrics.full_name else (repo_payload.get("owner", {}).get("login", ""), metrics.name)

    use_api = api_available and session is not None and not session.rate_limited
    docs: RepoDocumentation
    if use_api and session is not None:
        try:
            metrics.languages = get_repo_languages(session, owner, repo_name)
            branches = list_repo_branches(session, owner, repo_name)
            metrics.popular_branches = _select_popular_branches(metrics.default_branch, branches)
            docs = _collect_documentation(session, owner, repo_name, extended=config.modes.docs_only)
        except RetryError as error:
            session.rate_limited = True
            if _is_rate_limited_error(error):
                use_api = False
            else:
                raise
        except requests.HTTPError as error:
            if "rate limit" in str(error).lower():
                session.rate_limited = True
                use_api = False
            else:
                raise
    if not use_api:
        metrics.languages = repo_payload.get("languages", {})
        metrics.popular_branches = repo_payload.get("popular_branches", []) or [metrics.default_branch]
        docs = _collect_documentation_fallback(metrics.full_name, metrics.default_branch, extended=config.modes.docs_only)

    return RepoReport(metrics=metrics, docs=docs)


def _collect_documentation(session: GitHubSession, owner: str, repo: str, *, extended: bool) -> RepoDocumentation:
    documentation = RepoDocumentation()
    max_depth = 2 if extended else 1
    stack: List[Tuple[str, int]] = [("", 0)]
    while stack:
        path, depth = stack.pop()
        if depth > max_depth or len(documentation.files) >= _MAX_DOC_FILES:
            continue
        try:
            contents = list_directory_contents(session, owner, repo, path)
        except requests.HTTPError:
            continue
        for node in contents:
            node_type = node.get("type")
            name = node.get("name", "")
            download_url = node.get("download_url")
            size = int(node.get("size", 0))
            relative_path = node.get("path", name)
            if node_type == "dir" and depth < max_depth:
                if extended or _looks_like_doc_folder(name) or depth == 0:
                    stack.append((relative_path, depth + 1))
            elif node_type == "file" and _is_doc_file(name) and download_url and size <= _MAX_DOC_BYTES:
                try:
                    documentation.files[relative_path] = retrieve_file(session, download_url)
                except requests.HTTPError:
                    continue
    return documentation


def _collect_documentation_fallback(full_name: str, default_branch: str, *, extended: bool) -> RepoDocumentation:
    documentation = RepoDocumentation()
    branch_candidates = [default_branch]
    if default_branch != "main":
        branch_candidates.append("main")
    if default_branch != "master":
        branch_candidates.append("master")
    doc_paths = [
        "README.md",
        "Readme.md",
        "readme.md",
        "docs/README.md",
        "docs/index.md",
        "docs/overview.md",
        "docs/guide.md",
        "docs/introduction.md",
        "documentation.md",
    ]
    if extended:
        doc_paths.extend(
            [
                "docs/architecture.md",
                "docs/design.md",
                "docs/usage.md",
                "docs/setup.md",
            ]
        )
    for branch in branch_candidates:
        for path in doc_paths:
            if len(documentation.files) >= _MAX_DOC_FILES:
                return documentation
            url = f"https://raw.githubusercontent.com/{full_name}/{branch}/{path}"
            try:
                response = requests.get(url, headers={"User-Agent": "github-scanner/0.1"}, timeout=20)
            except requests.RequestException:
                continue
            if response.status_code != 200:
                continue
            text = response.text
            if len(text) > _MAX_DOC_BYTES:
                continue
            documentation.files[path] = text
    return documentation


def _looks_like_doc_folder(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _DOC_HINTS)


def _is_doc_file(name: str) -> bool:
    lowered = name.lower()
    if any(lowered.startswith(hint) for hint in _DOC_HINTS):
        return True
    return lowered.endswith(_DOC_EXTENSIONS)


def _select_popular_branches(default_branch: str, branches: List[str], limit: int = 3) -> List[str]:
    if default_branch in branches:
        branches.remove(default_branch)
    ordered = [default_branch]
    ordered.extend(branch for branch in branches if branch != default_branch)
    return ordered[:limit]


def _fetch_contributions(username: str) -> ContributionStats:
    url = f"https://github.com/users/{username}/contributions"
    response = requests.get(url, headers={"User-Agent": "github-scanner/0.1"}, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    yearly_totals: Dict[int, int] = defaultdict(int)
    for node in soup.select("rect[data-date][data-count]"):
        data_date = node.get("data-date")
        if not data_date:
            continue
        year = int(data_date.split("-")[0])
        count = int(node.get("data-count", "0"))
        yearly_totals[year] += count
    ordered = dict(sorted(yearly_totals.items()))
    return ContributionStats(yearly_counts=ordered)


def _scrape_user_repos(username: str, max_pages: int = 2) -> List[Dict[str, Any]]:
    repos: List[Dict[str, Any]] = []
    headers = {"User-Agent": "github-scanner/0.1"}
    for page in range(1, max_pages + 1):
        url = f"https://github.com/{username}?tab=repositories&type=source&sort=updated&page={page}"
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.RequestException:
            break
        soup = BeautifulSoup(response.text, "html.parser")
        container = soup.select_one("#user-repositories-list")
        if not container:
            break
        items = container.select("li")
        if not items:
            break
        for item in items:
            name_tag = item.select_one("h3 a")
            if not name_tag:
                continue
            name = name_tag.text.strip()
            if not name:
                continue
            full_name = f"{username}/{name}"
            html_url = f"https://github.com/{full_name}"
            description_tag = item.select_one("p")
            description = description_tag.text.strip() if description_tag else None
            language_tag = item.select_one("[itemprop='programmingLanguage']")
            primary_language = language_tag.text.strip() if language_tag else ""
            stars = _extract_count_from_repo_item(item, "stargazers")
            forks = _extract_count_from_repo_item(item, "network/members")
            repo_payload = {
                "name": name,
                "full_name": full_name,
                "html_url": html_url,
                "description": description,
                "stargazers_count": stars,
                "forks_count": forks,
                "open_issues_count": 0,
                "watchers_count": stars,
                "default_branch": "main",
                "topics": [],
                "languages": {primary_language: 1} if primary_language else {},
                "popular_branches": ["main"],
            }
            repos.append(repo_payload)
        if len(repos) >= 30:
            break
    return repos


def _extract_count_from_repo_item(item: Any, suffix: str) -> int:
    link = item.select_one(f"a[href$='/{suffix}']")
    if not link or not link.text:
        return 0
    text = link.text.strip().lower().replace(",", "")
    multiplier = 1
    if text.endswith("k"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000
        text = text[:-1]
    try:
        value = float(text)
    except ValueError:
        return 0
    return int(value * multiplier)


def _is_rate_limited_error(error: RetryError) -> bool:
    message = str(error)
    if hasattr(error, "last_attempt"):
        last = error.last_attempt
        if last:
            exc = last.exception()
            if exc is not None:
                message = str(exc)
    return "rate limit" in message.lower()
