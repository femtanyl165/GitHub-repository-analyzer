"""Deterministic repository health score calculation."""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class HealthMetrics:
    last_commit_date: str | None
    contributor_count: int
    open_issue_count: int
    release_count: int
    has_readme: bool


@dataclass(frozen=True)
class HealthCategory:
    key: str
    title: str
    points: int
    maximum: int
    explanation: str
    recommendation: str


@dataclass(frozen=True)
class HealthReport:
    total: int
    categories: tuple[HealthCategory, ...]


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def calculate_health_report(metrics: HealthMetrics, now: datetime | None = None) -> HealthReport:
    """Return the score and a user-facing breakdown for all five categories."""
    now = now or datetime.now(timezone.utc)
    categories: list[HealthCategory] = []
    last_commit = _parse_date(metrics.last_commit_date)
    if last_commit:
        days = max(0, (now - last_commit).days)
        activity = 35 if days <= 30 else 25 if days <= 90 else 15 if days <= 365 else 5
        activity_explanation = f"Последний коммит был {days} дн. назад."
        activity_recommendation = (
            "Активность высокая — поддерживайте регулярный темп изменений."
            if activity == 35 else
            "Публикуйте небольшие изменения чаще и зафиксируйте план ближайших работ."
        )
    else:
        activity = 0
        activity_explanation = "Дата последнего коммита недоступна."
        activity_recommendation = "Добавьте актуальный коммит и убедитесь, что основная ветка доступна GitHub API."
    categories.append(HealthCategory(
        "activity", "Активность", activity, 35, activity_explanation, activity_recommendation,
    ))

    count = metrics.contributor_count
    community = 20 if count >= 10 else 15 if count >= 3 else 8 if count >= 1 else 0
    categories.append(HealthCategory(
        "community", "Сообщество", community, 20,
        f"Обнаружено участников: {count}.",
        "Сообщество устойчиво — продолжайте отмечать вклад участников."
        if community == 20 else
        "Добавьте CONTRIBUTING.md, задачи для новичков и понятные правила участия.",
    ))

    # A managed, non-overwhelming issue queue indicates active issue tracking.
    issues = metrics.open_issue_count
    issue_points = 8 if issues == 0 else 15 if issues <= 100 else 10 if issues <= 500 else 5
    categories.append(HealthCategory(
        "issues", "Работа с issues", issue_points, 15,
        f"Открытых issues: {issues}.",
        "Очередь выглядит управляемой — регулярно закрывайте устаревшие задачи."
        if issue_points == 15 else
        "Разберите очередь, добавьте метки и приоритеты, закройте неактуальные issues."
        if issues > 100 else
        "Используйте issues для публичного планирования ошибок и улучшений.",
    ))

    releases = metrics.release_count
    release_points = 15 if releases >= 5 else 10 if releases >= 1 else 0
    categories.append(HealthCategory(
        "releases", "Релизы", release_points, 15,
        f"В выборке найдено релизов: {releases}.",
        "История релизов сформирована — продолжайте публиковать версии и changelog."
        if release_points == 15 else
        "Публикуйте версионированные релизы и краткий список изменений для пользователей.",
    ))

    documentation = 15 if metrics.has_readme else 0
    categories.append(HealthCategory(
        "documentation", "Документация", documentation, 15,
        "README найден и доступен." if metrics.has_readme else "README не найден.",
        "Поддерживайте инструкции по установке и примеры использования в актуальном состоянии."
        if metrics.has_readme else
        "Добавьте README с назначением проекта, установкой, запуском и примерами использования.",
    ))

    total = max(0, min(100, sum(category.points for category in categories)))
    return HealthReport(total, tuple(categories))


def calculate_health_score(metrics: HealthMetrics, now: datetime | None = None) -> int:
    """Return a 0–100 score based on activity, community and project hygiene."""
    return calculate_health_report(metrics, now).total
