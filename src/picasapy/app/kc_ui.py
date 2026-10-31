"""KC Picasa additions: whole-UI zoom, restart, and About info (KC app playbook).

Qt Quick fixes its scale factor when the QGuiApplication starts, so the zoom is
applied through ``QT_SCALE_FACTOR`` before the app is created. Changing it saves the
new value and offers a one-click restart (the window reopens at the new size).
A ``QT_SCALE_FACTOR`` already set in the environment wins, so tests and the OS
display scale are never overridden; Windows display scaling stacks on top.
"""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Property, QObject, QSettings, Signal, Slot
from PySide6.QtGui import QGuiApplication

KC_VERSION = "0.1.0"
KC_APP_NAME = "KC Picasa"
KC_BRAND_LABEL = "KCCS · mypueblopc.com"
KC_REPO_URL = "https://github.com/pueblokc/kc-picasa"
UPSTREAM_URL = "https://github.com/sanchomuzax/PicasaPy"

UI_SCALE_KEY = "view/kcUiScale"
DEFAULT_UI_SCALE = 1.25
MIN_UI_SCALE = 0.75
MAX_UI_SCALE = 2.5
UI_SCALE_STEP = 0.1

# Set in the environment of the process we start, so it knows the zoom came from us
# (and may be replaced on the next restart) rather than from the user's shell.
_OWN_SCALE_MARK = "KC_PICASA_SCALE_FROM_SETTINGS"


def clamp_ui_scale(value, default: float = DEFAULT_UI_SCALE) -> float:
    """Saved value -> a zoom factor in [MIN, MAX], rounded to 0.05. Bad values -> default."""
    try:
        scale = float(value)
    except (TypeError, ValueError):
        return default
    if scale != scale or scale in (float("inf"), float("-inf")):  # NaN / inf
        return default
    scale = min(MAX_UI_SCALE, max(MIN_UI_SCALE, scale))
    return round(round(scale / 0.05) * 0.05, 2)


def _settings() -> QSettings:
    return QSettings("PicasaPy", "PicasaPy")


def apply_ui_scale_env(settings: QSettings | None = None, environ=os.environ) -> float | None:
    """Before QGuiApplication: put the saved zoom into QT_SCALE_FACTOR.

    Returns the factor applied, or None when the environment already set one.
    """
    if environ.get("QT_SCALE_FACTOR") and not environ.get(_OWN_SCALE_MARK):
        return None
    settings = settings or _settings()
    scale = clamp_ui_scale(settings.value(UI_SCALE_KEY, DEFAULT_UI_SCALE))
    environ["QT_SCALE_FACTOR"] = f"{scale:g}"
    environ[_OWN_SCALE_MARK] = "1"
    return scale


def saved_dark_theme(settings: QSettings | None = None) -> bool:
    from .appearance_controller import DARK_THEME_KEY, coerce_dark_flag

    settings = settings or _settings()
    return coerce_dark_flag(settings.value(DARK_THEME_KEY))


def restart_command(argv: list[str] | None = None) -> list[str]:
    """The command that reopens this app with the same folders."""
    argv = list(sys.argv if argv is None else argv)
    return [sys.executable, "-m", "picasapy.app", *argv[1:]]


class KcUiController(QObject):
    """QML context object ``kcUi``: zoom controls and About details."""

    uiScaleChanged = Signal()

    def __init__(self, settings: QSettings | None = None, active_scale: float | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings or _settings()
        self._scale = clamp_ui_scale(self._settings.value(UI_SCALE_KEY, DEFAULT_UI_SCALE))
        if active_scale is None:
            active_scale = clamp_ui_scale(os.environ.get("QT_SCALE_FACTOR", "1"), default=1.0)
        self._active = active_scale

    # --- zoom -------------------------------------------------------------
    @Property(float, notify=uiScaleChanged)
    def uiScale(self) -> float:  # noqa: N802 - QML property
        """The saved zoom (applies after restart)."""
        return self._scale

    @Property(int, notify=uiScaleChanged)
    def uiScalePercent(self) -> int:  # noqa: N802
        return int(round(self._scale * 100))

    @Property(bool, notify=uiScaleChanged)
    def restartNeeded(self) -> bool:  # noqa: N802
        return abs(self._scale - self._active) > 0.001

    @Slot(float)
    def setUiScale(self, value: float) -> None:  # noqa: N802
        scale = clamp_ui_scale(value)
        if scale == self._scale:
            return
        self._scale = scale
        self._settings.setValue(UI_SCALE_KEY, f"{scale:g}")
        self._settings.sync()
        self.uiScaleChanged.emit()

    @Slot()
    def zoomIn(self) -> None:  # noqa: N802
        self.setUiScale(self._scale + UI_SCALE_STEP)

    @Slot()
    def zoomOut(self) -> None:  # noqa: N802
        self.setUiScale(self._scale - UI_SCALE_STEP)

    @Slot()
    def zoomReset(self) -> None:  # noqa: N802
        self.setUiScale(DEFAULT_UI_SCALE)

    @Slot(result=bool)
    def restartApp(self) -> bool:  # noqa: N802
        """Start a fresh copy, then quit this one. Returns False if the start failed."""
        env = dict(os.environ)
        env.pop("QT_SCALE_FACTOR", None)
        env.pop(_OWN_SCALE_MARK, None)
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        try:
            subprocess.Popen(restart_command(), env=env, creationflags=flags, close_fds=True)
        except OSError:
            return False
        app = QGuiApplication.instance()
        if app is not None:
            app.quit()
        return True

    # --- about --------------------------------------------------------------
    @Property(str, constant=True)
    def version(self) -> str:
        return KC_VERSION

    @Property(str, constant=True)
    def appName(self) -> str:  # noqa: N802
        return KC_APP_NAME

    @Property(str, constant=True)
    def brandLabel(self) -> str:  # noqa: N802
        return KC_BRAND_LABEL

    @Property(str, constant=True)
    def repoUrl(self) -> str:  # noqa: N802
        return KC_REPO_URL

    @Property(str, constant=True)
    def upstreamUrl(self) -> str:  # noqa: N802
        return UPSTREAM_URL

    @Slot(result=str)
    def statusJson(self) -> str:  # noqa: N802
        import json

        return json.dumps({"app": KC_APP_NAME, "version": KC_VERSION, "uiScale": self._scale,
                           "activeScale": self._active, "darkTheme": saved_dark_theme(self._settings)})
