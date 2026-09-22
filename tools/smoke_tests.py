import asyncio
import configparser
import json
import os
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


class temporary_profile:
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dzfyq_smoke_profile_")
        self.old_env = {key: os.environ.get(key) for key in ("USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA")}
        root = Path(self.temp.name)
        os.environ["USERPROFILE"] = str(root)
        os.environ["HOME"] = str(root)
        os.environ["APPDATA"] = str(root / "AppData" / "Roaming")
        os.environ["LOCALAPPDATA"] = str(root / "AppData" / "Local")
        Path(os.environ["APPDATA"]).mkdir(parents=True, exist_ok=True)
        Path(os.environ["LOCALAPPDATA"]).mkdir(parents=True, exist_ok=True)
        return root

    def __exit__(self, exc_type, exc, tb):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()


def check_versions():
    from src.version import APP_VERSION

    assert APP_VERSION == "1.2.11", APP_VERSION
    for relative in ("setup.py", "version.generated.iss", "file_version_info.txt", "src/ziyuan/changelog.md"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "1.2.11" in text, relative


def check_first_run_template():
    path = REPO_ROOT / "src" / "config" / "first_run.ini"
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8")
    assert "last_version = 0.0.0" in text


def check_license_notices():
    title_bar = (REPO_ROOT / "src" / "gui" / "title_bar.py").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    required = "Copyright (c) 2022 OwO Network Limited"
    assert required in title_bar
    assert required in readme


def check_config_migration():
    from src.shezhi.config import Config

    with temporary_profile() as root:
        Config._instance = None
        config_dir = root / ".dzfyq"
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "openai_compat": {
                        "vendor": "自定义",
                        "base_url": "https://example.invalid/v1",
                        "model": "demo-model",
                        "api_key": "demo-key",
                        "profiles": {
                            "OpenAI": {
                                "base_url": "https://api.openai.com/v1",
                                "model": "gpt-4o-mini",
                                "api_key": "",
                            }
                        },
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        config = Config()
        assert Config() is config
        profiles = config.get("openai_compat.profiles")
        assert profiles["自定义"]["base_url"] == "https://example.invalid/v1"
        assert profiles["自定义"]["model"] == "demo-model"
        assert config.get("display.source_font_size") == 18
        assert config.get("display.target_font_size") == 18


def check_update_manifest_and_script():
    from src.gongju.update import Updater
    from src.version import APP_VERSION

    with tempfile.TemporaryDirectory(prefix="dzfyq_update_smoke_") as temp:
        root = Path(temp)
        old_home = os.environ.get("DZFYQ_HOME")
        os.environ["DZFYQ_HOME"] = str(root / "dzfyq_home")
        try:
            updater = Updater()
            updater.latest_version = APP_VERSION
            try:
                updater._validate_update_manifest(str(root))
                raise AssertionError("missing manifest accepted")
            except RuntimeError:
                pass
            (root / "update_manifest.json").write_text(json.dumps({"app_version": "1.2.4"}), encoding="utf-8")
            try:
                updater._validate_update_manifest(str(root))
                raise AssertionError("mismatched manifest accepted")
            except RuntimeError:
                pass
            (root / "update_manifest.json").write_text(json.dumps({"app_version": APP_VERSION}), encoding="utf-8")
            updater._validate_update_manifest(str(root))

            script_path = root / "apply_update.ps1"
            updater._write_apply_script(str(script_path))
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"[scriptblock]::Create((Get-Content -LiteralPath '{script_path}' -Raw -Encoding UTF8)) | Out-Null",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            assert result.returncode == 0, result.stderr or result.stdout
        finally:
            if old_home is None:
                os.environ.pop("DZFYQ_HOME", None)
            else:
                os.environ["DZFYQ_HOME"] = old_home



def check_update_prompt_waits_for_changelog_modal():
    from PyQt5.QtWidgets import QDialog
    from src.gui import update_controller
    from src.gui.update_controller import UpdateCoordinator

    class FakeUpdater:
        force_update = False

        async def download_update(self):
            return None

    coordinator = UpdateCoordinator.__new__(UpdateCoordinator)
    coordinator.owner = object()
    coordinator.updater = FakeUpdater()
    coordinator.progress_dialog = None
    coordinator._update_checking = False
    coordinator._update_error_occurred = False
    coordinator._modal_dialog_active = False
    coordinator._pending_update_prompt = None

    config = configparser.ConfigParser()
    config.add_section("App")
    config.set("App", "first_run", "0")
    config.set("App", "last_version", "0.0.0")

    events = []
    original_changelog = update_controller.GengXinRiZhi
    original_prompt = update_controller.UpdatePromptDialog

    class FakeChangelogDialog:
        def __init__(self, owner):
            events.append(("changelog_init", coordinator._modal_dialog_active))

        def setModal(self, modal):
            events.append(("changelog_modal", modal))

        def exec_(self):
            events.append(("changelog_exec", coordinator._modal_dialog_active))
            coordinator.on_update_available("9.9.9", "notes", False)
            events.append(("after_update_signal", coordinator._pending_update_prompt is not None))
            return QDialog.Accepted

    class FakeUpdatePromptDialog:
        def __init__(self, owner, version, notes, force_update):
            events.append(("prompt_init", coordinator._modal_dialog_active, version, notes, force_update))

        def exec_(self):
            events.append(("prompt_exec", coordinator._modal_dialog_active))
            return QDialog.Rejected

    update_controller.GengXinRiZhi = FakeChangelogDialog
    update_controller.UpdatePromptDialog = FakeUpdatePromptDialog
    coordinator.report_previous_update_state = lambda: None
    coordinator.load_first_run_state = lambda: (config, str(REPO_ROOT / "unused-first-run.ini"))
    coordinator.persist_first_run_state = lambda saved_config, path: events.append(
        ("persist", saved_config.get("App", "first_run"), saved_config.get("App", "last_version"))
    )
    try:
        coordinator.show_changelog_if_needed()
    finally:
        update_controller.GengXinRiZhi = original_changelog
        update_controller.UpdatePromptDialog = original_prompt

    assert events == [
        ("changelog_init", True),
        ("changelog_modal", True),
        ("changelog_exec", True),
        ("after_update_signal", True),
        ("persist", "1", update_controller.APP_VERSION),
        ("prompt_init", True, "9.9.9", "notes", False),
        ("prompt_exec", True),
    ]
    assert coordinator._pending_update_prompt is None
    assert coordinator._modal_dialog_active is False


def check_autostart():
    if sys.platform != "win32":
        return
    from src.gongju import autostart

    with temporary_profile():
        shortcut = Path(autostart._get_windows_shortcut_path())
        shortcut.parent.mkdir(parents=True, exist_ok=True)
        shortcut.write_bytes(b"broken")
        assert autostart.is_autostart_enabled() is False
        autostart.configure_autostart(True)
        assert shortcut.exists()
        assert autostart.is_autostart_enabled() is True
        autostart.configure_autostart(False)
        assert not shortcut.exists()


def check_autostart_rebuilds_mismatched_shortcut():
    if sys.platform != "win32":
        return
    from src.gongju import autostart

    with temporary_profile() as root:
        shortcut = Path(autostart._get_windows_shortcut_path())
        shortcut.parent.mkdir(parents=True, exist_ok=True)
        old_dir = root / "OldInstall"
        old_dir.mkdir(parents=True)
        old_target = old_dir / "old.exe"
        old_target.write_bytes(b"MZ")
        script = f"""
$ErrorActionPreference = 'Stop'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut({autostart._powershell_literal(str(shortcut))})
$shortcut.TargetPath = {autostart._powershell_literal(str(old_target))}
$shortcut.Arguments = '--old'
$shortcut.WorkingDirectory = {autostart._powershell_literal(str(old_dir))}
$shortcut.IconLocation = {autostart._powershell_literal(str(old_target))}
$shortcut.Save()
"""
        autostart._run_powershell(script)

        assert autostart.is_autostart_enabled() is False
        autostart.configure_autostart(True)
        data = autostart._read_windows_shortcut(str(shortcut))
        command = autostart._get_launch_command()
        assert autostart._paths_equivalent(data.get("TargetPath", ""), command[0])
        assert autostart._normalize_windows_arguments(data.get("Arguments", "")) == autostart._normalize_windows_arguments(
            autostart._format_windows_arguments(command[1:])
        )
        assert autostart.is_autostart_enabled() is True


def check_autostart_shortcut_validation_tolerates_workdir_drift():
    from src.gongju import autostart

    original_read = autostart._read_windows_shortcut
    original_launch = autostart._get_launch_command
    original_workdir = autostart._get_working_directory
    original_is_packaged = autostart._is_packaged_app
    original_exists = autostart.os.path.exists
    try:
        autostart._get_launch_command = lambda: [r"C:\Program Files\Dzfyq\大佐翻译官.exe"]
        autostart._get_working_directory = lambda: r"C:\Program Files\Dzfyq"
        autostart._is_packaged_app = lambda: True
        autostart.os.path.exists = lambda path: True
        autostart._read_windows_shortcut = lambda path: {
            "TargetPath": r"C:\Program Files\Dzfyq\大佐翻译官.exe",
            "Arguments": "",
            "WorkingDirectory": "",
        }
        assert autostart._windows_shortcut_matches("startup.lnk") is True

        autostart._read_windows_shortcut = lambda path: {
            "TargetPath": r"C:\Program Files\Dzfyq\大佐翻译官.exe",
            "Arguments": "",
            "WorkingDirectory": r"C:\Other",
        }
        assert autostart._windows_shortcut_matches("startup.lnk") is False
        assert autostart._windows_shortcut_mismatch_reason("startup.lnk") == "working_directory"

        autostart._read_windows_shortcut = lambda path: {
            "TargetPath": r"C:\Other\大佐翻译官.exe",
            "Arguments": "",
            "WorkingDirectory": r"C:\Program Files\Dzfyq",
        }
        assert autostart._windows_shortcut_mismatch_reason("startup.lnk") == "target"
    finally:
        autostart._read_windows_shortcut = original_read
        autostart._get_launch_command = original_launch
        autostart._get_working_directory = original_workdir
        autostart._is_packaged_app = original_is_packaged
        autostart.os.path.exists = original_exists


def check_autostart_unknown_does_not_save_false():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication, QWidget
    from src.gui import shezhi_chuangkou
    from src.gui.shezhi_chuangkou import SheZhiChuangKou
    from src.shezhi.config import Config

    class Parent(QWidget):
        def __init__(self):
            super().__init__()
            self.config = Config()

        def reload_translation_api(self):
            pass

    with temporary_profile():
        Config._instance = None
        app = QApplication.instance() or QApplication(sys.argv)
        parent = Parent()
        parent.config.set("auto_start", True)
        original_get_state = shezhi_chuangkou.get_autostart_state
        original_configure = shezhi_chuangkou.configure_autostart
        calls = []
        shezhi_chuangkou.get_autostart_state = lambda: None
        shezhi_chuangkou.configure_autostart = lambda enabled: calls.append(enabled)
        try:
            dialog = SheZhiChuangKou(parent)
            assert dialog.auto_start_checkbox.checkState() == Qt.PartiallyChecked
            dialog._save_form_to_config()
            assert parent.config.get("auto_start") is True
            assert calls == []
            dialog.close()
            parent.close()
        finally:
            shezhi_chuangkou.get_autostart_state = original_get_state
            shezhi_chuangkou.configure_autostart = original_configure


def check_legacy_installer_reuses_existing_install_dir():
    import tools.legacy_update_installer as installer

    with temporary_profile() as root:
        default_dir = installer._default_install_dir()
        custom_dir = root / "ExistingInstall" / installer.APP_NAME
        default_dir.mkdir(parents=True)
        custom_dir.mkdir(parents=True)
        (default_dir / installer.EXE_NAME).write_text("wrong 1.2.5 install", encoding="utf-8")
        (custom_dir / installer.EXE_NAME).write_text("existing install", encoding="utf-8")

        originals = (
            installer._registry_install_dirs,
            installer._running_install_dirs,
            installer._shortcut_install_dirs,
            installer._known_install_dirs,
        )
        installer._registry_install_dirs = lambda: []
        installer._running_install_dirs = lambda: []
        installer._shortcut_install_dirs = lambda: [default_dir]
        installer._known_install_dirs = lambda: [custom_dir, default_dir]
        try:
            candidates = installer._install_candidates_by_source()
            assert installer._choose_install_dir(candidates) == custom_dir
            assert installer._install_dir() == custom_dir
        finally:
            (
                installer._registry_install_dirs,
                installer._running_install_dirs,
                installer._shortcut_install_dirs,
                installer._known_install_dirs,
            ) = originals


def check_window_geometry_keeps_recoverable_screen_area():
    from PyQt5.QtCore import QPoint, QRect
    from src.gui import window_geometry

    class FakeScreen:
        def __init__(self, available):
            self.available = QRect(available)

        def availableGeometry(self):
            return QRect(self.available)

    class FakeApplication:
        screen = FakeScreen(QRect(0, 0, 800, 600))

        @classmethod
        def primaryScreen(cls):
            return cls.screen

        @classmethod
        def screenAt(cls, point):
            return cls.screen if cls.screen.available.contains(point) else None

        @classmethod
        def screens(cls):
            return [cls.screen]

    class RaisingApplication:
        @classmethod
        def primaryScreen(cls):
            raise AssertionError("cached resize should not query QApplication.primaryScreen")

        @classmethod
        def screenAt(cls, point):
            raise AssertionError("cached resize should not query QApplication.screenAt")

        @classmethod
        def screens(cls):
            raise AssertionError("cached resize should not query QApplication.screens")

    class FakeConfig:
        def __init__(self, window):
            self._config = {"window": dict(window)}
            self.save_count = 0

        def get(self, key, default=None):
            current = self._config
            for part in key.split("."):
                if not isinstance(current, dict) or part not in current:
                    return default
                current = current[part]
            return current

        def save(self):
            self.save_count += 1

    class FakeWindow:
        def __init__(self, window_config, available, minimum=(969, 684)):
            FakeApplication.screen = FakeScreen(available)
            self.config = FakeConfig(window_config)
            self._geometry = QRect(0, 0, 969, 684)
            self._minimum = minimum
            self._maximum = (16777215, 16777215)
            self.is_mini_mode = False

        def windowHandle(self):
            return None

        def screen(self):
            return FakeApplication.screen

        def minimumWidth(self):
            return self._minimum[0]

        def minimumHeight(self):
            return self._minimum[1]

        def setMinimumSize(self, width, height):
            self._minimum = (width, height)

        def maximumWidth(self):
            return self._maximum[0]

        def maximumHeight(self):
            return self._maximum[1]

        def width(self):
            return self._geometry.width()

        def height(self):
            return self._geometry.height()

        def geometry(self):
            return QRect(self._geometry)

        def setGeometry(self, *args):
            self._geometry = QRect(*args)

        def isMaximized(self):
            return False

    def visible_rect(rect, available):
        return QRect(available).intersected(rect)

    original_application = window_geometry.QApplication
    window_geometry.QApplication = FakeApplication
    try:
        available_800 = QRect(0, 0, 800, 600)
        oversized = FakeWindow(
            {"width": 3000, "height": 2000, "x": 10, "y": 20},
            available_800,
        )
        window_geometry.load_window_geometry(oversized)
        assert oversized.geometry() == QRect(10, 20, 800, 600)
        assert oversized.config._config["window"] == {"width": 800, "height": 600, "x": 10, "y": 20}

        partially_offscreen = FakeWindow(
            {"width": 500, "height": 400, "x": -120, "y": 80},
            available_800,
            minimum=(300, 200),
        )
        window_geometry.load_window_geometry(partially_offscreen)
        assert partially_offscreen.geometry() == QRect(-120, 80, 500, 400)
        assert partially_offscreen.config.save_count == 0

        negative_screen = FakeWindow(
            {"width": 500, "height": 400, "x": -1200, "y": 40},
            QRect(-1280, 0, 1280, 720),
            minimum=(300, 200),
        )
        window_geometry.load_window_geometry(negative_screen)
        assert negative_screen.geometry() == QRect(-1200, 40, 500, 400)

        available_1920 = QRect(0, 0, 1920, 1080)
        offscreen = FakeWindow(
            {"width": 1000, "height": 700, "x": 5000, "y": -300},
            available_1920,
        )
        window_geometry.load_window_geometry(offscreen)
        visible = visible_rect(offscreen.geometry(), available_1920)
        assert visible.width() >= 96
        assert visible.height() >= 64

        small_screen = FakeWindow(
            {"width": 857, "height": 620, "x": None, "y": None},
            QRect(0, 0, 640, 480),
        )
        window_geometry.load_window_geometry(small_screen)
        assert small_screen.geometry() == QRect(0, 0, 640, 480)
        assert small_screen.minimumWidth() == 640
        assert small_screen.minimumHeight() == 480

        to_save = FakeWindow(
            {"width": 857, "height": 620, "x": 0, "y": 0},
            available_800,
        )
        to_save.setGeometry(-50, -50, 3000, 2000)
        window_geometry.save_window_geometry(to_save)
        assert to_save.geometry() == QRect(-50, 0, 800, 600)
        assert to_save.config._config["window"] == {"width": 800, "height": 600, "x": -50, "y": 0}

        partial_to_save = FakeWindow(
            {"width": 500, "height": 400, "x": 0, "y": 0},
            available_800,
            minimum=(300, 200),
        )
        partial_to_save.setGeometry(-120, 80, 500, 400)
        window_geometry.save_window_geometry(partial_to_save)
        assert partial_to_save.geometry() == QRect(-120, 80, 500, 400)
        assert partial_to_save.config._config["window"] == {"width": 500, "height": 400, "x": -120, "y": 80}

        offscreen_to_save = FakeWindow(
            {"width": 500, "height": 400, "x": 0, "y": 0},
            available_800,
            minimum=(300, 200),
        )
        offscreen_to_save.setGeometry(5000, 5000, 500, 400)
        window_geometry.save_window_geometry(offscreen_to_save)
        visible = visible_rect(offscreen_to_save.geometry(), available_800)
        assert visible.width() >= 96
        assert visible.height() >= 64

        barely_visible_to_save = FakeWindow(
            {"width": 500, "height": 400, "x": 0, "y": 0},
            available_800,
            minimum=(300, 200),
        )
        barely_visible_to_save.setGeometry(-480, 80, 500, 400)
        window_geometry.save_window_geometry(barely_visible_to_save)
        visible = visible_rect(barely_visible_to_save.geometry(), available_800)
        assert visible.width() >= 96
        assert visible.height() >= 64
        assert barely_visible_to_save.geometry().x() != -480

        resized = FakeWindow(
            {"width": 790, "height": 590, "x": 10, "y": 10},
            available_800,
        )
        resized.setGeometry(10, 10, 790, 590)
        resized._resize_start_pos = QPoint(0, 0)
        resized._resize_start_geometry = QRect(resized.geometry())
        resized._resize_edge = "bottom-right"
        window_geometry.perform_resize(resized, QPoint(2000, 2000))
        assert resized.geometry() == QRect(10, 10, 800, 600)

        left_resized = FakeWindow(
            {"width": 790, "height": 590, "x": 100, "y": 100},
            available_800,
            minimum=(300, 200),
        )
        left_resized.setGeometry(100, 100, 790, 590)
        left_resized._resize_start_pos = QPoint(0, 0)
        left_resized._resize_start_geometry = QRect(left_resized.geometry())
        left_resized._resize_edge = "left"
        window_geometry.perform_resize(left_resized, QPoint(-2000, 0))
        assert left_resized.geometry() == QRect(90, 100, 800, 590)

        programmatic_resize = FakeWindow(
            {"width": 500, "height": 400, "x": 0, "y": 0},
            available_800,
            minimum=(300, 200),
        )
        programmatic_resize.setGeometry(-120, 80, 3000, 2000)
        window_geometry.protect_window_size(programmatic_resize)
        assert programmatic_resize.geometry() == QRect(-120, 80, 800, 600)

        dragged = FakeWindow(
            {"width": 500, "height": 400, "x": 0, "y": 0},
            available_800,
            minimum=(300, 200),
        )
        dragged.setGeometry(-120, 80, 500, 400)
        window_geometry.begin_move(dragged)
        assert window_geometry.constrain_move_position(dragged, QPoint(-220, -80)) == QPoint(-220, 0)
        assert window_geometry.constrain_move_position(dragged, QPoint(-220, 120)) == QPoint(-220, 120)
        window_geometry.end_move(dragged)
        assert dragged._move_available_geometries is None

        cached_resize = FakeWindow(
            {"width": 790, "height": 590, "x": 10, "y": 10},
            available_800,
        )
        cached_resize.setGeometry(10, 10, 790, 590)
        window_geometry.begin_resize(cached_resize, "bottom-right", QPoint(0, 0))
        window_geometry.QApplication = RaisingApplication
        window_geometry.perform_resize(cached_resize, QPoint(2000, 2000))
        assert cached_resize.geometry() == QRect(10, 10, 800, 600)
        window_geometry.end_resize(cached_resize)
        assert cached_resize._resize_available_geometry is None
        assert cached_resize._resize_minimum_size is None
    finally:
        window_geometry.QApplication = original_application


async def check_achord_session():
    from src.gongju.fanyi_api.achord_builtin import AchordBuiltinAPI

    class FakeManager:
        token = "secret-token"
        base_url = "http://127.0.0.1:65530"

        async def ensure_started(self):
            return None

        def stop(self):
            return None

    api = AchordBuiltinAPI(manager=FakeManager())
    session = await api._ensure_ready()
    assert getattr(session, "_trust_env") is False
    await api.close()


def check_achord_payload_materialization():
    from src.gongju import achord_engine
    from src.gongju.achord_engine import AchordEngineLocator

    with tempfile.TemporaryDirectory(prefix="dzfyq_engine_payload_") as temp:
        root = Path(temp)
        bundled = root / "bundled"
        cache = root / "cache"
        bundled.mkdir(parents=True)
        source_exe = REPO_ROOT / "third_party" / "deeplx" / "windows" / "amd64" / "deeplx.exe"
        source_manifest = REPO_ROOT / "third_party" / "deeplx" / "windows" / "amd64" / "manifest.json"
        source_license = REPO_ROOT / "third_party" / "deeplx" / "windows" / "amd64" / "LICENSE"
        (bundled / "deeplx.exe.payload").write_bytes(source_exe.read_bytes())
        (bundled / "manifest.json").write_text(source_manifest.read_text(encoding="utf-8"), encoding="utf-8")
        (bundled / "LICENSE").write_text(source_license.read_text(encoding="utf-8"), encoding="utf-8")

        original_cache = achord_engine._engine_cache_root
        original_bundled = achord_engine._bundled_engine_dir
        original_dev = achord_engine._dev_engine_dir
        achord_engine._engine_cache_root = lambda: str(cache)
        achord_engine._bundled_engine_dir = lambda: str(bundled)
        achord_engine._dev_engine_dir = lambda: str(root / "missing_dev")
        try:
            info = AchordEngineLocator.current_engine()
            assert info.source == "payload_cache"
            assert Path(info.executable_path).is_file()
            assert Path(info.executable_path).name == "deeplx.exe"
            assert not (bundled / "deeplx.exe").exists()
        finally:
            achord_engine._engine_cache_root = original_cache
            achord_engine._bundled_engine_dir = original_bundled
            achord_engine._dev_engine_dir = original_dev


def check_settings_ui():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt5.QtWidgets import QApplication, QGroupBox, QLabel, QPushButton, QScrollArea, QSlider, QWidget
    from src.gui import shezhi_chuangkou
    from src.gui.shezhi_chuangkou import SheZhiChuangKou
    from src.shezhi.config import Config

    class Parent(QWidget):
        def __init__(self):
            super().__init__()
            self.config = Config()
            self.display_apply_count = 0

        def reload_translation_api(self):
            pass

        def apply_display_settings(self):
            self.display_apply_count += 1

    with temporary_profile():
        Config._instance = None
        app = QApplication.instance() or QApplication(sys.argv)
        parent = Parent()
        parent.config.set("translation.api", "achord_builtin")
        parent.config.set("display.source_font_size", 18)
        parent.config.set("display.target_font_size", 20)
        original_get_state = shezhi_chuangkou.get_autostart_state
        original_configure = shezhi_chuangkou.configure_autostart
        shezhi_chuangkou.get_autostart_state = lambda: False
        shezhi_chuangkou.configure_autostart = lambda enabled: None
        try:
            dialog = SheZhiChuangKou(parent)
            base_scroll = dialog.findChild(QScrollArea, "baseSettingsScroll")
            assert base_scroll is not None
            base_layout = base_scroll.widget().layout()
            startup_group = base_layout.itemAt(0).widget()
            assert isinstance(startup_group, QGroupBox)
            assert startup_group.objectName() == "startupGroup"
            assert startup_group.title() == "启动"
            assert not hasattr(dialog, "check_update_button")
            assert not hasattr(dialog, "changelog_button")
            assert not hasattr(dialog, "update_status_label")
            assert "更新" not in [group.title() for group in base_scroll.widget().findChildren(QGroupBox)]
            settings_button_texts = [button.text() for button in base_scroll.widget().findChildren(QPushButton)]
            assert "检测更新" not in settings_button_texts
            assert "查看更新说明" not in settings_button_texts
            dialog.translation_api_combo.setCurrentIndex(dialog.service_index("achord_builtin"))
            dialog._sync_ai_settings_visibility()
            text = " ".join(widget.text() for widget in dialog.findChildren(QLabel))
            assert not dialog.achord_engine_group.isHidden()
            assert dialog.deepl_settings_group.isHidden()
            assert dialog.microsoft_settings_group.isHidden()
            assert dialog.ai_settings_group.isHidden()
            dialog.translation_api_combo.setCurrentIndex(dialog.service_index("microsoft"))
            dialog._sync_ai_settings_visibility()
            assert not dialog.microsoft_settings_group.isHidden()
            assert dialog.achord_engine_group.isHidden()
            assert dialog.service_name_at(dialog.translation_api_combo.currentIndex()) == "microsoft"
            assert "微软翻译" in [dialog.translation_api_combo.itemText(i) for i in range(dialog.translation_api_combo.count())]
            assert "DeepLX Key" not in text
            assert "服务地址" not in text
            assert dialog.source_font_size_spinbox is dialog.source_font_size_spin
            assert dialog.target_font_size_spinbox is dialog.target_font_size_spin
            assert isinstance(dialog.source_font_size_slider, QSlider)
            assert isinstance(dialog.target_font_size_slider, QSlider)
            assert dialog.source_font_size_slider.objectName() == "sourceFontSizeSlider"
            assert dialog.target_font_size_slider.objectName() == "targetFontSizeSlider"
            assert dialog.source_font_size_slider.minimum() == 12
            assert dialog.source_font_size_slider.maximum() == 28
            assert dialog.target_font_size_slider.minimum() == 12
            assert dialog.target_font_size_slider.maximum() == 28
            assert dialog.source_font_size_slider.value() == 18
            assert dialog.target_font_size_slider.value() == 20
            assert dialog.source_font_size_value_label.text() == "18 px"
            assert dialog.target_font_size_value_label.text() == "20 px"
            assert "原文示例：Hello，欢迎使用大佐翻译官" == dialog.source_font_preview.text()
            assert "译文示例：你好，欢迎使用大佐翻译官" == dialog.target_font_preview.text()
            assert dialog.font_preview_card.objectName() == "fontPreviewCard"
            stylesheet = dialog.styleSheet()
            assert "QTabBar::tab" in stylesheet
            assert "min-height: 24px" in stylesheet
            assert "padding: 8px 18px" in stylesheet
            dialog.source_font_size_slider.setValue(19)
            dialog.target_font_size_slider.setValue(22)
            assert dialog.source_font_size_value_label.text() == "19 px"
            assert dialog.target_font_size_value_label.text() == "22 px"
            assert "font-size: 19px" in dialog.source_font_preview.styleSheet()
            assert "font-size: 22px" in dialog.target_font_preview.styleSheet()
            dialog._save_form_to_config()
        finally:
            shezhi_chuangkou.get_autostart_state = original_get_state
            shezhi_chuangkou.configure_autostart = original_configure
        assert parent.config.get("display.source_font_size") == 19
        assert parent.config.get("display.target_font_size") == 22
        assert parent.display_apply_count == 1
        dialog.close()
        parent.close()


def check_text_font_size_settings():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt5.QtWidgets import QApplication, QTextEdit, QWidget
    from src.gui.zhuchuangkou import ZhuChuangKou
    from src.shezhi.config import Config

    with temporary_profile():
        Config._instance = None
        app = QApplication.instance() or QApplication(sys.argv)
        config = Config()
        config.set("display.source_font_size", 10)
        config.set("display.target_font_size", 30)

        class Owner:
            pass

        themed_parent = QWidget()
        themed_parent.setStyleSheet(
            "QTextEdit { font-size: 16px; background-color: #202020; }"
            "QTextEdit[readOnly=\"true\"] { font-size: 16px; }"
        )
        owner = Owner()
        owner.config = config
        owner.input_text = QTextEdit(themed_parent)
        owner.output_text = QTextEdit(themed_parent)
        owner.output_text.setReadOnly(True)
        ZhuChuangKou._apply_text_font_sizes(owner)
        assert owner.input_text.font().pixelSize() == 12
        assert owner.output_text.font().pixelSize() == 28
        assert owner.input_text.document().defaultFont().pixelSize() == 12
        assert owner.output_text.document().defaultFont().pixelSize() == 28
        assert "QTextEdit { font-size: 12px; }" in owner.input_text.styleSheet()
        assert "QTextEdit[readOnly=\"true\"] { font-size: 28px; }" in owner.output_text.styleSheet()
        assert owner.input_text.styleSheet().count("achord-display-font-size:start") == 1

        config.set("display.source_font_size", 21)
        ZhuChuangKou._apply_text_font_sizes(owner)
        assert "QTextEdit { font-size: 21px; }" in owner.input_text.styleSheet()
        assert "QTextEdit { font-size: 12px; }" not in owner.input_text.styleSheet()
        assert owner.input_text.styleSheet().count("achord-display-font-size:start") == 1


def check_mini_window_ui():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt5.QtCore import pyqtSignal
    from PyQt5.QtWidgets import QApplication, QWidget
    from src.gui.mini_chuangkou import MiniChuangKou
    from src.shezhi.config import Config

    class Parent(QWidget):
        theme_changed = pyqtSignal()

        def __init__(self):
            super().__init__()
            self.config = Config()
            self.show_main_calls = 0

        def show_main_window(self):
            self.show_main_calls += 1

    with temporary_profile():
        Config._instance = None
        app = QApplication.instance() or QApplication(sys.argv)
        parent = Parent()
        parent.config.set("theme", "dark")
        parent.config.set("mini_window_opacity", 0.95)
        mini = MiniChuangKou(parent)
        try:
            assert mini.title_label.text() == ""
            assert not mini.title_label.isVisible()
            assert mini.restore_btn.objectName() == "miniRestoreButton"
            assert mini.restore_btn.text() == "↗"
            assert mini.restore_btn.width() >= 28
            assert mini.restore_btn.isEnabled()
            assert not mini.restore_btn.isHidden()
            assert mini.restore_btn.toolTip() == "切换到主窗口"
            assert mini.output_text.font().pixelSize() >= 15
            assert "font-size: 15px" in mini.output_text.styleSheet()
            assert "PingFang" not in mini.output_text.styleSheet()
            assert "border: none" in mini.output_text.styleSheet()
            mini.set_output_text("hello")
            assert mini.output_text.toPlainText() == "hello"
            assert mini.surface.objectName() == "miniSurface"
            assert "border-radius: 12px" in mini.surface.styleSheet()
            assert "background: transparent" in mini.styleSheet()
            assert "border: none" in mini.styleSheet()
            mini.restore_btn.click()
            assert parent.show_main_calls == 1
        finally:
            mini.close()
            parent.close()


def check_about_dialog_theme_ui():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QScrollArea, QWidget
    from src.gui.dialog_utils import get_palette_by_theme
    from src.gui.gengxinrizhi import GengXinRiZhi
    from src.gui.themes import ThemeManager
    from src.gui.title_bar import AboutDialog

    class Parent(QWidget):
        def __init__(self, theme: str):
            super().__init__()
            self.config = {"theme": theme}
            self.update_feedback_owner = None

        def _check_update_with_message(self, feedback_owner=None):
            self.update_feedback_owner = feedback_owner
            feedback_owner.update_status_label.setText("当前已是最新版本")
            feedback_owner.update_status_label.show()

    app = QApplication.instance() or QApplication(sys.argv)
    original_load_avatar = AboutDialog._load_avatar
    AboutDialog._load_avatar = lambda self, url: self._set_placeholder_avatar()
    try:
        for theme in ("light", "pink", "dark"):
            parent = Parent(theme)
            dialog = AboutDialog(parent)
            dialog.resize(dialog.minimumWidth(), dialog.height())
            dialog.show()
            app.processEvents()
            stylesheet = dialog.styleSheet()
            assert "#aboutCloseButton" in stylesheet
            scroll = dialog.findChild(QScrollArea, "aboutScroll")
            viewport = dialog.findChild(QWidget, "aboutViewport")
            card = dialog.findChild(QFrame, "aboutCard")
            sections = dialog.findChildren(QFrame, "aboutSection")
            palette = get_palette_by_theme(theme)
            muted_surface = palette.surface_alt if theme == "dark" else palette.background
            assert scroll is not None
            assert viewport is not None
            assert card is not None
            assert len(sections) == 3
            assert palette.background in viewport.styleSheet()
            assert palette.surface in card.styleSheet()
            assert all(muted_surface in section.styleSheet() for section in sections)
            card.hide()
            app.processEvents()
            viewport_image = viewport.grab().toImage()
            viewport_color = viewport_image.pixelColor(viewport.width() // 2, viewport.height() // 2).name()
            card.show()
            app.processEvents()
            card_image = card.grab().toImage()
            card_color = card_image.pixelColor(card.width() // 2, 8).name()
            assert viewport_color == palette.background.lower()
            assert card_color == palette.surface.lower()
            assert dialog.findChild(QLabel, "aboutVersionBadge") is not None
            header_actions = dialog.findChild(QWidget, "aboutHeaderActions")
            check_update_button = dialog.findChild(QPushButton, "aboutHeaderUpdateButton")
            changelog_button = dialog.findChild(QPushButton, "aboutHeaderChangelogButton")
            update_status = dialog.findChild(QLabel, "updateStatusLabel")
            assert header_actions is not None
            assert check_update_button is not None
            assert changelog_button is not None
            assert update_status is not None
            assert check_update_button.text() == "检测更新"
            assert changelog_button.text() == "更新说明"
            assert header_actions.width() == 112
            assert check_update_button.width() >= check_update_button.minimumSizeHint().width()
            assert changelog_button.width() >= changelog_button.minimumSizeHint().width()
            check_bottom = check_update_button.mapTo(header_actions, check_update_button.rect().bottomLeft()).y()
            changelog_top = changelog_button.mapTo(header_actions, changelog_button.rect().topLeft()).y()
            assert check_bottom < changelog_top
            assert dialog.findChildren(QPushButton, "aboutUpdateButton") == []
            assert scroll.verticalScrollBar().maximum() == 0
            dialog.check_update_button.click()
            assert parent.update_feedback_owner is dialog
            assert update_status.text() == "当前已是最新版本"
            assert update_status.isVisible()
            app.processEvents()
            assert scroll.verticalScrollBar().maximum() == 0
            assert len(dialog.findChildren(QPushButton, "aboutLinkButton")) == 2
            assert dialog.findChild(QPushButton, "aboutCloseButton") is not None
            assert dialog.width() <= 640
            assert dialog.height() <= 680
            assert dialog.contextMenuPolicy() == Qt.NoContextMenu
            for child in dialog.findChildren(QWidget):
                assert child.contextMenuPolicy() == Qt.NoContextMenu
            changelog = GengXinRiZhi(dialog)
            display_names = {"light": "浅色主题", "pink": "粉色主题", "dark": "深色主题"}
            assert changelog.styleSheet() == ThemeManager.get_theme_style(display_names[theme])
            changelog.close()
            dialog.close()
            parent.close()
    finally:
        AboutDialog._load_avatar = original_load_avatar


def check_main_window_redesign_ui():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PyQt5.QtWidgets import QApplication, QFrame, QMainWindow, QPushButton, QWidget
    from src.gui.theme_controller import update_button_icons
    from src.gui.themes import ThemeManager
    from src.gui.zhuchuangkou import ZhuChuangKou
    from src.version import APP_VERSION

    class ConfigStub:
        def __init__(self):
            self._config = {'theme': 'light', 'window': {}}

        def get(self, key, default=None):
            return self._config.get(key, default)

        def set(self, key, value):
            self._config[key] = value

        def save(self):
            return None

    app = QApplication.instance() or QApplication(sys.argv)
    window = ZhuChuangKou.__new__(ZhuChuangKou)
    QMainWindow.__init__(window)
    window.config = ConfigStub()
    window._is_dragging = False
    window._resize_edge = None
    window.is_mini_mode = False

    for name in (
        '_on_source_lang_changed',
        '_on_target_lang_changed',
        '_switch_languages',
        '_retry_connection',
        '_on_theme_change',
        '_toggle_mini_mode',
        '_on_settings',
        '_vm_on_input_text_changed',
        '_load_default_settings',
    ):
        setattr(window, name, lambda *args, **kwargs: None)

    ZhuChuangKou._create_ui(window)
    window.setStyleSheet(ThemeManager.get_theme_style('浅色主题'))
    update_button_icons(window, 'light')
    window.setMinimumSize(969, 684)
    window.resize(969, 684)
    window.show()
    app.processEvents()
    try:
        assert window.biaotilan.title_label.text() == f'大佐翻译官 v{APP_VERSION}'
        assert not hasattr(window.biaotilan, 'theme_btn')
        assert not hasattr(window.biaotilan, 'mini_mode_btn')
        assert not hasattr(window.biaotilan, 'settings_btn')
        toolbar = window.findChild(QFrame, 'translationToolbar')
        toolbar_actions = window.findChild(QWidget, 'toolbarActions')
        service_container = window.findChild(QFrame, 'serviceStatusPill')
        toolbar_buttons = window.findChildren(QPushButton, 'toolbarIconButton')
        assert toolbar is not None
        assert toolbar_actions is not None
        assert service_container is not None
        assert len(window.findChildren(QFrame, 'translationPanel')) == 2
        assert len(toolbar_buttons) == 3
        error_message = '连接失败：需海外网络'
        error_detail = (
            'Google 翻译：无法连接到 Google 翻译。Google 翻译在中国大陆无法直接访问，'
            '请确认已开启可以访问海外网站的网络（代理/VPN），并让本程序走系统代理，'
            '或改用微软翻译或 Achord 内置引擎。'
        ) * 2
        window.service_display.setText('通义千问(Qwen)')
        window.status_indicator.set_status('error', error_message, detail=error_detail)
        app.processEvents()
        assert window.status_indicator.retry_button.isVisible()
        assert window.status_indicator.retry_button.width() <= 60
        assert window.status_indicator.status_label.toolTip() == f"{error_message}\n{error_detail}"
        assert toolbar.layout().minimumSize().width() < window.minimumWidth() - 40
        expected_actions_width = sum(button.width() for button in toolbar_buttons) + 16
        assert toolbar_actions.width() >= expected_actions_width
        service_right = service_container.mapTo(toolbar, service_container.rect().topRight()).x()
        actions_left = toolbar_actions.mapTo(toolbar, toolbar_actions.rect().topLeft()).x()
        assert service_right < actions_left
        for button in toolbar_buttons:
            top_left = button.mapTo(toolbar, button.rect().topLeft())
            assert button.width() == 34 and button.height() >= 34, (
                button.size().width(), button.size().height(),
                toolbar_actions.width(), toolbar_actions.height(),
            )
            assert top_left.x() >= 0
            assert top_left.x() + button.width() <= toolbar.width()
        assert window.translation_workspace_layout.stretch(0) == 1
        assert window.translation_workspace_layout.stretch(1) == 1
        assert abs(window.source_panel.width() - window.target_panel.width()) <= 1

        window.input_text.setPlainText('已安装 App 和 Spark AI')
        window.output_text.setPlainText('App and Spark AI have been installed')
        app.processEvents()
        assert window.clear_source_button.isEnabled()
        assert window.copy_translation_button.isEnabled()
        assert window.output_text._use_header_copy_button
        assert window.output_text.copy_button.isHidden()

        theme_keys = {'浅色主题': 'light', '深色主题': 'dark', '粉色主题': 'pink'}
        for theme_name in ThemeManager.get_theme_names():
            style = ThemeManager.get_theme_style(theme_name)
            assert 'QFrame#translationToolbar' in style
            assert 'QFrame#translationPanel' in style
            assert 'QTextEdit#sourceTextEdit' in style
            assert 'QTextEdit#targetTextEdit' in style
            window.setStyleSheet(style)
            update_button_icons(window, theme_keys[theme_name])
            app.processEvents()
            service_right = service_container.mapTo(toolbar, service_container.rect().topRight()).x()
            actions_left = toolbar_actions.mapTo(toolbar, toolbar_actions.rect().topLeft()).x()
            assert service_right < actions_left
            for button in toolbar_buttons:
                top_left = button.mapTo(toolbar, button.rect().topLeft())
                assert button.width() == 34 and button.height() >= 34
                assert top_left.x() >= 0
                assert top_left.x() + button.width() <= toolbar.width()
    finally:
        window._is_quitting = True
        window.close()


def check_1_2_10_regressions():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "regression_tests_1_2_10.py")],
        check=False,
    )
    assert result.returncode == 0, result.returncode


def check_1_2_11_regressions():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "regression_tests_1_2_11.py")],
        check=False,
    )
    assert result.returncode == 0, result.returncode


def check_package(package_path: Path | None = None):
    from src.version import APP_VERSION
    from tools.verify_windows_package import verify_adjacent_signature, verify_package

    package = package_path or REPO_ROOT / "output" / f"dazuofanyiguan_full.for.windows_{APP_VERSION}.zip"
    if os.environ.get("DZFYQ_SKIP_PACKAGE_CHECK") == "1" and not package.exists():
        return
    if not package.exists():
        raise FileNotFoundError(f"package not found for smoke test: {package}")
    verify_package(package, APP_VERSION)
    verify_adjacent_signature(package, APP_VERSION)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=None)
    args = parser.parse_args()

    checks = [
        check_versions,
        check_first_run_template,
        check_license_notices,
        check_config_migration,
        check_update_manifest_and_script,
        check_update_prompt_waits_for_changelog_modal,
        check_autostart,
        check_autostart_rebuilds_mismatched_shortcut,
        check_autostart_shortcut_validation_tolerates_workdir_drift,
        check_autostart_unknown_does_not_save_false,
        check_legacy_installer_reuses_existing_install_dir,
        check_window_geometry_keeps_recoverable_screen_area,
        lambda: asyncio.run(check_achord_session()),
        check_achord_payload_materialization,
        check_settings_ui,
        check_text_font_size_settings,
        check_mini_window_ui,
        check_about_dialog_theme_ui,
        check_main_window_redesign_ui,
        check_1_2_10_regressions,
        check_1_2_11_regressions,
        lambda: check_package(args.package),
    ]
    for check in checks:
        check()
        print(f"ok {check.__name__ if hasattr(check, '__name__') else 'async_check'}")
    print("smoke tests ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
