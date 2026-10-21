from datetime import datetime
from html import escape
import re
from threading import Event
from typing import Any

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QThread, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QKeySequence, QResizeEvent, QTextDocument, QShortcut
from PySide6.QtWidgets import (
    QGridLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from models.repository import RepositoryAnalysis, RepositoryPage
from services.github_service import AnalysisCancelledError, GitHubError, GitHubService, parse_profile_url
from ui.components import (
    AnimatedStackedWidget,
    BottomNavigation,
    DualSectionPage,
    EvaluationSettingsDialog,
    HealthDetailsDialog,
    HealthScoreCard,
    ListSectionCard,
    MetricCard,
    NavigationRail,
    OverviewPage,
    QualityPage,
    RepositoryHeader,
    TopBar,
)
from ui.theme import (
    ANIMATIONS_ENABLED,
    APP_STYLESHEET,
    COLORS,
    DOCUMENT_CSS,
    NAVIGATION_ANIMATION_MS,
    style_markdown,
)
from utils.evaluation import EvaluationProfile, PRESET_PROFILES, evaluate_repository


class GitHubWorker(QObject):
    progress = Signal(str)
    result_ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(self, task: str, payload: Any, cancel_event: Event) -> None:
        super().__init__()
        self.task = task
        self.payload = payload
        self.cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        service = GitHubService()
        try:
            if self.task == "analyze":
                value = str(self.payload)
                username = parse_profile_url(value)
                if username:
                    repositories = service.list_public_repositories(
                        username,
                        progress=self.progress.emit,
                        is_cancelled=self.cancel_event.is_set,
                    )
                    if not repositories:
                        raise GitHubError("У этого пользователя нет публичных репозиториев.")
                    self.result_ready.emit(("repositories", repositories))
                else:
                    result = service.analyze(
                        value,
                        progress=self.progress.emit,
                        is_cancelled=self.cancel_event.is_set,
                    )
                    self.result_ready.emit(("analysis", result))
            elif self.task == "load_more":
                repository, category, page = self.payload
                labels = {
                    "issues": "issues",
                    "pull_requests": "pull requests",
                    "contributors": "contributors",
                    "releases": "releases",
                }
                self.progress.emit(f"Загрузка {labels[category]}: страница {page}…")
                result = service.load_page(
                    repository,
                    category,
                    page,
                    progress=self.progress.emit,
                    is_cancelled=self.cancel_event.is_set,
                )
                self.result_ready.emit(("page", result))
            else:
                raise GitHubError("Неизвестная фоновая операция.")
        except AnalysisCancelledError:
            self.cancelled.emit()
        except GitHubError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Непредвиденная ошибка: {exc}")
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RepoScope — GitHub Repository Analyzer")
        self.resize(1380, 880)
        self.setMinimumSize(560, 620)
        self.setStyleSheet(APP_STYLESHEET)
        self.current_result: RepositoryAnalysis | None = None
        self._pages = {"contributors": 1, "issues": 1, "pull_requests": 1, "releases": 1}
        self._thread: QThread | None = None
        self._worker: GitHubWorker | None = None
        self._cancel_event: Event | None = None
        self._pending_outcome: tuple[str, Any] | None = None
        self._busy = False
        self._metric_columns = 0
        self._layout_mode = ""
        self._uses_bottom_navigation: bool | None = None
        self._animations_enabled = ANIMATIONS_ENABLED
        self.evaluation_profile = PRESET_PROFILES["open_source"]

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        desktop_row = QHBoxLayout()
        desktop_row.setContentsMargins(0, 0, 0, 0)
        desktop_row.setSpacing(0)
        self.navigation = NavigationRail()
        self.navigation.page_requested.connect(self._show_page)
        desktop_row.addWidget(self.navigation)

        workspace = QWidget()
        workspace.setObjectName("workspace")
        self.workspace_layout = QVBoxLayout(workspace)
        self.workspace_layout.setContentsMargins(20, 16, 20, 16)
        self.workspace_layout.setSpacing(12)

        self.top_bar = TopBar()
        self.repository_input = self.top_bar.repository_input
        self.analyze_button = self.top_bar.analyze_button
        self.cancel_button = self.top_bar.cancel_button
        self.criteria_button = self.top_bar.criteria_button
        self.analyze_button.clicked.connect(self.analyze)
        self.cancel_button.clicked.connect(self.cancel_analysis)
        self.criteria_button.clicked.connect(self._show_evaluation_settings)
        self.repository_input.returnPressed.connect(self.analyze)
        self.workspace_layout.addWidget(self.top_bar)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.status_dot = QLabel("●")
        self.status_dot.setFixedWidth(12)
        self.status_label = QLabel("Готово к анализу.")
        self.status_label.setObjectName("mutedLabel")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(130)
        self.progress_bar.hide()
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.progress_bar)
        self.workspace_layout.addLayout(status_row)

        self.dashboard_scroll = QScrollArea()
        self.dashboard_scroll.setObjectName("dashboardScroll")
        self.dashboard_scroll.setWidgetResizable(True)
        self.dashboard_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dashboard_content = QWidget()
        self.dashboard_content.setObjectName("dashboardContent")
        self.dashboard_layout = QVBoxLayout(self.dashboard_content)
        self.dashboard_layout.setContentsMargins(0, 0, 4, 4)
        self.dashboard_layout.setSpacing(12)

        self.repository_header = RepositoryHeader()
        self.repository_header.open_requested.connect(self._open_repository)
        self.repository_header.refresh_requested.connect(self._reanalyze)
        self.repository_header.hide()
        self.dashboard_layout.addWidget(self.repository_header)

        self.metrics_panel = QWidget()
        self.metrics_layout = QGridLayout(self.metrics_panel)
        self.metrics_layout.setContentsMargins(0, 0, 0, 0)
        self.metrics_layout.setSpacing(12)
        self.health_card = HealthScoreCard()
        self.health_card.details_requested.connect(self._show_health_details)
        self.health_card.settings_requested.connect(self._show_evaluation_settings)
        self._health_dialog: HealthDetailsDialog | None = None
        self._evaluation_dialog: EvaluationSettingsDialog | None = None
        self.stars_card = MetricCard("★  Stars", accent="stars")
        self.forks_card = MetricCard("Forks")
        self.updated_card = MetricCard("Последнее обновление", technical=True)
        self.metric_cards = [self.health_card, self.stars_card, self.forks_card, self.updated_card]
        self._layout_metric_cards(4)
        self.metrics_panel.hide()
        self.dashboard_layout.addWidget(self.metrics_panel)

        self.page_stack = AnimatedStackedWidget(animations_enabled=ANIMATIONS_ENABLED)
        self.page_stack.setObjectName("pageStack")
        self.page_stack.setMinimumHeight(180)
        self.tabs = self.page_stack  # Compatibility for existing callers/tests.

        self.overview_page = OverviewPage()
        self.overview = self.overview_page.summary
        self.issues_card = ListSectionCard("Открытые issues", "Нет открытых issues.", "Показать ещё issues")
        self.pulls_card = ListSectionCard("Pull requests", "Нет открытых pull requests.", "Показать ещё pull requests")
        self.activity_page = DualSectionPage(self.issues_card, self.pulls_card)
        self.contributors_card = ListSectionCard("Contributors", "Нет данных об участниках.", "Показать ещё contributors")
        self.releases_card = ListSectionCard("Releases", "Релизы не найдены.", "Показать ещё releases")
        self.community_page = DualSectionPage(self.contributors_card, self.releases_card)
        self.quality_page = QualityPage()
        self.readme = self._make_readme_browser()

        # Compatibility names retain the original public interface.
        self.activity = self.issues_card.browser
        self.community = self.contributors_card.browser
        self.more_issues_button = self.issues_card.more_button
        self.more_pulls_button = self.pulls_card.more_button
        self.more_contributors_button = self.contributors_card.more_button
        self.more_releases_button = self.releases_card.more_button

        self.more_issues_button.clicked.connect(lambda: self.load_more("issues"))
        self.more_pulls_button.clicked.connect(lambda: self.load_more("pull_requests"))
        self.more_contributors_button.clicked.connect(lambda: self.load_more("contributors"))
        self.more_releases_button.clicked.connect(lambda: self.load_more("releases"))
        for browser in (self.issues_card.browser, self.pulls_card.browser,
                        self.contributors_card.browser, self.releases_card.browser,
                        *(card.browser for card in self.quality_page.cards)):
            browser.setOpenLinks(False)
            browser.setOpenExternalLinks(False)
            browser.anchorClicked.connect(self._open_github_link)

        self.page_stack.addWidget(self.overview_page)
        self.page_stack.addWidget(self.activity_page)
        self.page_stack.addWidget(self.community_page)
        self.page_stack.addWidget(self.quality_page)
        self.page_stack.addWidget(self.readme)
        self.dashboard_layout.addWidget(self.page_stack, 1)
        self.dashboard_scroll.setWidget(self.dashboard_content)
        self.workspace_layout.addWidget(self.dashboard_scroll, 1)
        desktop_row.addWidget(workspace, 1)
        root_layout.addLayout(desktop_row, 1)

        self.bottom_navigation = BottomNavigation()
        self.bottom_navigation.page_requested.connect(self._show_page)
        self.bottom_navigation.hide()
        root_layout.addWidget(self.bottom_navigation)
        self._setup_navigation_fades()
        self.setCentralWidget(root)

        self.search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.search_shortcut.activated.connect(self._focus_search)
        self._set_welcome()
        self._set_status("Готово к анализу.", "idle")
        self._update_more_buttons()
        self._apply_responsive_layout(self.width())

    def _make_readme_browser(self):
        from PySide6.QtWidgets import QTextBrowser

        browser = QTextBrowser()
        browser.setObjectName("readmeBrowser")
        browser.document().setDefaultStyleSheet(DOCUMENT_CSS)
        browser.setOpenLinks(False)
        browser.setOpenExternalLinks(False)
        browser.anchorClicked.connect(self._open_safe_link)
        return browser

    def _set_welcome(self) -> None:
        self.overview.setHtml(
            f'<p style="color:{COLORS["blue"]}; font-size:12px;">ДОБРО ПОЖАЛОВАТЬ В REPOSCOPE</p>'
            '<h1>Исследуйте GitHub-репозиторий</h1>'
            f'<p style="color:{COLORS["muted"]};">Введите адрес в верхней строке. Анализ выполняется в фоне, '
            'его можно отменить в любой момент.</p>'
            '<h3>Поддерживаемые форматы</h3>'
            '<p><code>owner/repository</code> — короткое имя</p>'
            '<p><code>https://github.com/owner/repository</code> — ссылка на репозиторий</p>'
            '<p><code>https://github.com/owner?tab=repositories</code> — профиль с выбором репозитория</p>'
            f'<p style="color:{COLORS["muted"]};">Нажмите <code>Ctrl+K</code>, чтобы перейти к поиску.</p>'
        )
        self.overview_page.languages.hide()
        for card in (self.issues_card, self.pulls_card, self.contributors_card, self.releases_card):
            card.browser.setHtml(f'<p style="color:{COLORS["muted"]};">Данные появятся после анализа.</p>')
        for card in self.quality_page.cards:
            card.browser.setHtml(f'<p style="color:{COLORS["muted"]};">Данные появятся после анализа.</p>')
        self.readme.setHtml(f'<h2>README</h2><p style="color:{COLORS["muted"]};">Документ появится после анализа репозитория.</p>')

    def _focus_search(self) -> None:
        self.repository_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.repository_input.selectAll()

    @Slot(int)
    def _show_page(self, index: int) -> None:
        if not (0 <= index < self.page_stack.count()):
            return
        changed = index != self.page_stack.currentIndex()
        self.navigation.set_current(index, animate=changed)
        self.bottom_navigation.set_current(index, animate=changed)
        if index == 4:
            self.repository_header.hide()
            self.metrics_panel.hide()
            self.dashboard_scroll.verticalScrollBar().setValue(0)
        elif self.current_result is not None:
            self.repository_header.show()
            self.metrics_panel.show()
        self.dashboard_layout.activate()
        if changed:
            self.page_stack.setCurrentIndexAnimated(index)

    def _setup_navigation_fades(self) -> None:
        self._navigation_effects: dict[QWidget, QGraphicsOpacityEffect] = {}
        self._navigation_fades: dict[QWidget, QPropertyAnimation] = {}
        for navigation in (self.navigation, self.bottom_navigation):
            effect = QGraphicsOpacityEffect(navigation)
            effect.setOpacity(1.0)
            navigation.setGraphicsEffect(effect)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(NAVIGATION_ANIMATION_MS)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._navigation_effects[navigation] = effect
            self._navigation_fades[navigation] = animation

    def set_animations_enabled(self, enabled: bool) -> None:
        """Enable or disable every navigation animation with one setting."""
        self._animations_enabled = bool(enabled)
        self.page_stack.set_animations_enabled(enabled)
        self.navigation.set_animations_enabled(enabled)
        self.bottom_navigation.set_animations_enabled(enabled)
        if not self._animations_enabled:
            for animation in self._navigation_fades.values():
                animation.stop()
            for effect in self._navigation_effects.values():
                effect.setOpacity(1.0)

    def _switch_navigation(self, use_bottom: bool, *, animate: bool) -> None:
        active = self.bottom_navigation if use_bottom else self.navigation
        inactive = self.navigation if use_bottom else self.bottom_navigation
        if self._uses_bottom_navigation == use_bottom:
            inactive.hide()
            active.show()
            active.sync_indicator()
            return
        for animation in self._navigation_fades.values():
            animation.stop()
        for effect in self._navigation_effects.values():
            effect.setOpacity(1.0)
        inactive.hide()
        active.show()
        active.sync_indicator()
        self._uses_bottom_navigation = use_bottom
        if animate and self._animations_enabled and self.isVisible():
            effect = self._navigation_effects[active]
            animation = self._navigation_fades[active]
            effect.setOpacity(0.45)
            animation.setStartValue(0.45)
            animation.setEndValue(1.0)
            animation.start()

    def _layout_metric_cards(self, columns: int) -> None:
        if columns == self._metric_columns:
            return
        for card in self.metric_cards:
            self.metrics_layout.removeWidget(card)
        for column in range(5):
            self.metrics_layout.setColumnStretch(column, 0)
        if columns == 4:
            self.metrics_layout.addWidget(self.health_card, 0, 0, 1, 2)
            self.metrics_layout.addWidget(self.stars_card, 0, 2)
            self.metrics_layout.addWidget(self.forks_card, 0, 3)
            self.metrics_layout.addWidget(self.updated_card, 0, 4)
            for column in range(5):
                self.metrics_layout.setColumnStretch(column, 1)
            self.metrics_panel.setMinimumHeight(168)
        elif columns == 2:
            self.metrics_layout.addWidget(self.health_card, 0, 0, 1, 2)
            self.metrics_layout.addWidget(self.stars_card, 1, 0)
            self.metrics_layout.addWidget(self.forks_card, 1, 1)
            self.metrics_layout.addWidget(self.updated_card, 2, 0, 1, 2)
            self.metrics_layout.setColumnStretch(0, 1)
            self.metrics_layout.setColumnStretch(1, 1)
            self.metrics_panel.setMinimumHeight(416)
        else:
            for row, card in enumerate(self.metric_cards):
                self.metrics_layout.addWidget(card, row, 0)
            self.metrics_layout.setColumnStretch(0, 1)
            self.metrics_panel.setMinimumHeight(540)
        self._metric_columns = columns

    def _apply_responsive_layout(self, width: int) -> None:
        if width >= 1180:
            mode = "wide"
            self.navigation.set_collapsed(False)
            self._layout_metric_cards(4)
            compact_lists = False
            self.page_stack.setMinimumHeight(180)
            self.repository_header.set_compact(False)
            use_bottom = False
        elif width >= 800:
            mode = "medium"
            self.navigation.set_collapsed(True)
            self._layout_metric_cards(4 if width >= 1040 else 2)
            compact_lists = width < 980
            self.page_stack.setMinimumHeight(150)
            self.repository_header.set_compact(False)
            use_bottom = False
        else:
            mode = "narrow"
            self._layout_metric_cards(2 if width >= 650 else 1)
            compact_lists = True
            self.page_stack.setMinimumHeight(100)
            self.repository_header.set_compact(width < 680)
            use_bottom = True
        self.activity_page.set_compact(compact_lists)
        self.community_page.set_compact(compact_lists)
        self.quality_page.set_compact(compact_lists)
        self.workspace_layout.setContentsMargins(20 if width >= 800 else 12, 16, 20 if width >= 800 else 12, 12)
        self._switch_navigation(use_bottom, animate=bool(self._layout_mode) and mode != self._layout_mode)
        self._layout_mode = mode

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "navigation"):
            self._apply_responsive_layout(event.size().width())

    @staticmethod
    def _format_date(value: str | None) -> str:
        if not value:
            return "Нет данных"
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d.%m.%Y")
        except ValueError:
            return "Нет данных"

    @Slot(QUrl)
    def _open_github_link(self, url: QUrl) -> None:
        if not url.isValid() or url.scheme().lower() != "https" or url.host().lower() not in {"github.com", "www.github.com"}:
            QMessageBox.warning(self, "Небезопасная ссылка", "Приложение открывает только HTTPS-ссылки GitHub.")
            return
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "Не удалось открыть ссылку", "Системный браузер не смог открыть ссылку GitHub.")

    @Slot(QUrl)
    def _open_safe_link(self, url: QUrl) -> None:
        if not url.isValid() or url.scheme().lower() != "https":
            QMessageBox.warning(self, "Небезопасная ссылка", "В README разрешены только HTTPS-ссылки.")
            return
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "Не удалось открыть ссылку", "Системный браузер не смог открыть ссылку.")

    def _open_repository(self) -> None:
        if self.current_result:
            self._open_github_link(QUrl(f"https://github.com/{self.current_result.owner}/{self.current_result.name}"))

    def _reanalyze(self) -> None:
        if self.current_result and not self._busy:
            self.repository_input.setText(self.current_result.full_name)
            self.analyze()

    @staticmethod
    def _list(items: list[dict], formatter) -> str:
        return "".join(f"<div style='margin-bottom:10px;'>{formatter(item)}</div>" for item in items) or f'<p style="color:{COLORS["muted"]};">Нет данных.</p>'

    @staticmethod
    def _html(value: object) -> str:
        return escape(str(value), quote=True)

    def analyze(self) -> None:
        if self._busy:
            return
        value = self.repository_input.text().strip()
        if not value:
            QMessageBox.information(self, "Репозиторий не указан", "Введите owner/repository или ссылку GitHub.")
            return
        self._start_task("analyze", value)

    def cancel_analysis(self) -> None:
        if not self._cancel_event or not self._busy:
            return
        self._cancel_event.set()
        self.cancel_button.setEnabled(False)
        self._set_status("Отмена после завершения текущего сетевого запроса…", "warning")

    def load_more(self, category: str) -> None:
        if self._busy or not self.current_result:
            return
        self._start_task("load_more", (self.current_result.full_name, category, self._pages[category] + 1))

    def _start_task(self, task: str, payload: Any) -> None:
        if self._thread is not None:
            return
        self._pending_outcome = None
        self._cancel_event = Event()
        self._thread = QThread(self)
        self._worker = GitHubWorker(task, payload, self._cancel_event)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._set_loading_status)
        self._worker.result_ready.connect(self._store_result)
        self._worker.failed.connect(self._store_error)
        self._worker.cancelled.connect(self._store_cancelled)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._background_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._set_busy(True)
        self._set_status("Подготовка анализа…", "loading")
        self._thread.start()

    @Slot(str)
    def _set_loading_status(self, message: str) -> None:
        self._set_status(message, "loading")

    def _set_status(self, message: str, state: str) -> None:
        colors = {"idle": COLORS["muted"], "loading": COLORS["blue"], "success": COLORS["success"],
                  "warning": COLORS["warning"], "error": COLORS["danger"]}
        self.status_label.setText(message)
        self.status_dot.setStyleSheet(f"color:{colors.get(state, COLORS['muted'])};")

    @Slot(object)
    def _store_result(self, outcome: tuple[str, Any]) -> None:
        self._pending_outcome = outcome

    @Slot(str)
    def _store_error(self, message: str) -> None:
        self._pending_outcome = ("error", message)

    @Slot()
    def _store_cancelled(self) -> None:
        self._pending_outcome = ("cancelled", None)

    @Slot()
    def _background_finished(self) -> None:
        outcome = self._pending_outcome
        self._worker = None
        self._thread = None
        self._cancel_event = None
        self._pending_outcome = None
        self._set_busy(False)
        if outcome is None:
            self._set_status("Фоновая операция завершилась без результата.", "warning")
            return
        kind, payload = outcome
        if kind == "analysis":
            self.show_result(payload)
            self._set_status("Анализ завершён.", "success")
        elif kind == "repositories":
            self._choose_repository(payload)
        elif kind == "page":
            self._apply_page(payload)
        elif kind == "cancelled":
            self._set_status("Анализ отменён.", "warning")
        elif kind == "error":
            self._set_status("Не удалось выполнить операцию.", "error")
            QMessageBox.warning(self, "Не удалось выполнить анализ", payload)

    def _choose_repository(self, repositories: list[dict[str, str]]) -> None:
        choices = [f'{item["full_name"]} — {item["description"]}' for item in repositories]
        choice, accepted = QInputDialog.getItem(self, "Выберите репозиторий", "Публичные репозитории:", choices, 0, False)
        if not accepted:
            self._set_status("Выбор репозитория отменён.", "warning")
            return
        value = repositories[choices.index(choice)]["full_name"]
        self.repository_input.setText(value)
        self._start_task("analyze", value)

    def _apply_page(self, page: RepositoryPage) -> None:
        if not self.current_result:
            return
        attributes = {
            "contributors": ("contributors", "contributors_has_more"),
            "issues": ("open_issues", "issues_has_more"),
            "pull_requests": ("pull_requests", "pull_requests_has_more"),
            "releases": ("releases", "releases_has_more"),
        }
        items_attribute, more_attribute = attributes[page.category]
        getattr(self.current_result, items_attribute).extend(page.items)
        setattr(self.current_result, more_attribute, page.has_more)
        self._pages[page.category] = page.page
        if page.category in {"issues", "pull_requests"}:
            self._render_activity()
        else:
            self._render_community()
        self._update_more_buttons()
        self._update_navigation_counts()
        self._set_status(f"Страница {page.page} загружена: добавлено {len(page.items)}.", "success")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.top_bar.set_busy(busy)
        self.progress_bar.setVisible(busy)
        self.repository_header.refresh_button.setEnabled(not busy)
        self.health_card.set_interactive(self.current_result is not None and not busy)
        self._update_more_buttons()

    def _update_more_buttons(self) -> None:
        states = {
            self.more_issues_button: bool(self.current_result and self.current_result.issues_has_more),
            self.more_pulls_button: bool(self.current_result and self.current_result.pull_requests_has_more),
            self.more_contributors_button: bool(self.current_result and self.current_result.contributors_has_more),
            self.more_releases_button: bool(self.current_result and self.current_result.releases_has_more),
        }
        for button, visible in states.items():
            button.setVisible(visible)
            button.setEnabled(visible and not self._busy)

    def _update_navigation_counts(self) -> None:
        if not self.current_result:
            self.navigation.set_counts(0, 0)
            return
        self.navigation.set_counts(
            max(self.current_result.open_issue_count, len(self.current_result.open_issues))
            + max(self.current_result.open_pull_request_count, len(self.current_result.pull_requests)),
            len(self.current_result.contributors) + len(self.current_result.releases),
        )

    def show_result(self, result: RepositoryAnalysis) -> None:
        self.current_result = result
        self._apply_evaluation_profile(self.evaluation_profile, refresh_views=False)
        self._pages = {"contributors": 1, "issues": 1, "pull_requests": 1, "releases": 1}
        self.repository_header.set_repository(result.full_name, result.description)
        self.repository_header.show()
        self.health_card.set_score(result.health_score)
        self.health_card.set_profile(result.evaluation_profile_name)
        self.health_card.set_interactive(True)
        self.stars_card.set_value(f"{result.stars:,}".replace(",", " "))
        self.forks_card.set_value(f"{result.forks:,}".replace(",", " "))
        self.updated_card.set_value(self._format_date(result.updated_at))
        self.updated_card.setToolTip(result.updated_at)
        self.metrics_panel.show()
        self.overview_page.languages.show()
        self._render_overview()
        self._render_activity()
        self._render_community()
        self._render_quality()
        self._render_readme(result.readme)
        self._update_more_buttons()
        self._update_navigation_counts()
        self._show_page(0)

    def _show_health_details(self) -> None:
        if not self.current_result or not self.health_card.is_interactive():
            return
        breakdown = self.current_result.health_breakdown
        if not breakdown:
            report = evaluate_repository(self.current_result, self.evaluation_profile)
            breakdown = [{
                "key": category.key,
                "title": category.title,
                "points": category.points,
                "maximum": category.maximum,
                "explanation": category.explanation,
                "recommendation": category.recommendation,
                "available": category.available,
            } for category in report.categories]
        if self._health_dialog is None:
            self._health_dialog = HealthDetailsDialog(self)
        self._health_dialog.set_report(
            self.current_result.health_score, breakdown, self.current_result.evaluation_profile_name,
        )
        self._health_dialog.show()
        self._health_dialog.raise_()
        self._health_dialog.activateWindow()

    def _show_evaluation_settings(self) -> None:
        if self._evaluation_dialog is None:
            self._evaluation_dialog = EvaluationSettingsDialog(self)
            self._evaluation_dialog.profile_applied.connect(self._apply_evaluation_profile)
        self._evaluation_dialog.set_profile(self.evaluation_profile)
        self._evaluation_dialog.show()
        self._evaluation_dialog.raise_()
        self._evaluation_dialog.activateWindow()

    @Slot(object)
    def _apply_evaluation_profile(
        self, profile: EvaluationProfile, *, refresh_views: bool = True,
    ) -> None:
        self.evaluation_profile = profile
        self.health_card.set_profile(profile.name)
        if self.current_result is None:
            return
        report = evaluate_repository(self.current_result, profile)
        self.current_result.health_score = report.total
        self.current_result.evaluation_profile_name = report.profile_name
        self.current_result.health_breakdown = [{
            "key": category.key,
            "title": category.title,
            "points": category.points,
            "maximum": category.maximum,
            "explanation": category.explanation,
            "recommendation": category.recommendation,
            "available": category.available,
        } for category in report.categories]
        self.health_card.set_score(report.total)
        self.health_card.set_profile(report.profile_name)
        if refresh_views:
            self._render_overview()
            if self._health_dialog is not None and self._health_dialog.isVisible():
                self._health_dialog.set_report(
                    report.total, self.current_result.health_breakdown, report.profile_name,
                )

    def _render_readme(self, markdown: str | None) -> None:
        safe_markdown = self._prepare_markdown(markdown or "README отсутствует.")
        self.readme.document().setMarkdown(safe_markdown, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
        style_markdown(self.readme.document())

    @staticmethod
    def _prepare_markdown(markdown: str) -> str:
        converted = re.sub(
            r"<summary\s*>(.*?)</summary\s*>",
            lambda match: f"\n\n### {re.sub(r'\s+', ' ', match.group(1)).strip()}\n\n",
            markdown,
            flags=re.IGNORECASE | re.DOTALL,
        )
        converted = re.sub(r"</?details(?:\s+open)?\s*>", "\n\n", converted, flags=re.IGNORECASE)
        return converted.replace("&", "&amp;").replace("<", "&lt;")

    def _render_overview(self) -> None:
        if not self.current_result:
            return
        result = self.current_result
        h = self._html
        self.overview.setHtml(
            '<h2>Основные сведения</h2>'
            f'<p><b>Репозиторий:</b> <code>{h(result.full_name)}</code></p>'
            f'<p>{h(result.description)}</p>'
            f'<p><b>Последний коммит:</b> <code>{h(result.last_commit_date or "Нет данных.")}</code></p>'
            f'<p><b>Обновлён:</b> <code>{h(result.updated_at)}</code></p>'
            '<h3>Как рассчитана оценка</h3>'
            f'<p style="color:{COLORS["muted"]};">Профиль <b>{h(result.evaluation_profile_name)}</b> дал '
            f'{result.health_score}/100. Балл рассчитан по выбранным требованиям, порогам и весам. '
            'Недоступные через GitHub данные не снижают итог. Нажмите «Настроить» в карточке оценки, '
            'чтобы изменить правила.</p>'
        )
        self.overview_page.languages.set_languages(result.languages)

    def _render_activity(self) -> None:
        if not self.current_result:
            return
        result = self.current_result
        h = self._html
        self.issues_card.set_count(max(result.open_issue_count, len(result.open_issues)))
        self.issues_card.browser.setHtml(self._list(
            result.open_issues,
            lambda item: f'<a href="{h(item.get("html_url", ""))}"><b>#{h(item.get("number", ""))}</b> '
                         f'{h(item.get("title", "Без названия"))}</a><br>'
                         f'<span style="color:{COLORS["muted"]}; font-size:12px;">Создан: '
                         f'{h(self._format_date(item.get("created_at")))}</span>',
        ))
        self.pulls_card.set_count(max(result.open_pull_request_count, len(result.pull_requests)))
        self.pulls_card.browser.setHtml(self._list(
            result.pull_requests,
            lambda item: f'<a href="{h(item.get("html_url", ""))}"><b>#{h(item.get("number", ""))}</b> '
                         f'{h(item.get("title", "Без названия"))}</a><br>'
                         f'<span style="color:{COLORS["muted"]}; font-size:12px;">Автор: '
                         f'{h((item.get("user") or {}).get("login", "неизвестен") if isinstance(item.get("user"), dict) else "неизвестен")}'
                         f' · {h(self._format_date(item.get("created_at")))}</span>',
        ))

    def _render_community(self) -> None:
        if not self.current_result:
            return
        result = self.current_result
        h = self._html
        self.contributors_card.set_count(len(result.contributors))
        self.contributors_card.browser.setHtml(self._list(
            result.contributors,
            lambda item: f'<a href="{h(item.get("html_url", ""))}"><b>{h(item.get("login", "Неизвестный пользователь"))}</b></a><br>'
                         f'<span style="color:{COLORS["muted"]}; font-size:12px;">'
                         f'{h(item.get("contributions", 0))} contributions</span>',
        ))
        self.releases_card.set_count(len(result.releases))
        self.releases_card.browser.setHtml(self._list(
            result.releases,
            lambda item: f'<a href="{h(item.get("html_url", ""))}"><b>'
                         f'{h(item.get("name") or item.get("tag_name") or "Без названия")}</b></a><br>'
                         f'<span style="color:{COLORS["muted"]}; font-size:12px;">'
                         f'{h(item.get("tag_name") or "Без тега")} · {h(self._format_date(item.get("published_at")))}</span>',
        ))

    @staticmethod
    def _format_duration(hours: float | None) -> str:
        if hours is None:
            return "Недостаточно данных"
        if hours < 24:
            return f"{hours:.1f} ч"
        return f"{hours / 24:.1f} дн."

    def _render_quality(self) -> None:
        if not self.current_result:
            return
        result = self.current_result
        h = self._html

        def state(value: bool | None, yes: str = "Есть", no: str = "Нет") -> str:
            if value is None:
                return f'<span style="color:{COLORS["muted"]};">Не удалось определить</span>'
            color = COLORS["success"] if value else COLORS["danger"]
            return f'<span style="color:{color};"><b>{h(yes if value else no)}</b></span>'

        files = "".join(
            f"<p><code>{h(filename)}</code> — {state(present)}</p>"
            for filename, present in result.quality_files.items()
        ) or f'<p style="color:{COLORS["muted"]};">Дерево файлов недоступно.</p>'
        workflow = result.last_successful_workflow
        workflow_html = f'<span style="color:{COLORS["muted"]};">Нет успешных запусков.</span>'
        if workflow:
            title = workflow.get("display_title") or workflow.get("name") or "Workflow"
            url = workflow.get("html_url") or ""
            linked_title = f'<a href="{h(url)}">{h(title)}</a>' if url else h(title)
            workflow_html = f'{linked_title}<br><span style="color:{COLORS["muted"]};">{h(self._format_date(workflow.get("updated_at")))}</span>'
        self.quality_page.standards.browser.setHtml(
            files
            + f'<p><b>GitHub Actions:</b> {state(result.has_actions, "Настроены", "Не найдены")}</p>'
            + f'<p><b>Тесты:</b> {state(result.has_tests, "Найдены", "Не найдены")}</p>'
            + f'<p><b>Документация:</b> {state(result.has_documentation, "Найдена", "Не найдена")}</p>'
            + f'<p><b>Архивирован:</b> {state(not result.is_archived, "Нет", "Да")}</p>'
            + f'<p><b>Основная ветка:</b> <code>{h(result.default_branch)}</code></p>'
            + f'<p><b>Защита ветки:</b> {state(result.default_branch_protected, "Включена", "Выключена")}</p>'
            + f'<p><b>Последний успешный workflow:</b><br>{workflow_html}</p>'
        )

        counts = result.commit_counts
        commits_html = (
            f'<p><b>Коммиты за 30 дней:</b> {h(counts.get(30, 0))}</p>'
            f'<p><b>Коммиты за 90 дней:</b> {h(counts.get(90, 0))}</p>'
            f'<p><b>Коммиты за 365 дней:</b> {h(counts.get(365, 0))}</p>'
            if counts else f'<p style="color:{COLORS["muted"]};">Статистика коммитов пока недоступна.</p>'
        )
        self.quality_page.activity.browser.setHtml(
            commits_html
            + f'<p><b>Открытые issues:</b> {h(result.open_issue_count)}</p>'
            + f'<p><b>Открытые pull requests:</b> {h(result.open_pull_request_count)}</p>'
            + f'<p><b>Среднее закрытие issue:</b> {h(self._format_duration(result.average_issue_close_hours))}</p>'
            + f'<p><b>Среднее слияние PR:</b> {h(self._format_duration(result.average_pull_merge_hours))}</p>'
            + f'<p style="color:{COLORS["muted"]}; font-size:12px;">Средние значения рассчитаны по последним 100 закрытым элементам.</p>'
        )

        if result.dependency_status == "available":
            dependency_rows = "".join(
                f'<p><code>{h(item.get("name", "Пакет"))}</code> '
                f'<span style="color:{COLORS["muted"]};">{h(item.get("version", "—"))}</span></p>'
                for item in result.dependencies[:25]
            ) or f'<p style="color:{COLORS["muted"]};">Зависимости не обнаружены.</p>'
            dependency_intro = f'<p><b>Всего зависимостей:</b> {h(result.dependency_count)}</p>'
        elif result.dependency_status == "permission_required":
            dependency_intro = f'<p style="color:{COLORS["warning"]};">Для dependency graph токену не хватает разрешения Contents: read.</p>'
            dependency_rows = ""
        else:
            dependency_intro = f'<p style="color:{COLORS["muted"]};">Dependency graph недоступен или не включён.</p>'
            dependency_rows = ""
        updates = "Не удалось определить" if result.dependabot_update_count is None else str(result.dependabot_update_count)
        self.quality_page.dependencies.browser.setHtml(
            dependency_intro
            + f'<p><b>Открытые обновления Dependabot:</b> {h(updates)}</p>'
            + dependency_rows
        )

        if result.dependabot_status == "available":
            alerts_html = self._list(
                result.dependabot_alerts,
                lambda item: (
                    f'<a href="{h(item.get("html_url", ""))}"><b>{h(item.get("package", "Пакет"))}</b></a> '
                    f'<span style="color:{COLORS["danger"]};">{h(item.get("severity", "unknown"))}</span><br>'
                    f'{h(item.get("summary", ""))}<br>'
                    f'<span style="color:{COLORS["muted"]}; font-size:12px;">Исправление: '
                    f'{h(item.get("patched_version", "—"))}</span>'
                ),
            )
            security_intro = f'<p><b>Открытые известные уязвимости:</b> {h(len(result.dependabot_alerts))}</p>'
        elif result.dependabot_status == "permission_required":
            security_intro = f'<p style="color:{COLORS["warning"]};">Токену требуется разрешение Dependabot alerts: read.</p>'
            alerts_html = ""
        else:
            security_intro = f'<p style="color:{COLORS["muted"]};">Dependabot alerts недоступны или отключены.</p>'
            alerts_html = ""
        self.quality_page.security.browser.setHtml(
            f'<p><b>Файл конфигурации:</b> {state(result.dependabot_configured, "Найден", "Не найден")}</p>'
            + security_intro
            + alerts_html
        )
