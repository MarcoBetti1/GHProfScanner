from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


@dataclass(slots=True)
class ContributionStats:
    yearly_counts: Dict[int, int]


@dataclass(slots=True)
class RepoDocumentation:
    files: Dict[str, str] = field(default_factory=dict)

    def merge(self, other: "RepoDocumentation") -> None:
        for name, content in other.files.items():
            if name not in self.files:
                self.files[name] = content


@dataclass(slots=True)
class RepoMetrics:
    name: str
    full_name: str
    html_url: str
    description: Optional[str]
    stars: int
    forks: int
    open_issues: int
    watchers: int
    default_branch: str
    languages: Dict[str, int] = field(default_factory=dict)
    topics: List[str] = field(default_factory=list)
    popular_branches: List[str] = field(default_factory=list)


@dataclass(slots=True)
class RepoReport:
    metrics: RepoMetrics
    docs: RepoDocumentation
    summary: str = ""


@dataclass(slots=True)
class ProfileContext:
    username: str
    profile_url: str
    contributions: ContributionStats
    repos: List[RepoReport]
    generated_at: date
