"""KC Picasa: whole-UI zoom clamp, env application and settings round-trip."""

import json
import sys

import pytest
from PySide6.QtCore import QSettings

from picasapy.app import kc_ui


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.mark.parametrize("value,expected", [
    (None, 1.25), ("", 1.25), ("abc", 1.25), (float("nan"), 1.25), (float("inf"), 1.25),
    ("1.4", 1.4), (1.42, 1.4), (0.1, 0.75), (9, 2.5), ("2.5", 2.5), (0.75, 0.75), (1.0, 1.0),
])
def test_clamp_ui_scale(value, expected):
    assert kc_ui.clamp_ui_scale(value) == expected


def test_env_gets_saved_scale(settings):
    settings.setValue(kc_ui.UI_SCALE_KEY, "1.6")
    env = {}
    assert kc_ui.apply_ui_scale_env(settings, env) == 1.6
    assert env["QT_SCALE_FACTOR"] == "1.6"


def test_env_default_when_unset(settings):
    env = {}
    assert kc_ui.apply_ui_scale_env(settings, env) == 1.25
    assert env["QT_SCALE_FACTOR"] == "1.25"


def test_user_set_env_wins(settings):
    settings.setValue(kc_ui.UI_SCALE_KEY, "2")
    env = {"QT_SCALE_FACTOR": "1"}
    assert kc_ui.apply_ui_scale_env(settings, env) is None
    assert env["QT_SCALE_FACTOR"] == "1"


def test_controller_zoom_persists_and_flags_restart(qt_app, settings):
    c = kc_ui.KcUiController(settings=settings, active_scale=1.25)
    assert c.uiScale == 1.25 and c.uiScalePercent == 125 and not c.restartNeeded
    seen = []
    c.uiScaleChanged.connect(lambda: seen.append(c.uiScale))
    c.zoomIn()
    c.zoomIn()
    assert c.uiScale == 1.45 and c.restartNeeded
    assert kc_ui.clamp_ui_scale(settings.value(kc_ui.UI_SCALE_KEY)) == 1.45
    c.zoomReset()
    assert c.uiScale == 1.25 and not c.restartNeeded
    assert seen == [1.35, 1.45, 1.25]
    # survives a "restart": a new controller reads the saved value
    c.setUiScale(1.8)
    assert kc_ui.KcUiController(settings=settings, active_scale=1.8).uiScale == 1.8


def test_controller_clamps_at_limits(qt_app, settings):
    c = kc_ui.KcUiController(settings=settings, active_scale=1.25)
    for _ in range(40):
        c.zoomOut()
    assert c.uiScale == kc_ui.MIN_UI_SCALE
    for _ in range(40):
        c.zoomIn()
    assert c.uiScale == kc_ui.MAX_UI_SCALE


def test_restart_command_reuses_folders():
    cmd = kc_ui.restart_command(["C:/x/__main__.py", "C:/Pics"])
    assert cmd == [sys.executable, "-m", "picasapy.app", "C:/Pics"]


def test_status_json(qt_app, settings):
    data = json.loads(kc_ui.KcUiController(settings=settings, active_scale=1.0).statusJson())
    assert data["app"] == "KC Picasa" and data["version"] == kc_ui.KC_VERSION
    assert data["darkTheme"] is True  # dark is the default
