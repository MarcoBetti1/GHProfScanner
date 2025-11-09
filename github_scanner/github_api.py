from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from requests import Response
from tenacity import retry, stop_after_attempt, wait_exponential

API_ROOT = "https://api.github.com"
_USER_AGENT = "github-scanner/0.1"


@dataclass(slots=True)
class GitHubSession:
    http: requests.Session
    rate_limited: bool = False

    @classmethod
    def create(cls) -> "GitHubSession":
        session = requests.Session()
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": _USER_AGENT,
        }
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        session.headers.update(headers)
        return cls(http=session)

    def close(self) -> None:
        self.http.close()


def _raise_for_status(response: Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        message = response.json().get("message") if response.headers.get("Content-Type", "").startswith("application/json") else response.text
        raise requests.HTTPError(f"GitHub API request failed: {response.status_code} {message}") from error


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _get(session: GitHubSession, path: str, params: Optional[Dict[str, str]] = None) -> Response:
    url = f"{API_ROOT}{path}"
    response = session.http.get(url, params=params, timeout=30)
    if response.status_code == 403 and "rate limit" in response.text.lower():
        session.rate_limited = True
        raise requests.HTTPError("GitHub API rate limit exceeded")
    _raise_for_status(response)
    return response


def list_user_repos(session: GitHubSession, username: str, owned_only: bool = True, max_pages: int = 5) -> List[Dict[str, Any]]:
    repos: List[Dict[str, Any]] = []
    params = {
        "per_page": "100",
        "type": "owner" if owned_only else "all",
        "sort": "pushed",
    }
    for page in range(1, max_pages + 1):
        params["page"] = str(page)
        response = _get(session, f"/users/{username}/repos", params=params)
        page_items = response.json()
        if not page_items:
            break
        repos.extend(page_items)
    return repos


def get_repo_languages(session: GitHubSession, owner: str, repo: str) -> Dict[str, int]:
    response = _get(session, f"/repos/{owner}/{repo}/languages")
    body = response.json()
    return {str(language): int(bytes_count) for language, bytes_count in body.items()}


def list_repo_branches(session: GitHubSession, owner: str, repo: str, limit: int = 5) -> List[str]:
    response = _get(session, f"/repos/{owner}/{repo}/branches", params={"per_page": str(limit)})
    branches = [item.get("name") for item in response.json()]
    return [branch for branch in branches if branch]


def list_directory_contents(session: GitHubSession, owner: str, repo: str, path: str = "") -> List[Dict[str, any]]:
    api_path = f"/repos/{owner}/{repo}/contents/{path}" if path else f"/repos/{owner}/{repo}/contents"
    response = _get(session, api_path)
    data = response.json()
    if isinstance(data, dict):
        return [data]
    return data


def retrieve_file(session: GitHubSession, download_url: str) -> str:
    response = session.http.get(download_url, timeout=30)
    _raise_for_status(response)
    return response.text


def guess_username_from_profile(profile_url: str) -> str:
    sanitized = profile_url.strip().rstrip("/")
    if sanitized.endswith("github.com") or not sanitized:
        raise ValueError("Profile URL must include a username, e.g. https://github.com/octocat")
    username = sanitized.split("github.com/")[-1]
    if "/" in username:
        username = username.split("/")[0]
    if not username:
        raise ValueError("Unable to parse GitHub username from URL")
    return username
