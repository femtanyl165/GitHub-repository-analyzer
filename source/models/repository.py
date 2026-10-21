from dataclasses import dataclass, field
from typing import Any


@dataclass
class RepositoryAnalysis:
    owner: str
    name: str
    full_name: str
    description: str
    stars: int
    forks: int
    updated_at: str
    last_commit_date: str | None
    languages: dict[str, int] = field(default_factory=dict)
    contributors: list[dict[str, Any]] = field(default_factory=list)
    open_issues: list[dict[str, Any]] = field(default_factory=list)
    pull_requests: list[dict[str, Any]] = field(default_factory=list)
    releases: list[dict[str, Any]] = field(default_factory=list)
    readme: str | None = None
    health_score: int = 0
    health_breakdown: list[dict[str, Any]] = field(default_factory=list)
    evaluation_profile_name: str = "Базовая оценка"
    contributors_has_more: bool = False
    issues_has_more: bool = False
    pull_requests_has_more: bool = False
    releases_has_more: bool = False
    open_issue_count: int = 0
    open_pull_request_count: int = 0
    commit_counts: dict[int, int] = field(default_factory=dict)
    average_issue_close_hours: float | None = None
    average_pull_merge_hours: float | None = None
    quality_files: dict[str, bool] = field(default_factory=dict)
    has_actions: bool = False
    has_tests: bool = False
    has_documentation: bool = False
    is_archived: bool = False
    default_branch: str = "—"
    default_branch_protected: bool | None = None
    last_successful_workflow: dict[str, Any] | None = None
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    dependency_count: int = 0
    dependency_status: str = "unavailable"
    dependabot_configured: bool = False
    dependabot_update_count: int | None = None
    dependabot_alerts: list[dict[str, Any]] = field(default_factory=list)
    dependabot_status: str = "permission_required"


@dataclass
class RepositoryPage:
    category: str
    page: int
    items: list[dict[str, Any]] = field(default_factory=list)
    has_more: bool = False
