"""Application entry point."""
from __future__ import annotations

import sys

from app_info import APP_NAME, VERSION_LABEL, __version__


def main() -> int:
    if "--version" in sys.argv[1:]:
        print(f"{APP_NAME} {VERSION_LABEL} ({__version__})")
        return 0

    # Load Qt only when the GUI is started.
    from PySide6.QtWidgets import QApplication
    import ui

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MKVStudio.MKVStudio.1")
        except (AttributeError, OSError):
            pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(ui.app_icon())
    sans = ui.pick_family(ui.SANS_CANDIDATES)
    display = ui.pick_family(ui.DISPLAY_CANDIDATES)
    mono = ui.pick_family(ui.MONO_CANDIDATES, "monospace")
    app.setStyleSheet(ui.build_style(sans, display, mono))
    window = ui.MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
