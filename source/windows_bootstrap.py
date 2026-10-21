"""Entry point executed by the Windows PyInstaller bootloader."""
import os
import sys

_DLL_DIRECTORY_HANDLES = []
for package_name in ("shiboken6", "PySide6"):
    package_dir = os.path.join(sys._MEIPASS, package_name)
    if os.path.isdir(package_dir):
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(package_dir))
_DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(sys._MEIPASS))

source_dir = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "source")
sys.path.insert(0, source_dir)
try:
    from main_windows import main
    result = main()
except Exception:
    import ctypes
    import traceback
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.dirname(sys.executable)), "RepoScope")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "startup-error.log")
    with open(log_file, "w", encoding="utf-8") as stream:
        traceback.print_exc(file=stream)
    ctypes.windll.user32.MessageBoxW(
        None,
        "Не удалось запустить RepoScope.\n\nРаспакуйте архив полностью и сохраните папки source и _internal рядом с EXE.\n\nПодробности: " + log_file,
        "RepoScope — ошибка запуска", 0x10,
    )
    raise SystemExit(1)
raise SystemExit(result)
