import asyncio
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

    assert APP_VERSION == "1.2.6", APP_VERSION
    for relative in ("setup.py", "version.generated.iss", "file_version_info.txt", "src/ziyuan/changelog.md"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "1.2.6" in text, relative


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


def check_update_manifest_and_script():
    from src.gongju.update import Updater
    from src.version import APP_VERSION

    with tempfile.TemporaryDirectory(prefix="dzfyq_update_smoke_") as temp:
        root = Path(temp)
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
    from PyQt5.QtWidgets import QApplication, QLabel, QWidget
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
        parent.config.set("translation.api", "achord_builtin")
        dialog = SheZhiChuangKou(parent)
        dialog.translation_api_combo.setCurrentIndex(2)
        dialog._sync_ai_settings_visibility()
        text = " ".join(widget.text() for widget in dialog.findChildren(QLabel))
        assert not dialog.achord_engine_group.isHidden()
        assert dialog.deepl_settings_group.isHidden()
        assert dialog.ai_settings_group.isHidden()
        assert "DeepLX Key" not in text
        assert "服务地址" not in text
        dialog.close()
        parent.close()


def check_package(package_path: Path | None = None):
    from src.version import APP_VERSION
    from tools.verify_windows_package import verify_package

    package = package_path or REPO_ROOT / "output" / f"dazuofanyiguan_full.for.windows_{APP_VERSION}.zip"
    if os.environ.get("DZFYQ_SKIP_PACKAGE_CHECK") == "1" and not package.exists():
        return
    if not package.exists():
        raise FileNotFoundError(f"package not found for smoke test: {package}")
    verify_package(package, APP_VERSION)


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
        check_autostart,
        check_autostart_unknown_does_not_save_false,
        check_legacy_installer_reuses_existing_install_dir,
        check_window_geometry_keeps_recoverable_screen_area,
        lambda: asyncio.run(check_achord_session()),
        check_achord_payload_materialization,
        check_settings_ui,
        lambda: check_package(args.package),
    ]
    for check in checks:
        check()
        print(f"ok {check.__name__ if hasattr(check, '__name__') else 'async_check'}")
    print("smoke tests ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
