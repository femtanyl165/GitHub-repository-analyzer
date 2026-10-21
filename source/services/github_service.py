import base64
import os
import re
from datetime import datetime, timedelta, timezone
from time import monotonic, sleep
from typing import Any, Callable
from urllib.parse import quote, quote_plus

import requests

from models.repository import RepositoryAnalysis, RepositoryPage
from utils.health_score import HealthMetrics, calculate_health_report


class GitHubError(Exception):
    pass


class InvalidRepositoryError(GitHubError):
    pass


class RepositoryNotFoundError(GitHubError):
    pass


class RateLimitError(GitHubError):
    pass


class NetworkError(GitHubError):
    pass


class AnalysisCancelledError(GitHubError):
    pass


class AnalysisTimeoutError(GitHubError):
    pass


class InvalidTokenError(GitHubError):
    pass


class AccessDeniedError(GitHubError):
    pass


class RepositoryRemovedError(GitHubError):
    pass


class InvalidResponseError(GitHubError):
    pass


class GitHubUnavailableError(GitHubError):
    pass


ProgressCallback = Callable[[str], None]
CancelCallback = Callable[[], bool]


def parse_repository(value: str) -> tuple[str, str]:
    value = value.strip().rstrip("/")
    match = re.fullmatch(r"(?:https?://(?:www\.)?github\.com/)?([\w.-]+)/([\w.-]+)(?:\.git)?", value)
    if not match:
        raise InvalidRepositoryError("Введите owner/repo или ссылку https://github.com/owner/repo")
    return match.group(1), match.group(2).removesuffix(".git")


def parse_profile_url(value: str) -> str | None:
    """Return a GitHub username from a profile repository-list URL, if supplied."""
    match = re.fullmatch(r"https?://(?:www\.)?github\.com/([\w.-]+)/?\?tab=repositories", value.strip())
    return match.group(1) if match else None


class GitHubService:
    BASE_URL = "https://api.github.com"
    ANALYSIS_TIMEOUT_SECONDS = 120.0
    PAGE_TIMEOUT_SECONDS = 30.0
    REQUEST_TIMEOUT_SECONDS = 15.0
    MAX_ATTEMPTS = 3
    RETRY_DELAYS = (1.0, 2.0)
    RETRYABLE_STATUS_CODES = {408, 500, 502, 503, 504}
    PAGE_SIZES = {
        "contributors": 20,
        "issues": 30,
        "pull_requests": 20,
        "releases": 10,
    }

    def __init__(self, token: str | None = None, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        token = token if token is not None else os.getenv("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitHub-Repository-Analyzer",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.has_token = bool(token)

    def _get(
        self,
        path: str,
        *,
        optional: bool = False,
        expected_type: type | tuple[type, ...] | None = None,
        progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
        deadline: float | None = None,
    ) -> Any:
        deadline = deadline or monotonic() + self.ANALYSIS_TIMEOUT_SECONDS
        last_network_error: requests.RequestException | None = None
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            self._check_operation(is_cancelled, deadline)
            remaining = deadline - monotonic()
            request_timeout = max(0.5, min(self.REQUEST_TIMEOUT_SECONDS, remaining))
            try:
                response = self.session.get(
                    f"{self.BASE_URL}{path}",
                    headers=self.headers,
                    timeout=request_timeout,
                )
                self._check_operation(is_cancelled, deadline)
            except requests.RequestException as exc:
                last_network_error = exc
                if attempt == self.MAX_ATTEMPTS:
                    break
                self._retry_delay(attempt, progress, is_cancelled, deadline)
                continue

            if response.status_code in self.RETRYABLE_STATUS_CODES:
                if attempt == self.MAX_ATTEMPTS:
                    raise GitHubUnavailableError(
                        f"GitHub временно недоступен (ошибка {response.status_code}). Повторите позже."
                    )
                self._retry_delay(attempt, progress, is_cancelled, deadline)
                continue

            return self._parse_response(response, optional=optional, expected_type=expected_type)

        self._check_operation(is_cancelled, deadline)
        raise NetworkError(
            "Не удалось подключиться к GitHub после нескольких попыток. "
            "Проверьте интернет, прокси или брандмауэр."
        ) from last_network_error

    def _parse_response(
        self,
        response: requests.Response,
        *,
        optional: bool,
        expected_type: type | tuple[type, ...] | None,
    ) -> Any:
        status = response.status_code
        response_text = response.text or ""
        if status == 401:
            raise InvalidTokenError(
                "GitHub отклонил токен. Проверьте GITHUB_TOKEN: он мог истечь, быть отозван или введён неверно."
            )
        if status in {403, 429} and self._is_rate_limit_response(response):
            raise RateLimitError(self._rate_limit_message(response))
        if status in {403, 451}:
            raise AccessDeniedError(
                "GitHub запретил доступ к ресурсу. Токену может не хватать разрешений или доступ ограничен организацией."
            )
        if status == 404 and optional:
            return None
        if status == 404:
            raise RepositoryNotFoundError(
                "Репозиторий не найден: он мог быть удалён, переименован, не существовать или быть скрыт правами токена."
            )
        if status == 410:
            raise RepositoryRemovedError("Репозиторий или запрошенный ресурс был удалён.")
        if status == 204 and optional:
            return None
        if not response.ok:
            detail = self._safe_error_message(response_text)
            suffix = f" {detail}" if detail else ""
            raise GitHubError(f"GitHub API вернул ошибку {status}.{suffix}")
        try:
            data = response.json()
        except (requests.JSONDecodeError, ValueError) as exc:
            raise InvalidResponseError(
                "GitHub вернул повреждённый JSON. Повторите анализ позже."
            ) from exc
        if expected_type is not None and not isinstance(data, expected_type):
            raise InvalidResponseError("GitHub API вернул неожиданный формат данных.")
        return data

    @staticmethod
    def _safe_error_message(response_text: str) -> str:
        text = " ".join(response_text.strip().split())
        return text[:200] if text and not text.startswith("<") else ""

    @staticmethod
    def _is_rate_limit_response(response: requests.Response) -> bool:
        text = (response.text or "").lower()
        return (
            response.status_code == 429
            or response.headers.get("X-RateLimit-Remaining") == "0"
            or "rate limit" in text
            or "secondary rate" in text
        )

    @staticmethod
    def _rate_limit_message(response: requests.Response) -> str:
        retry_after = response.headers.get("Retry-After")
        reset = response.headers.get("X-RateLimit-Reset")
        if retry_after and retry_after.isdigit():
            return f"Превышен лимит GitHub API. Повторите через {retry_after} сек."
        if reset and reset.isdigit():
            reset_at = datetime.fromtimestamp(int(reset), tz=timezone.utc).astimezone()
            return f"Превышен лимит GitHub API. Лимит обновится примерно в {reset_at:%H:%M:%S}."
        return "Превышен лимит GitHub API. Добавьте корректный токен или повторите позже."

    def _retry_delay(
        self,
        attempt: int,
        progress: ProgressCallback | None,
        is_cancelled: CancelCallback | None,
        deadline: float,
    ) -> None:
        delay = self.RETRY_DELAYS[min(attempt - 1, len(self.RETRY_DELAYS) - 1)]
        self._report(
            progress,
            f"Временная ошибка GitHub. Повтор {attempt + 1}/{self.MAX_ATTEMPTS} через {delay:g} сек.…",
        )
        wait_until = monotonic() + delay
        while monotonic() < wait_until:
            self._check_operation(is_cancelled, deadline)
            remaining_delay = wait_until - monotonic()
            if remaining_delay <= 0:
                break
            sleep(min(0.1, remaining_delay))

    @staticmethod
    def _check_cancelled(is_cancelled: CancelCallback | None) -> None:
        if is_cancelled and is_cancelled():
            raise AnalysisCancelledError("Анализ отменён.")

    @classmethod
    def _check_operation(cls, is_cancelled: CancelCallback | None, deadline: float) -> None:
        cls._check_cancelled(is_cancelled)
        if monotonic() >= deadline:
            raise AnalysisTimeoutError(
                "Анализ превысил общий тайм-аут. Попробуйте позже или выберите репозиторий меньшего размера."
            )

    @staticmethod
    def _report(progress: ProgressCallback | None, message: str) -> None:
        if progress:
            progress(message)

    def _get_all(
        self,
        path: str,
        *,
        optional: bool = False,
        per_page: int = 100,
        progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
        deadline: float | None = None,
    ) -> list[dict[str, Any]]:
        """Load every page from a GitHub endpoint that returns a list."""
        deadline = deadline or monotonic() + self.ANALYSIS_TIMEOUT_SECONDS
        items: list[dict[str, Any]] = []
        separator = "&" if "?" in path else "?"
        page = 1
        while True:
            self._check_operation(is_cancelled, deadline)
            self._report(progress, f"Загрузка списка репозиториев: страница {page}…")
            data = self._get(
                f"{path}{separator}per_page={per_page}&page={page}",
                optional=optional,
                expected_type=list,
                progress=progress,
                is_cancelled=is_cancelled,
                deadline=deadline,
            )
            self._check_operation(is_cancelled, deadline)
            if data is None:
                return items
            self._validate_object_list(data)
            items.extend(data)
            if len(data) < per_page:
                return items
            page += 1

    @staticmethod
    def _compact(items: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
        return [{field: item.get(field) for field in fields} for item in items]

    @staticmethod
    def _validate_object_list(items: list[Any]) -> None:
        if not all(isinstance(item, dict) for item in items):
            raise InvalidResponseError("GitHub API вернул неожиданный формат списка.")

    @staticmethod
    def _parse_github_date(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @classmethod
    def _average_duration_hours(
        cls,
        items: list[dict[str, Any]],
        finished_field: str,
    ) -> float | None:
        durations: list[float] = []
        for item in items:
            created = cls._parse_github_date(item.get("created_at"))
            finished = cls._parse_github_date(item.get(finished_field))
            if created and finished and finished >= created:
                durations.append((finished - created).total_seconds() / 3600)
        return sum(durations) / len(durations) if durations else None

    @staticmethod
    def _commit_counts(activity: list[dict[str, Any]], now: datetime | None = None) -> dict[int, int]:
        now = now or datetime.now(timezone.utc)
        counts = {30: 0, 90: 0, 365: 0}
        for week in activity:
            timestamp = week.get("week")
            days = week.get("days")
            if not isinstance(timestamp, int) or not isinstance(days, list):
                continue
            week_start = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            for offset, total in enumerate(days[:7]):
                if not isinstance(total, int):
                    continue
                day = week_start + timedelta(days=offset)
                for period in counts:
                    if day >= now - timedelta(days=period):
                        counts[period] += total
        return counts

    def _search_count(
        self,
        query: str,
        *,
        progress: ProgressCallback | None,
        is_cancelled: CancelCallback | None,
        deadline: float,
    ) -> int:
        data = self._get(
            f"/search/issues?q={quote_plus(query)}&per_page=1",
            expected_type=dict,
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        )
        total = data.get("total_count")
        if not isinstance(total, int):
            raise InvalidResponseError("GitHub вернул некорректное количество issues или pull requests.")
        return total

    def _optional_search_count(
        self,
        query: str,
        *,
        progress: ProgressCallback | None,
        is_cancelled: CancelCallback | None,
        deadline: float,
    ) -> int | None:
        try:
            return self._search_count(
                query,
                progress=progress,
                is_cancelled=is_cancelled,
                deadline=deadline,
            )
        except (AccessDeniedError, InvalidTokenError, RateLimitError, GitHubUnavailableError):
            return None

    def _permission_optional_get(
        self,
        path: str,
        *,
        expected_type: type | tuple[type, ...],
        progress: ProgressCallback | None,
        is_cancelled: CancelCallback | None,
        deadline: float,
    ) -> tuple[str, Any]:
        try:
            data = self._get(
                path,
                optional=True,
                expected_type=expected_type,
                progress=progress,
                is_cancelled=is_cancelled,
                deadline=deadline,
            )
        except (AccessDeniedError, InvalidTokenError):
            return "permission_required", None
        except RateLimitError:
            return "rate_limited", None
        return ("available", data) if data is not None else ("unavailable", None)

    def load_page(
        self,
        repository: str,
        category: str,
        page: int,
        *,
        progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
        _deadline: float | None = None,
    ) -> RepositoryPage:
        """Load one bounded page for a list displayed by the application."""
        deadline = _deadline or monotonic() + self.PAGE_TIMEOUT_SECONDS
        owner, name = parse_repository(repository)
        base = f"/repos/{owner}/{name}"
        page_size = self.PAGE_SIZES.get(category)
        if page_size is None:
            raise GitHubError("Неизвестный тип данных для постраничной загрузки.")
        endpoints = {
            "contributors": (f"{base}/contributors", ("login", "contributions", "html_url")),
            "issues": (f"{base}/issues?state=open", ("number", "title", "html_url", "created_at")),
            "pull_requests": (f"{base}/pulls?state=open", ("number", "title", "html_url", "created_at", "user")),
            "releases": (f"{base}/releases", ("name", "tag_name", "html_url", "published_at")),
        }
        path, fields = endpoints[category]
        separator = "&" if "?" in path else "?"
        self._check_operation(is_cancelled, deadline)
        data = self._get(
            f"{path}{separator}per_page={page_size}&page={page}",
            optional=True,
            expected_type=list,
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        ) or []
        self._check_operation(is_cancelled, deadline)
        self._validate_object_list(data)
        has_more = len(data) == page_size
        if category == "issues":
            # GitHub's issues endpoint includes pull requests.
            data = [item for item in data if "pull_request" not in item]
        return RepositoryPage(
            category=category,
            page=page,
            items=self._compact(data, fields),
            has_more=has_more,
        )

    def analyze(
        self,
        repository: str,
        *,
        progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
    ) -> RepositoryAnalysis:
        deadline = monotonic() + self.ANALYSIS_TIMEOUT_SECONDS
        owner, name = parse_repository(repository)
        base = f"/repos/{owner}/{name}"
        self._check_operation(is_cancelled, deadline)
        self._report(progress, "Загрузка сведений о репозитории…")
        repo = self._get(
            base,
            expected_type=dict,
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        )
        if not isinstance(repo.get("full_name"), str):
            raise InvalidResponseError("В ответе GitHub отсутствует имя репозитория.")
        self._check_operation(is_cancelled, deadline)
        self._report(progress, "Загрузка последнего коммита…")
        commit_data = self._get(
            f"{base}/commits?per_page=1",
            optional=True,
            expected_type=list,
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        ) or []
        self._validate_object_list(commit_data)
        try:
            last_commit = commit_data[0]["commit"]["author"].get("date") if commit_data else None
        except (KeyError, TypeError, AttributeError) as exc:
            raise InvalidResponseError("GitHub вернул неожиданный формат данных коммита.") from exc
        self._check_operation(is_cancelled, deadline)
        self._report(progress, "Загрузка языков…")
        languages = self._get(
            f"{base}/languages",
            expected_type=dict,
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        )
        if not all(isinstance(language, str) and isinstance(size, int) for language, size in languages.items()):
            raise InvalidResponseError("GitHub вернул неожиданный формат списка языков.")
        pages: dict[str, RepositoryPage] = {}
        labels = {
            "contributors": "contributors",
            "issues": "issues",
            "pull_requests": "pull requests",
            "releases": "releases",
        }
        for category, label in labels.items():
            self._report(progress, f"Загрузка {label}…")
            pages[category] = self.load_page(
                repository,
                category,
                1,
                progress=progress,
                is_cancelled=is_cancelled,
                _deadline=deadline,
            )
        self._report(progress, "Загрузка README…")
        readme_data = self._get(
            f"{base}/readme",
            optional=True,
            expected_type=dict,
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        )
        self._check_operation(is_cancelled, deadline)
        readme = None
        if readme_data:
            try:
                readme = base64.b64decode(readme_data["content"]).decode("utf-8", errors="replace")
            except (KeyError, TypeError, ValueError) as exc:
                raise InvalidResponseError("GitHub вернул повреждённые данные README.") from exc

        default_branch = repo.get("default_branch") if isinstance(repo.get("default_branch"), str) else "—"
        self._report(progress, "Проверка структуры и файлов качества…")
        tree_data = None
        if default_branch != "—":
            tree_data = self._get(
                f"{base}/git/trees/{quote(default_branch, safe='')}?recursive=1",
                optional=True,
                expected_type=dict,
                progress=progress,
                is_cancelled=is_cancelled,
                deadline=deadline,
            )
        tree_items = tree_data.get("tree", []) if isinstance(tree_data, dict) else []
        if not isinstance(tree_items, list) or not all(isinstance(item, dict) for item in tree_items):
            raise InvalidResponseError("GitHub вернул неожиданный формат дерева репозитория.")
        paths = {
            str(item.get("path", "")).replace("\\", "/").lower()
            for item in tree_items
            if item.get("type") in {"blob", "tree"}
        }
        basenames = {path.rsplit("/", 1)[-1] for path in paths}

        def has_named_file(stem: str) -> bool:
            return any(name == stem or name.startswith(f"{stem}.") for name in basenames)

        quality_files = {
            "LICENSE": has_named_file("license") or has_named_file("copying"),
            "CONTRIBUTING.md": has_named_file("contributing"),
            "SECURITY.md": has_named_file("security"),
            "CODE_OF_CONDUCT.md": has_named_file("code_of_conduct") or has_named_file("code-of-conduct"),
        }
        has_actions = any(path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")) for path in paths)
        has_tests = any(
            path.startswith(("tests/", "test/", "spec/", "__tests__/"))
            or "/tests/" in path
            or "/test/" in path
            or path.rsplit("/", 1)[-1].startswith(("test_", "spec_"))
            for path in paths
        )
        has_documentation = bool(readme) or any(
            path.startswith(("docs/", "doc/"))
            or path in {"docs", "doc"}
            or path in {"mkdocs.yml", "mkdocs.yaml", "docs.yml", "docs.yaml"}
            for path in paths
        )
        dependabot_configured = any(
            path in {".github/dependabot.yml", ".github/dependabot.yaml"}
            for path in paths
        )

        default_branch_protected: bool | None = None
        if default_branch != "—":
            branch_data = self._get(
                f"{base}/branches/{quote(default_branch, safe='')}",
                optional=True,
                expected_type=dict,
                progress=progress,
                is_cancelled=is_cancelled,
                deadline=deadline,
            )
            if isinstance(branch_data, dict) and isinstance(branch_data.get("protected"), bool):
                default_branch_protected = branch_data["protected"]

        self._report(progress, "Загрузка статистики коммитов…")
        commit_activity = self._get(
            f"{base}/stats/commit_activity",
            optional=True,
            expected_type=(list, dict),
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        )
        commit_counts = self._commit_counts(commit_activity) if isinstance(commit_activity, list) else {}

        self._report(progress, "Расчёт времени закрытия issues и pull requests…")
        closed_issues_data = self._get(
            f"{base}/issues?state=closed&sort=updated&direction=desc&per_page=100&page=1",
            optional=True,
            expected_type=list,
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        ) or []
        closed_pulls_data = self._get(
            f"{base}/pulls?state=closed&sort=updated&direction=desc&per_page=100&page=1",
            optional=True,
            expected_type=list,
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        ) or []
        self._validate_object_list(closed_issues_data)
        self._validate_object_list(closed_pulls_data)
        closed_issues = [item for item in closed_issues_data if "pull_request" not in item]
        merged_pulls = [item for item in closed_pulls_data if item.get("merged_at")]
        average_issue_close_hours = self._average_duration_hours(closed_issues, "closed_at")
        average_pull_merge_hours = self._average_duration_hours(merged_pulls, "merged_at")

        self._report(progress, "Подсчёт открытых issues и pull requests…")
        repository_query = f"repo:{owner}/{name}"
        open_issue_count = self._optional_search_count(
            f"{repository_query} type:issue state:open",
            progress=progress, is_cancelled=is_cancelled, deadline=deadline,
        )
        open_pull_request_count = self._optional_search_count(
            f"{repository_query} type:pr state:open",
            progress=progress, is_cancelled=is_cancelled, deadline=deadline,
        )
        if open_issue_count is None:
            open_issue_count = len(pages["issues"].items)
        if open_pull_request_count is None:
            open_pull_request_count = len(pages["pull_requests"].items)

        self._report(progress, "Проверка GitHub Actions…")
        _, workflow_data = self._permission_optional_get(
            f"{base}/actions/runs?status=success&per_page=1",
            expected_type=dict,
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        )
        last_successful_workflow = None
        if isinstance(workflow_data, dict):
            runs = workflow_data.get("workflow_runs", [])
            if isinstance(runs, list) and runs and isinstance(runs[0], dict):
                run = runs[0]
                last_successful_workflow = self._compact([run], (
                    "name", "display_title", "html_url", "updated_at", "conclusion",
                ))[0]

        self._report(progress, "Загрузка зависимостей…")
        dependency_status, sbom_data = self._permission_optional_get(
            f"{base}/dependency-graph/sbom",
            expected_type=dict,
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        )
        dependencies: list[dict[str, Any]] = []
        dependency_count = 0
        if isinstance(sbom_data, dict):
            packages = (sbom_data.get("sbom") or {}).get("packages", [])
            if isinstance(packages, list):
                for package in packages:
                    if not isinstance(package, dict) or package.get("SPDXID") == "SPDXRef-Repository":
                        continue
                    references = package.get("externalRefs") or []
                    purl = next((ref.get("referenceLocator") for ref in references
                                 if isinstance(ref, dict) and ref.get("referenceType") == "purl"), "")
                    dependencies.append({
                        "name": package.get("name") or "Неизвестный пакет",
                        "version": package.get("versionInfo") or "—",
                        "package_url": purl,
                    })
                dependency_count = len(dependencies)
                dependencies = dependencies[:50]

        self._report(progress, "Проверка Dependabot и уязвимостей…")
        dependabot_update_count = self._optional_search_count(
            f"{repository_query} is:pr is:open author:app/dependabot",
            progress=progress, is_cancelled=is_cancelled, deadline=deadline,
        )
        dependabot_status, alerts_data = self._permission_optional_get(
            f"{base}/dependabot/alerts?state=open&per_page=100",
            expected_type=list,
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        )
        dependabot_alerts: list[dict[str, Any]] = []
        if isinstance(alerts_data, list):
            self._validate_object_list(alerts_data)
            for alert in alerts_data:
                dependency = alert.get("dependency") or {}
                package = dependency.get("package") or {}
                advisory = alert.get("security_advisory") or {}
                vulnerability = alert.get("security_vulnerability") or {}
                patched = vulnerability.get("first_patched_version") or {}
                dependabot_alerts.append({
                    "package": package.get("name") or "Неизвестный пакет",
                    "ecosystem": package.get("ecosystem") or "—",
                    "severity": advisory.get("severity") or vulnerability.get("severity") or "unknown",
                    "summary": advisory.get("summary") or "Описание отсутствует.",
                    "patched_version": patched.get("identifier") or "Нет исправленной версии",
                    "html_url": alert.get("html_url") or "",
                })

        health_report = calculate_health_report(HealthMetrics(
            last_commit_date=last_commit,
            contributor_count=len(pages["contributors"].items),
            open_issue_count=open_issue_count,
            release_count=len(pages["releases"].items),
            has_readme=bool(readme),
        ))
        self._report(progress, "Формирование отчёта…")
        self._check_operation(is_cancelled, deadline)
        return RepositoryAnalysis(
            owner=owner,
            name=name,
            full_name=repo["full_name"],
            description=repo.get("description") or "Нет описания.",
            stars=repo.get("stargazers_count", 0),
            forks=repo.get("forks_count", 0),
            updated_at=repo.get("updated_at", "—"),
            last_commit_date=last_commit,
            languages=languages,
            contributors=pages["contributors"].items,
            open_issues=pages["issues"].items,
            pull_requests=pages["pull_requests"].items,
            releases=pages["releases"].items,
            readme=readme,
            health_score=health_report.total,
            health_breakdown=[{
                "key": category.key,
                "title": category.title,
                "points": category.points,
                "maximum": category.maximum,
                "explanation": category.explanation,
                "recommendation": category.recommendation,
            } for category in health_report.categories],
            contributors_has_more=pages["contributors"].has_more,
            issues_has_more=pages["issues"].has_more,
            pull_requests_has_more=pages["pull_requests"].has_more,
            releases_has_more=pages["releases"].has_more,
            open_issue_count=open_issue_count,
            open_pull_request_count=open_pull_request_count,
            commit_counts=commit_counts,
            average_issue_close_hours=average_issue_close_hours,
            average_pull_merge_hours=average_pull_merge_hours,
            quality_files=quality_files,
            has_actions=has_actions,
            has_tests=has_tests,
            has_documentation=has_documentation,
            is_archived=bool(repo.get("archived", False)),
            default_branch=default_branch,
            default_branch_protected=default_branch_protected,
            last_successful_workflow=last_successful_workflow,
            dependencies=dependencies,
            dependency_count=dependency_count,
            dependency_status=dependency_status,
            dependabot_configured=dependabot_configured,
            dependabot_update_count=dependabot_update_count,
            dependabot_alerts=dependabot_alerts,
            dependabot_status=dependabot_status,
        )

    def list_public_repositories(
        self,
        username: str,
        *,
        progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
    ) -> list[dict[str, str]]:
        """List a profile's public repositories for the selection dialog."""
        deadline = monotonic() + self.ANALYSIS_TIMEOUT_SECONDS
        data = self._get_all(
            f"/users/{username}/repos?type=public&sort=updated",
            progress=progress,
            is_cancelled=is_cancelled,
            deadline=deadline,
        )
        repositories: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item.get("full_name"), str):
                raise InvalidResponseError("GitHub вернул репозиторий без корректного имени.")
            repositories.append({
                "full_name": item["full_name"],
                "description": item.get("description") or "Нет описания.",
            })
        return repositories
