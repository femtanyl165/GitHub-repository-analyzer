"""RepoScope GitHub Dark × Fluent theme and Markdown styling."""

from PySide6.QtGui import (
    QColor,
    QFont,
    QPalette,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextFrameFormat,
    QTextTable,
)
from PySide6.QtWidgets import QApplication


COLORS = {
    "background": "#080C12",
    "panel": "#0E141D",
    "surface": "#141B25",
    "surface_nested": "#19222E",
    "border": "#253141",
    "border_hover": "#3B4B60",
    "text": "#F3F6FB",
    "muted": "#94A3B8",
    "blue": "#4F8CFF",
    "blue_hover": "#3978EA",
    "nav_hover": "#B8CCFF",
    "nav_indicator": "#13233B",
    "nav_indicator_border": "#203B64",
    "success": "#43C66E",
    "warning": "#F2B84B",
    "danger": "#F25F5C",
    "purple": "#A371F7",
}

# A single switch disables every decorative navigation animation. Page changes
# and responsive navigation remain fully functional when it is False.
ANIMATIONS_ENABLED = True
NAVIGATION_ANIMATION_MS = 220
NAVIGATION_INDICATOR_MS = 320
NAVIGATION_HOVER_MS = 150
PAGE_TRANSITION_MS = 280


APP_STYLESHEET = f"""
QMainWindow, QDialog {{ background: {COLORS['background']}; color: {COLORS['text']}; }}
QWidget {{
    color: {COLORS['text']};
    font-family: "Segoe UI Variable", "Segoe UI", "Arial";
    font-size: 14px;
}}
QWidget#appRoot, QWidget#workspace, QStackedWidget#pageStack {{ background: {COLORS['background']}; }}
QFrame#navigationRail {{ background: {COLORS['panel']}; border-right: 1px solid {COLORS['border']}; }}
QLabel#brandMark {{
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
    color: white; background: {COLORS['blue']}; border-radius: 8px;
    font-family: "Cascadia Code", "Consolas"; font-size: 18px; font-weight: 700;
}}
QLabel#brandTitle {{ font-size: 16px; font-weight: 700; }}
QLabel#brandCaption, QLabel#railFooter, QLabel#mutedLabel {{ color: {COLORS['muted']}; font-size: 12px; }}
QLabel#railSection, QLabel#repositoryEyebrow {{ color: {COLORS['muted']}; font-size: 11px; font-weight: 600; }}
QPushButton#navButton {{
    min-height: 42px; padding: 0 12px; text-align: left;
    color: {COLORS['muted']}; background: transparent; border: 1px solid transparent; border-radius: 8px;
}}
QFrame#bottomNavigation {{ background: {COLORS['panel']}; border-top: 1px solid {COLORS['border']}; }}
QFrame#navSelectionIndicator {{
    background: {COLORS['nav_indicator']};
    border: 1px solid {COLORS['nav_indicator_border']};
    border-radius: 8px;
}}
QPushButton#bottomNavButton {{
    min-height: 52px; padding: 4px; color: {COLORS['muted']}; background: transparent;
    border: none; border-top: 2px solid transparent; border-radius: 0; font-size: 12px;
}}
QFrame#topBar, QFrame#repositoryHeader, QFrame#healthCard, QFrame#metricCard,
QFrame#contentCard, QFrame#listCard {{
    background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 10px;
}}
QFrame#healthCard[interactive="true"]:hover {{ background: #182231; border-color: {COLORS['blue']}; }}
QFrame#healthCard[interactive="true"]:focus {{ border-color: {COLORS['blue']}; }}
QLineEdit {{
    min-height: 42px; padding: 0 12px; color: {COLORS['text']};
    background: {COLORS['surface_nested']}; border: 1px solid {COLORS['border']}; border-radius: 8px;
    selection-background-color: {COLORS['blue']};
}}
QLineEdit:hover {{ border-color: {COLORS['border_hover']}; }}
QLineEdit:focus {{ border-color: {COLORS['blue']}; }}
QLineEdit:disabled {{ color: #66758A; background: #101722; }}
QPushButton {{
    min-height: 40px; padding: 0 15px; font-weight: 500;
    background: {COLORS['surface_nested']}; border: 1px solid {COLORS['border']}; border-radius: 8px;
}}
QPushButton:hover {{ background: #202C3A; border-color: {COLORS['border_hover']}; }}
QPushButton:pressed {{ background: #121A24; }}
QPushButton:focus {{ border-color: {COLORS['blue']}; }}
QPushButton:disabled {{ color: #66758A; background: #111821; border-color: #1B2633; }}
QPushButton#primaryButton {{ color: white; background: {COLORS['blue']}; border-color: {COLORS['blue']}; }}
QPushButton#primaryButton:hover {{ background: {COLORS['blue_hover']}; border-color: {COLORS['blue_hover']}; }}
QPushButton#primaryButton:pressed {{ background: #2866D2; }}
QPushButton#cancelButton {{ color: white; background: {COLORS['danger']}; border-color: {COLORS['danger']}; }}
QPushButton#cancelButton:hover {{ background: #D94E4B; }}
QPushButton#secondaryButton, QPushButton#loadMoreButton {{ color: {COLORS['blue']}; }}
QPushButton#linkButton {{ min-height: 26px; padding: 0 8px; color: {COLORS['blue']}; background: transparent; border: none; }}
QPushButton#linkButton:hover {{ color: {COLORS['nav_hover']}; background: {COLORS['surface_nested']}; }}
QPushButton#iconButton {{ min-width: 40px; max-width: 40px; padding: 0; font-size: 19px; }}
QStackedWidget#actionStack {{ background: transparent; border: none; }}
QLabel#repositoryTitle {{ font-family: "Cascadia Code", "Consolas"; font-size: 21px; font-weight: 600; }}
QLabel#repositoryDescription {{ color: {COLORS['muted']}; }}
QLabel#metricTitle {{ color: {COLORS['muted']}; font-size: 12px; }}
QLabel#metricValue {{ font-size: 27px; font-weight: 700; }}
QLabel#metricValue[technical="true"] {{ font-family: "Cascadia Code", "Consolas"; font-size: 17px; }}
QLabel#metricValue[accent="stars"] {{ color: {COLORS['warning']}; }}
QLabel#healthRating {{ font-size: 18px; font-weight: 600; }}
QLabel#healthHint {{ color: {COLORS['blue']}; font-size: 12px; }}
QLabel#profileBadge {{ color: {COLORS['blue']}; background: {COLORS['nav_indicator']}; border: 1px solid {COLORS['nav_indicator_border']}; border-radius: 7px; padding: 2px 7px; font-size: 11px; }}
QLabel#dialogTitle {{ font-size: 21px; font-weight: 600; }}
QLabel#dialogScore {{ font-size: 18px; font-weight: 700; }}
QLabel#sectionTitle {{ font-size: 16px; font-weight: 600; }}
QTextBrowser {{ color: {COLORS['text']}; background: {COLORS['surface']}; border: none; selection-background-color: {COLORS['blue']}; }}
QTextBrowser#overviewSummary {{ padding: 10px; border: 1px solid {COLORS['border']}; border-radius: 10px; }}
QTextBrowser#listBrowser {{ background: {COLORS['surface']}; padding: 0; }}
QTextBrowser#qualityBrowser {{ background: {COLORS['surface']}; padding: 0; min-height: 220px; }}
QTextBrowser#healthDetailsBrowser {{
    background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 8px; padding: 12px;
}}
QProgressBar {{ min-height: 4px; max-height: 4px; background: {COLORS['surface_nested']}; border: none; border-radius: 2px; }}
QProgressBar::chunk {{ background: {COLORS['blue']}; border-radius: 2px; }}
QSplitter::handle {{ background: {COLORS['background']}; width: 12px; height: 12px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: {COLORS['background']}; }}
QScrollBar:vertical {{ width: 11px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #435267; min-height: 28px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background: #5B6B80; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: transparent; }}
QScrollBar:horizontal {{ height: 11px; background: transparent; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #435267; min-width: 28px; border-radius: 5px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ width: 0; background: transparent; }}
QToolTip {{ color: {COLORS['text']}; background: {COLORS['surface_nested']}; border: 1px solid {COLORS['border']}; padding: 6px; }}
QMessageBox, QInputDialog {{ background: {COLORS['background']}; }}
QMessageBox QLabel, QInputDialog QLabel {{ color: {COLORS['text']}; }}
QComboBox {{ min-height: 38px; padding: 0 10px; background: {COLORS['surface_nested']}; border: 1px solid {COLORS['border']}; border-radius: 8px; }}
QComboBox:focus {{ border-color: {COLORS['blue']}; }}
QComboBox QAbstractItemView {{ color: {COLORS['text']}; background: {COLORS['surface_nested']}; border: 1px solid {COLORS['border']}; selection-background-color: {COLORS['blue_hover']}; }}
QSpinBox {{ min-height: 36px; padding: 0 8px; background: {COLORS['surface_nested']}; border: 1px solid {COLORS['border']}; border-radius: 8px; }}
QSpinBox:focus {{ border-color: {COLORS['blue']}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; }}
QLabel#tableHeader {{ color: {COLORS['muted']}; font-size: 11px; font-weight: 600; }}
QLabel#weightTotal {{ color: {COLORS['warning']}; }}
QLabel#weightTotal[balanced="true"] {{ color: {COLORS['success']}; }}
QScrollArea#criteriaScroll {{ background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 8px; }}
QScrollArea#criteriaScroll > QWidget > QWidget {{ background: {COLORS['surface']}; }}
"""


DOCUMENT_CSS = f"""
body {{ color: {COLORS['text']}; font-family: 'Segoe UI Variable', 'Segoe UI', Arial; font-size: 14px; }}
h1, h2, h3 {{ color: {COLORS['text']}; font-weight: 600; margin-top: 18px; margin-bottom: 8px; }}
h1 {{ font-size: 24px; }} h2 {{ font-size: 20px; }} h3 {{ font-size: 16px; }}
p {{ margin-top: 5px; margin-bottom: 9px; }}
a {{ color: {COLORS['blue']}; text-decoration: none; }}
pre {{ background-color: {COLORS['surface_nested']}; border: 1px solid {COLORS['border']}; padding: 10px; }}
code {{ font-family: 'Cascadia Code', 'Consolas'; color: {COLORS['text']}; }}
blockquote {{ color: {COLORS['muted']}; border-left: 3px solid {COLORS['blue']}; margin-left: 0; padding-left: 12px; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid {COLORS['border']}; padding: 7px 10px; }}
th {{ background-color: {COLORS['surface_nested']}; }}
"""


def apply_application_theme(app: QApplication) -> None:
    font = QFont()
    font.setFamilies(["Segoe UI Variable", "Segoe UI", "Arial"])
    font.setPixelSize(14)
    app.setStyle("Fusion")
    app.setFont(font)
    palette = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: COLORS["background"],
        QPalette.ColorRole.WindowText: COLORS["text"],
        QPalette.ColorRole.Base: COLORS["surface"],
        QPalette.ColorRole.AlternateBase: COLORS["surface_nested"],
        QPalette.ColorRole.Text: COLORS["text"],
        QPalette.ColorRole.Button: COLORS["surface_nested"],
        QPalette.ColorRole.ButtonText: COLORS["text"],
        QPalette.ColorRole.Highlight: COLORS["blue_hover"],
        QPalette.ColorRole.HighlightedText: COLORS["text"],
        QPalette.ColorRole.Link: COLORS["blue"],
        QPalette.ColorRole.LinkVisited: COLORS["purple"],
        QPalette.ColorRole.ToolTipBase: COLORS["surface_nested"],
        QPalette.ColorRole.ToolTipText: COLORS["text"],
        QPalette.ColorRole.PlaceholderText: COLORS["muted"],
    }.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(COLORS["muted"]))
    app.setPalette(palette)
    app.setStyleSheet(APP_STYLESHEET)


def health_accent(score: int) -> tuple[str, str]:
    if score >= 75:
        return "health-good", COLORS["success"]
    if score >= 40:
        return "health-warning", COLORS["warning"]
    return "health-danger", COLORS["danger"]


def style_markdown(document: QTextDocument) -> None:
    """Style Qt's parsed Markdown without interpreting untrusted HTML."""
    block = document.begin()
    while block.isValid():
        cursor = QTextCursor(block)
        block_format = block.blockFormat()
        code = (
            block_format.hasProperty(QTextFormat.Property.BlockCodeFence)
            or block_format.hasProperty(QTextFormat.Property.BlockCodeLanguage)
            or block_format.nonBreakableLines()
        )
        heading = block_format.headingLevel()
        quote = block_format.intProperty(QTextFormat.Property.BlockQuoteLevel) > 0
        block_format.setTopMargin(16 if heading else 4)
        block_format.setBottomMargin(8)
        if code:
            block_format.setBackground(QColor(COLORS["surface_nested"]))
            block_format.setLeftMargin(12)
            block_format.setRightMargin(12)
            block_format.setTopMargin(0)
            block_format.setBottomMargin(0)
            block_format.setLineHeight(145, 1)
        elif quote:
            block_format.setLeftMargin(16)
        cursor.setBlockFormat(block_format)
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                original = fragment.charFormat()
                fmt = QTextCharFormat()
                if code or original.fontFixedPitch():
                    fmt.setFontFamilies(["Cascadia Code", "Consolas"])
                    fmt.setFontFixedPitch(True)
                    fmt.setBackground(QColor(COLORS["surface_nested"]))
                    if code:
                        fmt.setFontWeight(QFont.Weight.Normal)
                if original.isAnchor():
                    fmt.setForeground(QColor(COLORS["blue"]))
                elif quote:
                    fmt.setForeground(QColor(COLORS["muted"]))
                if heading:
                    fmt.setFontWeight(QFont.Weight.DemiBold)
                cursor.setPosition(fragment.position())
                cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.MoveMode.KeepAnchor)
                cursor.mergeCharFormat(fmt)
            iterator += 1
        block = block.next()

    def style_tables(frame) -> None:
        for child in frame.childFrames():
            if isinstance(child, QTextTable):
                table_format = child.format()
                table_format.setBorder(1)
                table_format.setBorderBrush(QColor(COLORS["border"]))
                table_format.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
                table_format.setCellPadding(8)
                table_format.setCellSpacing(0)
                child.setFormat(table_format)
                for row in range(child.rows()):
                    for column in range(child.columns()):
                        cell = child.cellAt(row, column)
                        first = cell.firstCursorPosition()
                        last = cell.lastCursorPosition()
                        if not first.block().text() and first.block() != last.block():
                            first.deleteChar()
                        cell_cursor = cell.firstCursorPosition()
                        cell_cursor.setPosition(cell.lastCursorPosition().position(), QTextCursor.MoveMode.KeepAnchor)
                        cell_block_format = cell_cursor.blockFormat()
                        cell_block_format.setTopMargin(0)
                        cell_block_format.setBottomMargin(0)
                        cell_cursor.setBlockFormat(cell_block_format)
                        if row == 0:
                            cell_format = cell.format()
                            cell_format.setBackground(QColor(COLORS["surface_nested"]))
                            cell.setFormat(cell_format)
                            header_format = QTextCharFormat()
                            header_format.setFontWeight(QFont.Weight.DemiBold)
                            cell_cursor.mergeCharFormat(header_format)
            style_tables(child)

    style_tables(document.rootFrame())
