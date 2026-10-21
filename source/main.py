import os
import sys

# PyInstaller's Qt runtime hook does not reliably register the package DLL
# directories on Python 3.14. Keep the handles alive for the whole process;
# otherwise Windows removes the directories from the DLL search path again.
_DLL_DIRECTORY_HANDLES: list[object] = []
if getattr(sys, "frozen", False) and sys.platform == "win32":
    bundle_root = getattr(sys, "_MEIPASS", "")
    for package_name in ("shiboken6", "PySide6"):
        package_dir = os.path.join(bundle_root, package_name)
        if os.path.isdir(package_dir):
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(package_dir))

from dotenv import load_dotenv
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import apply_application_theme


def resource_path(*parts: str) -> str:
    """Return an asset path that works in source and packaged builds."""
    bundle_root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(bundle_root, *parts)


def main() -> int:
    load_dotenv()
    app = QApplication(sys.argv)
    app.setApplicationName("GitHub Repository Analyzer")
    app.setWindowIcon(QIcon(resource_path("assets", "github-repository-analyzer-logo.ico")))
    apply_application_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
