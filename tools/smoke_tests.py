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

    assert APP_VERSION == "1.2.5", APP_VERSION
    for relative in ("setup.py", "version.generated.iss", "file_version_info.txt", "src/ziyuan/changelog.md"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "1.2.5" in text, relative
        assert "1.2.6" not in text, relative


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

    with tempfile.TemporaryDirectory(prefix="dzfyq_update_smoke_") as temp:
        root = Path(temp)
        updater = Updater()
        updater.latest_version = "1.2.5"
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
        (root / "update_manifest.json").write_text(json.dumps({"app_version": "1.2.5"}), encoding="utf-8")
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
        lambda: asyncio.run(check_achord_session()),
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
