"""Minimal PyQt6 dashboard shell."""
from __future__ import annotations

import asyncio

try:  # pragma: no cover - optional dependency
    from PyQt6 import QtWidgets
except Exception:  # pragma: no cover
    QtWidgets = None

from ..core.orchestrator import SpatialCommandPlatform
from ..config import DEFAULT_CONFIG


class CommandDashboard(QtWidgets.QMainWindow if QtWidgets else object):  # type: ignore[misc]
    """Simple placeholder dashboard showing advisories."""

    def __init__(self, platform: SpatialCommandPlatform) -> None:  # pragma: no cover - GUI
        if QtWidgets is None:
            raise RuntimeError("PyQt6 is required for the desktop dashboard")
        super().__init__()
        self.platform = platform
        self.setWindowTitle("Operational Command Dashboard")
        self.resize(1024, 768)
        self._list = QtWidgets.QListWidget()
        self.setCentralWidget(self._list)
        self._timer = QtWidgets.QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)

    def refresh(self) -> None:  # pragma: no cover - GUI
        report = self.platform.latest_report()
        self._list.clear()
        if report:
            for advisory in report.advisories:
                self._list.addItem(advisory)


def run_dashboard() -> None:  # pragma: no cover - GUI
    if QtWidgets is None:
        raise RuntimeError("PyQt6 is required")
    app = QtWidgets.QApplication([])
    platform = SpatialCommandPlatform(DEFAULT_CONFIG)
    window = CommandDashboard(platform)

    async def bootstrap() -> None:
        await platform.initialize()
        window.show()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(bootstrap())
    app.exec()
    loop.run_until_complete(platform.shutdown())
