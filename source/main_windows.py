"""Windows entry point for the portable RepoScope build."""
import os
import json
import platform
from pathlib import Path
import sys

from dotenv import load_dotenv
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from models.repository import RepositoryAnalysis
from ui.main_window import MainWindow
from ui.theme import apply_application_theme


def main() -> int:
    executable_dir = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    # Explicit paths also work when launched from the desktop file manager.
    load_dotenv(executable_dir / ".env", override=False)
    config_root = Path(os.environ.get("APPDATA", str(Path.home())))
    load_dotenv(config_root / "RepoScope" / ".env", override=False)
    assets_root = Path(__file__).resolve().parent
    smoke_test = "--smoke-test" in sys.argv
    app = QApplication([sys.argv[0]])
    app.setApplicationName("RepoScope")
    app.setOrganizationName("RepoScope")
    app.setDesktopFileName("reposcope")
    app.setWindowIcon(QIcon(str(assets_root / "assets" / "github-repository-analyzer-logo.ico")))
    apply_application_theme(app)
    window = MainWindow()
    window.show()
    if smoke_test:
        window.set_animations_enabled(False)
        window.show_result(RepositoryAnalysis(
            owner="octocat", name="Hello-World", full_name="octocat/Hello-World",
            description="Проверка Windows-сборки RepoScope", stars=100, forks=10,
            updated_at="2026-10-14T10:00:00Z", last_commit_date="2026-10-14T10:00:00Z",
            languages={"Python": 1000}, readme="# RepoScope\n\nWindows build check.",
            quality_files={"LICENSE": True}, has_tests=True, has_actions=True,
            commit_counts={30: 5, 90: 20, 365: 50},
        ))

        def verify() -> None:
            for index in range(5):
                window._show_page(index)
                app.processEvents()
            window._show_evaluation_settings()
            app.processEvents()
            window._evaluation_dialog.close()
            window._show_health_details()
            app.processEvents()
            window._health_dialog.close()
            if "--smoke-test-report" in sys.argv:
                report_path = Path(sys.argv[sys.argv.index("--smoke-test-report") + 1])
                report_path.write_text(json.dumps({
                    "status": "OK", "platform": sys.platform,
                    "python": platform.python_version(), "pages": 5,
                    "criteria": len(window.evaluation_profile.criteria),
                    "ui_module": sys.modules["ui.main_window"].__file__,
                    "evaluation_module": sys.modules["utils.evaluation"].__file__,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
            window.close()
            app.quit()

        QTimer.singleShot(1000, verify)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
