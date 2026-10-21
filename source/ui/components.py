"""Reusable dashboard widgets for GitHub Repository Analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from PySide6.QtCore import (
    Property,
    QAbstractAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
    QRectF,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from utils.evaluation import (
    CRITERION_LIBRARY,
    EvaluationCriterion,
    EvaluationProfile,
    PRESET_PROFILES,
    criterion,
)

from ui.theme import (
    ANIMATIONS_ENABLED,
    COLORS,
    DOCUMENT_CSS,
    NAVIGATION_ANIMATION_MS,
    NAVIGATION_HOVER_MS,
    NAVIGATION_INDICATOR_MS,
    PAGE_TRANSITION_MS,
    health_accent,
)


PAGES = (
    ("⌂", "Обзор"),
    ("↗", "Активность"),
    ("◎", "Сообщество"),
    ("✓", "Качество проекта"),
    ("≡", "README"),
)


def search_icon() -> QIcon:
    """Create a small outline search icon without external assets."""
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(COLORS["muted"]), 1.7))
    painter.drawEllipse(QRectF(3.5, 3.5, 9.5, 9.5))
    painter.drawLine(11.5, 11.5, 16.5, 16.5)
    painter.end()
    return QIcon(pixmap)


def _mix_color(start: QColor, end: QColor, progress: float) -> QColor:
    """Return a stable RGB interpolation for lightweight button animation."""
    progress = max(0.0, min(1.0, progress))
    return QColor(
        round(start.red() + (end.red() - start.red()) * progress),
        round(start.green() + (end.green() - start.green()) * progress),
        round(start.blue() + (end.blue() - start.blue()) * progress),
    )


class NavigationButton(QPushButton):
    """Navigation button with an animated selected-state palette."""

    def __init__(self, icon_text: str, label: str, *, variant: str = "rail") -> None:
        super().__init__()
        self.variant = variant
        self.setObjectName("bottomNavButton" if variant == "bottom" else "navButton")
        self.icon_text = icon_text
        self.label = label
        self.count = 0
        self.collapsed = False
        self._animations_enabled = ANIMATIONS_ENABLED
        self._selection_progress = 0.0
        self._hover_progress = 0.0
        self._current_text_color = QColor(COLORS["muted"])
        self._selection_animation = QPropertyAnimation(self, b"selectionProgress", self)
        self._selection_animation.setDuration(NAVIGATION_ANIMATION_MS)
        self._selection_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_animation = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_animation.setDuration(NAVIGATION_HOVER_MS)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(label)
        self.setToolTip(label)
        self._refresh_text()
        self._apply_selection_style()

    def _get_selection_progress(self) -> float:
        return self._selection_progress

    def _set_selection_progress(self, value: float) -> None:
        self._selection_progress = max(0.0, min(1.0, float(value)))
        self._apply_selection_style()

    selectionProgress = Property(float, _get_selection_progress, _set_selection_progress)

    def _get_hover_progress(self) -> float:
        return self._hover_progress

    def _set_hover_progress(self, value: float) -> None:
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self._apply_selection_style()

    hoverProgress = Property(float, _get_hover_progress, _set_hover_progress)

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = bool(enabled)
        if not self._animations_enabled:
            self._selection_animation.stop()
            self._hover_animation.stop()
            self._set_selection_progress(1.0 if self.isChecked() else 0.0)
            self._set_hover_progress(0.0)

    def set_selected(self, selected: bool, *, animate: bool = True) -> None:
        self.setChecked(selected)
        target = 1.0 if selected else 0.0
        self._selection_animation.stop()
        if not animate or not self._animations_enabled:
            self._set_selection_progress(target)
            return
        self._selection_animation.setStartValue(self._selection_progress)
        self._selection_animation.setEndValue(target)
        self._selection_animation.start()

    def _apply_selection_style(self) -> None:
        progress = self._selection_progress
        hover_text = _mix_color(
            QColor(COLORS["muted"]), QColor(COLORS["nav_hover"]), self._hover_progress,
        )
        text = _mix_color(hover_text, QColor(COLORS["blue"]), progress)
        self._current_text_color = text
        if self.variant == "bottom":
            self.setStyleSheet(
                "QPushButton {"
                "min-height:52px; padding:4px; border:1px solid transparent; border-radius:6px; font-size:12px;"
                f"color:{text.name()}; background:transparent;"
                "}"
                f"QPushButton:focus {{ border-color:{COLORS['border_hover']}; }}"
            )
            return
        padding = round(12 + 3 * progress)
        self.setStyleSheet(
            "QPushButton {"
            f"min-height:42px; padding:0 {padding}px; text-align:left; color:{text.name()};"
            "background:transparent; border:1px solid transparent; border-radius:8px;"
            "}"
            f"QPushButton:focus {{ border-color:{COLORS['border_hover']}; }}"
        )

    def _animate_hover(self, hovered: bool) -> None:
        target = 1.0 if hovered and not self.isChecked() else 0.0
        self._hover_animation.stop()
        if not self._animations_enabled:
            self._set_hover_progress(target)
            return
        self._hover_animation.setStartValue(self._hover_progress)
        self._hover_animation.setEndValue(target)
        self._hover_animation.start()

    def enterEvent(self, event) -> None:
        self._animate_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate_hover(False)
        super().leaveEvent(event)

    def set_count(self, count: int) -> None:
        self.count = max(0, count)
        self._refresh_text()

    def set_collapsed(self, collapsed: bool) -> None:
        self.collapsed = collapsed
        self._refresh_text()

    def _refresh_text(self) -> None:
        if self.variant == "bottom":
            self.setText(f"{self.icon_text}\n{self.label}")
            return
        if self.collapsed:
            self.setText(self.icon_text)
        else:
            badge = f"   {self.count}" if self.count else ""
            self.setText(f"{self.icon_text}   {self.label}{badge}")


class AnimatedSelectionIndicator(QFrame):
    """One reusable rounded selection background that moves between buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navSelectionIndicator")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._animations_enabled = ANIMATIONS_ENABLED
        self._target_geometry = QRect()
        self.last_start_geometry = QRect()
        self._animation = QPropertyAnimation(self, b"geometry", self)
        self._animation.setDuration(NAVIGATION_INDICATOR_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.finished.connect(self._finish_at_target)
        self.hide()

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = bool(enabled)
        if not self._animations_enabled and self._animation.state() == QAbstractAnimation.State.Running:
            self._animation.stop()
            self.setGeometry(self._target_geometry)

    def move_to(self, target: QRect, *, animate: bool) -> None:
        self._target_geometry = QRect(target)
        self._animation.stop()
        if (
            not self.isVisible()
            or not animate
            or not self._animations_enabled
            or self.geometry() == target
        ):
            self.setGeometry(target)
            self.show()
            self.last_start_geometry = QRect(target)
            return
        self.last_start_geometry = QRect(self.geometry())
        self._animation.setStartValue(self.last_start_geometry)
        self._animation.setEndValue(target)
        self._animation.start()

    def _finish_at_target(self) -> None:
        self.setGeometry(self._target_geometry)


class _AnimatedNavigation:
    """Shared active-indicator behavior for rail and bottom navigation."""

    _indicator_is_bottom: bool
    buttons: list[NavigationButton]

    def _init_indicator(self, *, bottom: bool) -> None:
        self._indicator_is_bottom = bottom
        self._animations_enabled = ANIMATIONS_ENABLED
        self._current_index = -1
        self.indicator = AnimatedSelectionIndicator(self)
        self._stack_indicator_behind_buttons()

    def _indicator_geometry(self, index: int) -> QRect:
        button = self.buttons[index]
        geometry = button.geometry()
        return QRect(geometry)

    def _stack_indicator_behind_buttons(self) -> None:
        self.indicator.lower()
        for button in self.buttons:
            button.raise_()

    def _move_indicator(self, index: int, *, animate: bool) -> None:
        if not (0 <= index < len(self.buttons)):
            return
        target = self._indicator_geometry(index)
        self.indicator.move_to(target, animate=animate and self._animations_enabled)
        self._stack_indicator_behind_buttons()

    def set_current(self, index: int, *, animate: bool = True) -> None:
        if not (0 <= index < len(self.buttons)):
            return
        changed = index != self._current_index
        should_animate = animate and changed and self._animations_enabled
        for position, button in enumerate(self.buttons):
            button.set_selected(position == index, animate=should_animate)
        self._current_index = index
        self._move_indicator(index, animate=should_animate)

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = bool(enabled)
        self.indicator.set_animations_enabled(enabled)
        for button in self.buttons:
            button.set_animations_enabled(enabled)
        self.sync_indicator()

    def sync_indicator(self) -> None:
        if self._current_index >= 0:
            self._move_indicator(self._current_index, animate=False)


class NavigationRail(_AnimatedNavigation, QFrame):
    page_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("navigationRail")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(8)

        self.brand = QWidget()
        brand_layout = QHBoxLayout(self.brand)
        brand_layout.setContentsMargins(4, 0, 4, 16)
        brand_layout.setSpacing(10)
        mark = QLabel("R")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brand_text = QWidget()
        text_layout = QVBoxLayout(self.brand_text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        title = QLabel("RepoScope")
        title.setObjectName("brandTitle")
        caption = QLabel("GitHub Analyzer")
        caption.setObjectName("brandCaption")
        text_layout.addWidget(title)
        text_layout.addWidget(caption)
        brand_layout.addWidget(mark)
        brand_layout.addWidget(self.brand_text, 1)
        layout.addWidget(self.brand)

        section = QLabel("НАВИГАЦИЯ")
        section.setObjectName("railSection")
        self.section_label = section
        layout.addWidget(section)
        self.buttons: list[NavigationButton] = []
        for index, (icon, label) in enumerate(PAGES):
            button = NavigationButton(icon, label)
            button.clicked.connect(lambda checked=False, page=index: self.page_requested.emit(page))
            layout.addWidget(button)
            self.buttons.append(button)
        layout.addStretch(1)
        version = QLabel("Локальный анализатор")
        version.setObjectName("railFooter")
        self.footer = version
        layout.addWidget(version)
        self._init_indicator(bottom=False)
        self.set_collapsed(False)
        self.set_current(0, animate=False)

    def set_counts(self, activity: int, community: int) -> None:
        self.buttons[1].set_count(activity)
        self.buttons[2].set_count(community)

    def set_collapsed(self, collapsed: bool) -> None:
        self.setFixedWidth(76 if collapsed else 224)
        self.brand_text.setVisible(not collapsed)
        self.section_label.setVisible(not collapsed)
        self.footer.setVisible(not collapsed)
        for button in self.buttons:
            button.set_collapsed(collapsed)
        QTimer.singleShot(0, self.sync_indicator)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self.sync_indicator)


class BottomNavigation(_AnimatedNavigation, QFrame):
    page_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("bottomNavigation")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        self.buttons: list[NavigationButton] = []
        for index, (icon, label) in enumerate(PAGES):
            button = NavigationButton(icon, label, variant="bottom")
            button.clicked.connect(lambda checked=False, page=index: self.page_requested.emit(page))
            layout.addWidget(button, 1)
            self.buttons.append(button)
        self._init_indicator(bottom=True)
        self.set_current(0, animate=False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self.sync_indicator)


class AnimatedStackedWidget(QStackedWidget):
    """A QStackedWidget with cancellable directional slide/fade transitions."""

    transition_started = Signal(int, int, int)
    transition_finished = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        animations_enabled: bool = ANIMATIONS_ENABLED,
        duration: int = PAGE_TRANSITION_MS,
    ) -> None:
        super().__init__(parent)
        self._animations_enabled = animations_enabled
        self._duration = max(0, duration)
        self._animation_group: QParallelAnimationGroup | None = None
        self._effects: dict[QWidget, QGraphicsOpacityEffect] = {}
        self._outgoing: QWidget | None = None
        self._incoming: QWidget | None = None
        self._focus_was_in_outgoing = False
        self.last_direction = 0
        self.transition_count = 0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def addWidget(self, widget: QWidget) -> int:
        index = super().addWidget(widget)
        self._ensure_effect(widget)
        return index

    def insertWidget(self, index: int, widget: QWidget) -> int:
        inserted = super().insertWidget(index, widget)
        self._ensure_effect(widget)
        return inserted

    def removeWidget(self, widget: QWidget) -> None:
        if widget in {self._outgoing, self._incoming}:
            self._complete_active_transition()
        self._effects.pop(widget, None)
        super().removeWidget(widget)

    def _ensure_effect(self, widget: QWidget) -> QGraphicsOpacityEffect:
        effect = self._effects.get(widget)
        if effect is None:
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(1.0)
            widget.setGraphicsEffect(effect)
            self._effects[widget] = effect
        return effect

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = bool(enabled)
        if not self._animations_enabled:
            self._complete_active_transition()

    def animations_enabled(self) -> bool:
        return self._animations_enabled

    def is_animating(self) -> bool:
        return bool(
            self._animation_group
            and self._animation_group.state() == QAbstractAnimation.State.Running
        )

    def setCurrentIndexAnimated(self, index: int) -> bool:
        """Switch to index and return whether a visual transition was started."""
        if not (0 <= index < self.count()):
            return False
        if index == self.currentIndex():
            return False
        if self.is_animating():
            self._complete_active_transition()
        old_index = self.currentIndex()
        if not self._animations_enabled or self._duration == 0 or not self.isVisible():
            super().setCurrentIndex(index)
            self.last_direction = 1 if index > old_index else -1
            return False
        self._start_transition(old_index, index)
        return True

    def _start_transition(self, old_index: int, new_index: int) -> None:
        outgoing = self.widget(old_index)
        incoming = self.widget(new_index)
        if outgoing is None or incoming is None:
            super().setCurrentIndex(new_index)
            return
        direction = 1 if new_index > old_index else -1
        self.last_direction = direction
        self.transition_count += 1
        self.transition_started.emit(old_index, new_index, direction)
        self._outgoing = outgoing
        self._incoming = incoming
        focused = outgoing.focusWidget()
        self._focus_was_in_outgoing = focused is not None
        if self._focus_was_in_outgoing:
            self.setFocus(Qt.FocusReason.OtherFocusReason)

        base = self.contentsRect()
        distance = max(18, min(46, round(base.width() * 0.035)))
        outgoing_end = base.translated(-direction * distance, 0)
        incoming_start = base.translated(direction * distance, 0)
        outgoing_effect = self._ensure_effect(outgoing)
        incoming_effect = self._ensure_effect(incoming)

        super().setCurrentIndex(new_index)
        outgoing.setGeometry(base)
        incoming.setGeometry(incoming_start)
        outgoing_effect.setOpacity(1.0)
        incoming_effect.setOpacity(0.0)
        outgoing.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        incoming.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        outgoing.show()
        incoming.show()
        incoming.raise_()

        group = QParallelAnimationGroup(self)
        for target, property_name, start, end in (
            (outgoing, b"geometry", base, outgoing_end),
            (incoming, b"geometry", incoming_start, base),
            (outgoing_effect, b"opacity", 1.0, 0.0),
            (incoming_effect, b"opacity", 0.0, 1.0),
        ):
            animation = QPropertyAnimation(target, property_name, group)
            animation.setDuration(self._duration)
            animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
            animation.setStartValue(start)
            animation.setEndValue(end)
            group.addAnimation(animation)
        group.finished.connect(lambda active=group: self._transition_complete(active))
        self._animation_group = group
        group.start()

    def _transition_complete(self, group: QParallelAnimationGroup) -> None:
        if group is not self._animation_group:
            return
        self._finish_transition_state()

    def _complete_active_transition(self) -> None:
        group = self._animation_group
        if group is None:
            return
        group.stop()
        self._finish_transition_state()

    def _finish_transition_state(self) -> None:
        group = self._animation_group
        outgoing = self._outgoing
        incoming = self._incoming
        self._animation_group = None
        self._outgoing = None
        self._incoming = None
        base = self.contentsRect()
        if outgoing is not None:
            self._ensure_effect(outgoing).setOpacity(1.0)
            outgoing.setGeometry(base)
            outgoing.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            outgoing.hide()
        if incoming is not None:
            self._ensure_effect(incoming).setOpacity(1.0)
            incoming.setGeometry(base)
            incoming.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            incoming.show()
            incoming.raise_()
            if self._focus_was_in_outgoing:
                self.setFocus(Qt.FocusReason.OtherFocusReason)
            self.transition_finished.emit(self.indexOf(incoming))
        self._focus_was_in_outgoing = False
        if group is not None:
            group.deleteLater()

    def resizeEvent(self, event) -> None:
        if self.is_animating():
            self._complete_active_transition()
        super().resizeEvent(event)


class TopBar(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("topBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        self.repository_input = QLineEdit()
        self.repository_input.setPlaceholderText("owner/repository или ссылка GitHub")
        self.repository_input.setClearButtonEnabled(True)
        self.repository_input.addAction(search_icon(), QLineEdit.ActionPosition.LeadingPosition)
        self.repository_input.setAccessibleName("Репозиторий или профиль GitHub")
        self.repository_input.setToolTip("Введите owner/repository, ссылку на репозиторий или профиль GitHub · Ctrl+K")
        self.action_stack = QStackedWidget()
        self.action_stack.setObjectName("actionStack")
        self.action_stack.setFixedWidth(142)
        self.action_stack.setFixedHeight(44)
        self.analyze_button = QPushButton("Анализировать")
        self.analyze_button.setObjectName("primaryButton")
        self.cancel_button = QPushButton("Отменить")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setEnabled(False)
        self.criteria_button = QPushButton("Критерии")
        self.criteria_button.setObjectName("secondaryButton")
        self.criteria_button.setToolTip("Выбрать профиль, пороги и веса оценки")
        self.action_stack.addWidget(self.analyze_button)
        self.action_stack.addWidget(self.cancel_button)
        layout.addWidget(self.repository_input, 1)
        layout.addWidget(self.criteria_button)
        layout.addWidget(self.action_stack)

    def set_busy(self, busy: bool) -> None:
        self.repository_input.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy)
        self.criteria_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.action_stack.setCurrentWidget(self.cancel_button if busy else self.analyze_button)


class RepositoryHeader(QFrame):
    open_requested = Signal()
    refresh_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("repositoryHeader")
        self.header_layout = QGridLayout(self)
        self.header_layout.setContentsMargins(20, 18, 20, 18)
        self.header_layout.setHorizontalSpacing(16)
        self.header_layout.setVerticalSpacing(6)
        self.eyebrow = QLabel("PUBLIC REPOSITORY  •  АНАЛИЗ ЗАВЕРШЁН")
        self.eyebrow.setObjectName("repositoryEyebrow")
        self.title = QLabel()
        self.title.setObjectName("repositoryTitle")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.description = QLabel()
        self.description.setObjectName("repositoryDescription")
        self.description.setTextFormat(Qt.TextFormat.PlainText)
        self.description.setWordWrap(True)
        self.open_button = QPushButton("Открыть на GitHub  ↗")
        self.open_button.setObjectName("secondaryButton")
        self.refresh_button = QPushButton("↻")
        self.refresh_button.setObjectName("iconButton")
        self.refresh_button.setToolTip("Повторить анализ")
        self.open_button.clicked.connect(self.open_requested)
        self.refresh_button.clicked.connect(self.refresh_requested)
        self.actions_widget = QWidget()
        actions = QHBoxLayout(self.actions_widget)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self.open_button)
        actions.addWidget(self.refresh_button)
        self.header_layout.addWidget(self.eyebrow, 0, 0)
        self.header_layout.addWidget(self.actions_widget, 0, 1, 2, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.header_layout.addWidget(self.title, 1, 0)
        self.header_layout.addWidget(self.description, 2, 0, 1, 2)
        self.header_layout.setColumnStretch(0, 1)

    def set_repository(self, full_name: str, description: str) -> None:
        self.title.setText(full_name)
        self.description.setText(description)

    def set_compact(self, compact: bool) -> None:
        if compact:
            self.header_layout.addWidget(self.eyebrow, 0, 0, 1, 2)
            self.header_layout.addWidget(self.title, 1, 0, 1, 2)
            self.header_layout.addWidget(self.description, 2, 0, 1, 2)
            self.header_layout.addWidget(self.actions_widget, 3, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
        else:
            self.header_layout.addWidget(self.eyebrow, 0, 0)
            self.header_layout.addWidget(self.title, 1, 0)
            self.header_layout.addWidget(self.actions_widget, 0, 1, 2, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            self.header_layout.addWidget(self.description, 2, 0, 1, 2)


class ScoreRing(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.score = 0
        self.color = COLORS["danger"]
        self.setFixedSize(128, 128)

    def set_score(self, score: int) -> None:
        self.score = max(0, min(100, score))
        self.color = health_accent(self.score)[1]
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(12, 12, self.width() - 24, self.height() - 24)
        painter.setPen(QPen(QColor(COLORS["surface_nested"]), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 0, 360 * 16)
        painter.setPen(QPen(QColor(self.color), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 90 * 16, -int(360 * 16 * self.score / 100))
        painter.setPen(QColor(COLORS["text"]))
        font = QFont("Segoe UI Variable")
        font.setPixelSize(29)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self.score))
        painter.end()


class HealthScoreCard(QFrame):
    details_requested = Signal()
    settings_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("healthCard")
        self.setMinimumHeight(168)
        self._interactive = False
        self.setProperty("interactive", False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(18)
        self.ring = ScoreRing()
        # Kept as a non-visual accessibility/testing value source.
        self.value_label = QLabel("0 / 100", self)
        self.value_label.hide()
        labels = QVBoxLayout()
        labels.setSpacing(6)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel("Оценка по вашим критериям")
        title.setObjectName("metricTitle")
        self.profile_label = QLabel("Open Source")
        self.profile_label.setObjectName("profileBadge")
        self.settings_button = QPushButton("Настроить")
        self.settings_button.setObjectName("linkButton")
        self.settings_button.setToolTip("Изменить критерии, пороги и веса")
        self.settings_button.clicked.connect(self.settings_requested)
        title_row.addWidget(title)
        title_row.addWidget(self.profile_label)
        title_row.addStretch(1)
        title_row.addWidget(self.settings_button)
        self.rating = QLabel("Оценка недоступна")
        self.rating.setObjectName("healthRating")
        self.explanation = QLabel("Ваши требования, пороги и веса")
        self.explanation.setObjectName("mutedLabel")
        self.explanation.setWordWrap(True)
        self.interaction_hint = QLabel("↗  Нажмите, чтобы посмотреть подробности")
        self.interaction_hint.setObjectName("healthHint")
        self.interaction_hint.hide()
        labels.addStretch(1)
        labels.addLayout(title_row)
        labels.addWidget(self.rating)
        labels.addWidget(self.explanation)
        labels.addWidget(self.interaction_hint)
        labels.addStretch(1)
        layout.addWidget(self.ring)
        layout.addLayout(labels, 1)
        for child in (self.ring, title, self.rating, self.explanation, self.interaction_hint):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_profile(self, profile_name: str) -> None:
        self.profile_label.setText(profile_name)

    def set_score(self, score: int) -> None:
        self.ring.set_score(score)
        self.value_label.setText(f"{score} / 100")
        self.value_label.setProperty("accent", health_accent(score)[0])
        if score >= 75:
            rating = "Отличное состояние"
        elif score >= 40:
            rating = "Требует внимания"
        else:
            rating = "Низкий показатель"
        self.rating.setText(rating)
        self.rating.setStyleSheet(f"color: {health_accent(score)[1]};")

    def set_interactive(self, interactive: bool) -> None:
        self._interactive = interactive
        self.setProperty("interactive", interactive)
        self.setCursor(Qt.CursorShape.PointingHandCursor if interactive else Qt.CursorShape.ArrowCursor)
        self.interaction_hint.setVisible(interactive)
        self.setToolTip("Нажмите, чтобы посмотреть подробности" if interactive else "")
        self.style().unpolish(self)
        self.style().polish(self)

    def is_interactive(self) -> bool:
        return self._interactive

    def mouseReleaseEvent(self, event) -> None:
        if self._interactive and event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.details_requested.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if self._interactive and event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.details_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_value(self, value: str, accent: str = "") -> None:
        """Compatibility with the former metric-card API."""
        try:
            score = int(value.split()[0])
        except (ValueError, IndexError):
            score = 0
        self.set_score(score)


class HealthDetailsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("healthDetailsDialog")
        self.setWindowTitle("Расшифровка Health Score")
        self.setModal(False)
        self.setMinimumSize(460, 380)
        self.resize(700, 640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        self.heading = QLabel("Расшифровка Health Score")
        self.heading.setObjectName("dialogTitle")
        self.score_label = QLabel()
        self.score_label.setObjectName("dialogScore")
        self.browser = QTextBrowser()
        self.browser.setObjectName("healthDetailsBrowser")
        self.browser.document().setDefaultStyleSheet(DOCUMENT_CSS)
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.heading)
        layout.addWidget(self.score_label)
        layout.addWidget(self.browser, 1)
        layout.addWidget(self.buttons)

    def set_report(self, score: int, categories: list[dict], profile_name: str = "") -> None:
        color = health_accent(score)[1]
        profile_suffix = f" · {profile_name}" if profile_name else ""
        self.score_label.setText(f"Итоговая оценка: {score} из 100{profile_suffix}")
        self.score_label.setStyleSheet(f"color: {color};")
        sections: list[str] = []
        for category in categories:
            title = escape(str(category.get("title", "Категория")))
            points = escape(str(category.get("points", 0)))
            maximum = escape(str(category.get("maximum", 0)))
            explanation = escape(str(category.get("explanation", "Нет пояснения.")))
            recommendation = escape(str(category.get("recommendation", "Нет рекомендаций.")))
            available = bool(category.get("available", True))
            result_text = f"{points} из {maximum}" if available else "не учитывается"
            sections.append(
                '<div style="margin-bottom:18px;">'
                f'<h3>{title} — {result_text}</h3>'
                f'<p>{explanation}</p>'
                f'<p><b>Рекомендация:</b> {recommendation}</p>'
                '</div>'
            )
        self.browser.setHtml("".join(sections))
        self.browser.verticalScrollBar().setValue(0)


class EvaluationSettingsDialog(QDialog):
    """Edit a preset's thresholds and weights without exposing formula syntax."""

    profile_applied = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("evaluationSettingsDialog")
        self.setWindowTitle("Критерии оценки")
        self.setModal(False)
        self.setMinimumSize(660, 520)
        self.resize(790, 680)
        self._controls: dict[str, tuple[QCheckBox, QSpinBox, QSpinBox, EvaluationCriterion]] = {}
        self._current_profile = PRESET_PROFILES["open_source"]

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)
        heading = QLabel("Настройте оценку под свою задачу")
        heading.setObjectName("dialogTitle")
        intro = QLabel(
            "Выберите готовый профиль или измените требования. Итог всегда приводится к шкале 0–100."
        )
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(intro)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Профиль:"))
        self.profile_combo = QComboBox()
        for key, profile in PRESET_PROFILES.items():
            self.profile_combo.addItem(profile.name, key)
        self.profile_combo.currentIndexChanged.connect(self._load_selected_profile)
        preset_row.addWidget(self.profile_combo, 1)
        root.addLayout(preset_row)
        self.description = QLabel()
        self.description.setObjectName("mutedLabel")
        self.description.setWordWrap(True)
        root.addWidget(self.description)

        self.criteria_scroll = QScrollArea()
        self.criteria_scroll.setWidgetResizable(True)
        self.criteria_scroll.setObjectName("criteriaScroll")
        self.criteria_host = QWidget()
        self.criteria_grid = QGridLayout(self.criteria_host)
        self.criteria_grid.setContentsMargins(4, 4, 8, 4)
        self.criteria_grid.setHorizontalSpacing(12)
        self.criteria_grid.setVerticalSpacing(9)
        self.criteria_scroll.setWidget(self.criteria_host)
        root.addWidget(self.criteria_scroll, 1)

        self.total_label = QLabel()
        self.total_label.setObjectName("weightTotal")
        root.addWidget(self.total_label)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setText("Применить оценку")
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setObjectName("primaryButton")
        self.buttons.clicked.connect(self._handle_button)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self._render_profile(self._current_profile)

    def set_profile(self, profile: EvaluationProfile) -> None:
        self._current_profile = profile
        preset_key = profile.key if profile.key in PRESET_PROFILES else None
        if preset_key:
            index = self.profile_combo.findData(preset_key)
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentIndex(index)
            self.profile_combo.blockSignals(False)
        self._render_profile(profile)

    def _clear_grid(self) -> None:
        while self.criteria_grid.count():
            item = self.criteria_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._controls.clear()

    def _load_selected_profile(self) -> None:
        key = self.profile_combo.currentData()
        self._current_profile = PRESET_PROFILES[str(key)]
        self._render_profile(self._current_profile)

    def _render_profile(self, profile: EvaluationProfile) -> None:
        self._clear_grid()
        self.description.setText(profile.description)
        for column, text in enumerate(("Критерий", "Требование", "Порог", "Вес")):
            label = QLabel(text)
            label.setObjectName("tableHeader")
            self.criteria_grid.addWidget(label, 0, column)
        existing = {item.key: item for item in profile.criteria}
        expanded = tuple(
            existing.get(key, criterion(key, 0, enabled=False))
            for key in CRITERION_LIBRARY
        )
        for row, item in enumerate(expanded, start=1):
            enabled = QCheckBox(item.title)
            enabled.setChecked(item.enabled)
            condition = QLabel({
                "min": "не менее", "max": "не более", "max_zero": "не более", "bool": "обязательно",
            }[item.comparison])
            condition.setObjectName("mutedLabel")
            target = QSpinBox(self.criteria_host)
            target.setRange(0, 10000)
            target.setValue(round(item.target))
            target.setSuffix(f" {item.unit}" if item.unit else "")
            target.setEnabled(item.comparison != "bool")
            weight = QSpinBox()
            weight.setRange(0, 100)
            weight.setValue(item.weight)
            weight.setSuffix(" %")
            enabled.toggled.connect(self._update_total)
            weight.valueChanged.connect(self._update_total)
            self.criteria_grid.addWidget(enabled, row, 0)
            self.criteria_grid.addWidget(condition, row, 1)
            if item.comparison == "bool":
                target.hide()
                placeholder = QLabel("—")
                placeholder.setObjectName("mutedLabel")
                self.criteria_grid.addWidget(placeholder, row, 2)
            else:
                self.criteria_grid.addWidget(target, row, 2)
            self.criteria_grid.addWidget(weight, row, 3)
            self._controls[item.key] = (enabled, target, weight, item)
        self.criteria_grid.setColumnStretch(0, 2)
        self.criteria_grid.setColumnStretch(1, 1)
        self.criteria_grid.setColumnStretch(2, 1)
        self.criteria_grid.setColumnStretch(3, 1)
        self._update_total()

    def _update_total(self) -> None:
        total = sum(weight.value() for enabled, _target, weight, _item in self._controls.values() if enabled.isChecked())
        note = "Итоговые веса будут автоматически приведены к 100%." if total != 100 else "Профиль сбалансирован."
        self.total_label.setText(f"Сумма активных весов: {total}% · {note}")
        self.total_label.setProperty("balanced", total == 100)
        self.total_label.style().unpolish(self.total_label)
        self.total_label.style().polish(self.total_label)

    def _build_profile(self) -> EvaluationProfile:
        base_key = str(self.profile_combo.currentData())
        base = PRESET_PROFILES[base_key]
        criteria = tuple(
            EvaluationCriterion(
                key=item.key, title=item.title, metric=item.metric, comparison=item.comparison,
                target=target.value(), weight=weight.value(), unit=item.unit, enabled=enabled.isChecked(),
            )
            for enabled, target, weight, item in self._controls.values()
        )
        base_by_key = {item.key: item for item in base.criteria}
        expanded_base = tuple(
            base_by_key.get(key, criterion(key, 0, enabled=False))
            for key in CRITERION_LIBRARY
        )
        if criteria == expanded_base:
            return base
        return EvaluationProfile("custom", f"{base.name} · свой", "Пользовательские критерии и веса.", criteria)

    def _handle_button(self, button: QPushButton) -> None:
        if self.buttons.standardButton(button) == QDialogButtonBox.StandardButton.Apply:
            profile = self._build_profile()
            if not any(item.enabled and item.weight > 0 for item in profile.criteria):
                self.total_label.setText("Включите хотя бы один критерий с ненулевым весом.")
                self.total_label.setProperty("balanced", False)
                return
            self._current_profile = profile
            self.profile_applied.emit(profile)


class MetricCard(QFrame):
    def __init__(self, title: str, *, technical: bool = False, accent: str = "") -> None:
        super().__init__()
        self.setObjectName("metricCard")
        self.setMinimumHeight(112)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("metricTitle")
        self.value_label = QLabel("—")
        self.value_label.setObjectName("metricValue")
        self.value_label.setProperty("technical", technical)
        self.value_label.setTextFormat(Qt.TextFormat.PlainText)
        self.value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.accent = accent
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        layout.addWidget(self.value_label)

    def set_value(self, value: str, accent: str | None = None) -> None:
        self.value_label.setText(value)
        self.value_label.setProperty("accent", self.accent if accent is None else accent)
        self.value_label.style().unpolish(self.value_label)
        self.value_label.style().polish(self.value_label)


@dataclass(frozen=True)
class LanguagePart:
    name: str
    percent: float
    color: str


class LanguageBar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[LanguagePart] = []
        self.setFixedHeight(12)

    def set_parts(self, parts: list[LanguagePart]) -> None:
        self.parts = parts
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 1, self.width(), 10), 5, 5)
        painter.setClipPath(path)
        painter.fillRect(self.rect(), QColor(COLORS["surface_nested"]))
        x = 0.0
        for part in self.parts:
            width = self.width() * part.percent / 100
            painter.fillRect(QRectF(x, 1, width + 1, 10), QColor(part.color))
            x += width
        painter.end()


class LanguageDistribution(QFrame):
    PALETTE = (COLORS["blue"], COLORS["purple"], COLORS["success"], COLORS["warning"], "#DB61A2", "#56D4DD")

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("contentCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        title = QLabel("Языки проекта")
        title.setObjectName("sectionTitle")
        self.bar = LanguageBar()
        self.legend = QWidget()
        self.legend_layout = QGridLayout(self.legend)
        self.legend_layout.setContentsMargins(0, 0, 0, 0)
        self.legend_layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(self.bar)
        layout.addWidget(self.legend)

    def set_languages(self, languages: dict[str, int]) -> None:
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        total = sum(languages.values())
        ordered = sorted(languages.items(), key=lambda item: item[1], reverse=True)
        visible = ordered[:7]
        if len(ordered) > 7:
            visible.append(("Другие", sum(value for _, value in ordered[7:])))
        parts: list[LanguagePart] = []
        for index, (name, size) in enumerate(visible):
            percent = size / total * 100 if total else 0
            color = self.PALETTE[index % len(self.PALETTE)]
            parts.append(LanguagePart(name, percent, color))
            item = QLabel(f'<span style="color:{color}">●</span> {escape(name)}  <b>{percent:.1f}%</b>')
            item.setTextFormat(Qt.TextFormat.RichText)
            self.legend_layout.addWidget(item, index // 3, index % 3)
        self.bar.set_parts(parts)


class OverviewPage(QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 4, 4)
        self.content_layout.setSpacing(14)
        self.summary = QTextBrowser()
        self.summary.setObjectName("overviewSummary")
        self.summary.setMinimumHeight(220)
        self.summary.document().setDefaultStyleSheet(DOCUMENT_CSS)
        self.languages = LanguageDistribution()
        self.content_layout.addWidget(self.summary, 1)
        self.content_layout.addWidget(self.languages)
        self.setWidget(content)


class ReportSectionCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("contentCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        self.browser = QTextBrowser()
        self.browser.setObjectName("qualityBrowser")
        self.browser.document().setDefaultStyleSheet(DOCUMENT_CSS)
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        layout.addWidget(heading)
        layout.addWidget(self.browser, 1)


class QualityPage(QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 4, 4)
        self.grid.setSpacing(12)
        self.standards = ReportSectionCard("Файлы и настройки")
        self.activity = ReportSectionCard("Метрики активности")
        self.dependencies = ReportSectionCard("Зависимости и обновления")
        self.security = ReportSectionCard("Dependabot и безопасность")
        self.cards = [self.standards, self.activity, self.dependencies, self.security]
        self._columns = 0
        self.set_compact(False)
        self.setWidget(self.content)

    def set_compact(self, compact: bool) -> None:
        columns = 1 if compact else 2
        if columns == self._columns:
            return
        for card in self.cards:
            self.grid.removeWidget(card)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
        for column in range(2):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        self._columns = columns


class ListSectionCard(QFrame):
    def __init__(self, title: str, empty_text: str, button_text: str) -> None:
        super().__init__()
        self.setObjectName("listCard")
        self.base_title = title
        self.empty_text = empty_text
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("sectionTitle")
        self.browser = QTextBrowser()
        self.browser.setObjectName("listBrowser")
        self.browser.document().setDefaultStyleSheet(DOCUMENT_CSS)
        self.more_button = QPushButton(button_text)
        self.more_button.setObjectName("loadMoreButton")
        self.more_button.hide()
        layout.addWidget(self.title_label)
        layout.addWidget(self.browser, 1)
        layout.addWidget(self.more_button, 0, Qt.AlignmentFlag.AlignLeft)

    def set_count(self, count: int) -> None:
        self.title_label.setText(f"{self.base_title}  ·  {count}")


class DualSectionPage(QWidget):
    def __init__(self, first: ListSectionCard, second: ListSectionCard) -> None:
        super().__init__()
        self.first = first
        self.second = second
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("contentSplitter")
        self.splitter.addWidget(first)
        self.splitter.addWidget(second)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

    def set_compact(self, compact: bool) -> None:
        self.splitter.setOrientation(Qt.Orientation.Vertical if compact else Qt.Orientation.Horizontal)
        self.splitter.setSizes([1, 1])
