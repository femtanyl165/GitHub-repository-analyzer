"""Configurable repository evaluation profiles and scoring engine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class EvaluationCriterion:
    key: str
    title: str
    metric: str
    comparison: str
    target: float
    weight: int
    unit: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class EvaluationProfile:
    key: str
    name: str
    description: str
    criteria: tuple[EvaluationCriterion, ...]


@dataclass(frozen=True)
class EvaluationCategory:
    key: str
    title: str
    points: float
    maximum: int
    explanation: str
    recommendation: str
    available: bool = True


@dataclass(frozen=True)
class EvaluationReport:
    total: int
    profile_name: str
    categories: tuple[EvaluationCategory, ...]


CRITERION_LIBRARY = {
    "recent_commit": ("Свежесть проекта", "days_since_commit", "max", 30, "дн."),
    "commits_90": ("Активность за 90 дней", "commits_90", "min", 20, "коммитов"),
    "readme": ("README", "has_readme", "bool", 1, ""),
    "tests": ("Автоматические тесты", "has_tests", "bool", 1, ""),
    "actions": ("GitHub Actions", "has_actions", "bool", 1, ""),
    "license": ("Лицензия", "has_license", "bool", 1, ""),
    "branch_protection": ("Защита основной ветки", "branch_protected", "bool", 1, ""),
    "pr_response": ("Скорость обработки PR", "average_pr_hours", "max", 72, "ч"),
    "vulnerabilities": ("Известные уязвимости", "vulnerability_count", "max_zero", 0, ""),
    "contributors": ("Участники", "contributors", "min", 3, "участника"),
    "releases": ("Релизы", "releases", "min", 1, "релиз"),
    "documentation": ("Документация", "has_documentation", "bool", 1, ""),
}


def criterion(key: str, weight: int, target: float | None = None, *, enabled: bool = True) -> EvaluationCriterion:
    title, metric, comparison, default_target, unit = CRITERION_LIBRARY[key]
    return EvaluationCriterion(
        key=key,
        title=title,
        metric=metric,
        comparison=comparison,
        target=default_target if target is None else target,
        weight=weight,
        unit=unit,
        enabled=enabled,
    )


PRESET_PROFILES = {
    "open_source": EvaluationProfile(
        "open_source",
        "Open Source",
        "Сообщество, документация, регулярная активность и безопасная публикация.",
        (
            criterion("recent_commit", 15, 30), criterion("commits_90", 10, 20),
            criterion("readme", 10), criterion("documentation", 5), criterion("tests", 10),
            criterion("actions", 10), criterion("license", 10), criterion("contributors", 10, 3),
            criterion("releases", 10, 1), criterion("vulnerabilities", 10),
        ),
    ),
    "work": EvaluationProfile(
        "work",
        "Рабочий проект",
        "Надёжность разработки, контроль изменений и скорость работы команды.",
        (
            criterion("recent_commit", 15, 14), criterion("commits_90", 10, 30),
            criterion("readme", 5), criterion("tests", 15), criterion("actions", 15),
            criterion("branch_protection", 15), criterion("pr_response", 10, 72),
            criterion("vulnerabilities", 15),
        ),
    ),
    "study": EvaluationProfile(
        "study",
        "Учебный проект",
        "Понятность, завершённость и базовые инженерные практики.",
        (
            criterion("recent_commit", 15, 90), criterion("readme", 25),
            criterion("documentation", 15), criterion("tests", 20), criterion("actions", 10),
            criterion("license", 5), criterion("releases", 10, 1),
        ),
    ),
}


def clone_profile(profile: EvaluationProfile, *, name: str | None = None, key: str = "custom") -> EvaluationProfile:
    return EvaluationProfile(key, name or profile.name, profile.description, tuple(replace(item) for item in profile.criteria))


def _days_since(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return float(max(0, (now - parsed).days))


def repository_metrics(repository: Any, now: datetime | None = None) -> dict[str, float | bool | None]:
    """Extract values used by profiles from a RepositoryAnalysis-like object."""
    now = now or datetime.now(timezone.utc)
    quality_files = getattr(repository, "quality_files", {}) or {}
    dependabot_status = getattr(repository, "dependabot_status", "permission_required")
    vulnerabilities = (
        len(getattr(repository, "dependabot_alerts", []) or [])
        if dependabot_status == "available" else None
    )
    branch_protected = getattr(repository, "default_branch_protected", None)
    return {
        "days_since_commit": _days_since(getattr(repository, "last_commit_date", None), now),
        "commits_90": (getattr(repository, "commit_counts", {}) or {}).get(90),
        "has_readme": bool(getattr(repository, "readme", None)),
        "has_tests": bool(getattr(repository, "has_tests", False)),
        "has_actions": bool(getattr(repository, "has_actions", False)),
        "has_license": bool(quality_files.get("LICENSE")),
        "branch_protected": branch_protected,
        "average_pr_hours": getattr(repository, "average_pull_merge_hours", None),
        "vulnerability_count": vulnerabilities,
        "contributors": len(getattr(repository, "contributors", []) or []),
        "releases": len(getattr(repository, "releases", []) or []),
        "has_documentation": bool(getattr(repository, "has_documentation", False)),
    }


def _ratio(actual: float | bool, criterion_value: EvaluationCriterion) -> float:
    target = max(0.0, float(criterion_value.target))
    if criterion_value.comparison == "bool":
        return 1.0 if bool(actual) == bool(target) else 0.0
    value = max(0.0, float(actual))
    if criterion_value.comparison == "min":
        return 1.0 if target == 0 else min(1.0, value / target)
    if criterion_value.comparison == "max_zero":
        return 1.0 if value <= target else 0.0
    if criterion_value.comparison == "max":
        if value <= target:
            return 1.0
        return 0.0 if value == 0 else min(1.0, target / value)
    raise ValueError(f"Unknown comparison: {criterion_value.comparison}")


def _format_value(value: float | bool, item: EvaluationCriterion) -> str:
    if item.comparison == "bool":
        return "есть" if bool(value) else "нет"
    number = int(value) if float(value).is_integer() else round(float(value), 1)
    return f"{number} {item.unit}".strip()


def evaluate_repository(repository: Any, profile: EvaluationProfile, now: datetime | None = None) -> EvaluationReport:
    values = repository_metrics(repository, now)
    categories: list[EvaluationCategory] = []
    earned = 0.0
    available_weight = 0
    for item in profile.criteria:
        if not item.enabled or item.weight <= 0:
            continue
        actual = values.get(item.metric)
        if actual is None:
            categories.append(EvaluationCategory(
                item.key, item.title, 0, item.weight,
                "GitHub не предоставил достаточно данных для проверки.",
                "Разрешите доступ к этим данным или повторите анализ позже.", False,
            ))
            continue
        ratio = _ratio(actual, item)
        points = ratio * item.weight
        earned += points
        available_weight += item.weight
        target_text = _format_value(item.target, item)
        actual_text = _format_value(actual, item)
        comparison_text = {
            "min": f"не менее {target_text}",
            "max": f"не более {target_text}",
            "max_zero": "нет известных уязвимостей",
            "bool": "обязательно",
        }[item.comparison]
        passed = ratio >= 0.999
        recommendation = (
            "Критерий выполнен — поддерживайте текущее состояние."
            if passed else
            f"Доведите показатель до требования: {comparison_text}."
        )
        categories.append(EvaluationCategory(
            item.key, item.title, round(points, 1), item.weight,
            f"Фактически: {actual_text}. Требование: {comparison_text}.", recommendation,
        ))
    total = round(earned / available_weight * 100) if available_weight else 0
    return EvaluationReport(max(0, min(100, total)), profile.name, tuple(categories))


def profile_with_updates(
    base: EvaluationProfile,
    updates: dict[str, tuple[bool, int, float]],
    *,
    name: str = "Своя оценка",
) -> EvaluationProfile:
    criteria = tuple(
        replace(item, enabled=updates[item.key][0], weight=updates[item.key][1], target=updates[item.key][2])
        if item.key in updates else item
        for item in base.criteria
    )
    return EvaluationProfile("custom", name, "Пользовательские критерии и веса.", criteria)
