import asyncio
import copy
import inspect
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


async def check_service_scoped_rate_limits():
    from src.viewmodels.translator_viewmodel import TranslatorViewModel

    fanyi = SimpleNamespace(
        _fanyi_jiekou=None,
        fanyi=AsyncMock(side_effect=ValueError("HTTP 429")),
    )
    vm = TranslatorViewModel(fanyi)
    try:
        await vm._translate_with_rate_limit_retry(
            "x", "auto", "简体中文", 1, False, "google", 1
        )
    except ValueError:
        pass
    assert vm._api_rate_limit_remaining_s("google") > 50
    assert vm._api_rate_limit_remaining_s("deepl") == 0
    assert vm._api_rate_limit_remaining_s("openai_compat") == 0


async def check_ai_second_429_restarts_cooldown():
    from src.viewmodels import translator_viewmodel
    from src.viewmodels.translator_viewmodel import TranslatorViewModel

    fanyi = SimpleNamespace(
        _fanyi_jiekou=None,
        fanyi=AsyncMock(
            side_effect=[ValueError("HTTP 429"), ValueError("HTTP 429")]
        ),
    )
    vm = TranslatorViewModel(fanyi)
    vm._active_token = 1
    vm._ai_rate_limit_cooldown_s = 1.0
    original_sleep = translator_viewmodel.asyncio.sleep
    translator_viewmodel.asyncio.sleep = AsyncMock()
    try:
        try:
            await vm._translate_with_rate_limit_retry(
                "x", "auto", "简体中文", 1, True, "openai_compat", 1
            )
        except ValueError:
            pass
        else:
            raise AssertionError("second AI 429 was not propagated")
    finally:
        translator_viewmodel.asyncio.sleep = original_sleep
    assert fanyi.fanyi.await_count == 2
    assert vm.rate_limit_remaining_s("openai_compat") > 0


def check_packaged_deeplx_allowlist():
    from src.gongju import achord_engine

    with tempfile.TemporaryDirectory(prefix="dzfyq_packaged_allowlist_") as temp:
        root = Path(temp)
        bundled = root / "engines" / "deeplx" / "windows" / "amd64"
        bundled.mkdir(parents=True)
        digest = "a" * 64
        (bundled / "manifest.json").write_text(
            '{"version":"1.2.2","sha256":"' + ("b" * 64) + '"}',
            encoding="utf-8",
        )
        (root / "engines" / "deeplx" / "trusted_releases.json").write_text(
            '{"releases":{"9.9.9":"' + digest + '"}}',
            encoding="utf-8",
        )
        original_bundled = achord_engine._bundled_engine_dir
        original_dev = achord_engine._dev_engine_dir
        original_trusted = achord_engine.TRUSTED_ENGINE_DIGESTS
        achord_engine._bundled_engine_dir = lambda: str(bundled)
        achord_engine._dev_engine_dir = lambda: str(root / "missing" / "windows" / "amd64")
        achord_engine.TRUSTED_ENGINE_DIGESTS = {}
        try:
            assert achord_engine._expected_engine_digest("9.9.9") == digest
        finally:
            achord_engine._bundled_engine_dir = original_bundled
            achord_engine._dev_engine_dir = original_dev
            achord_engine.TRUSTED_ENGINE_DIGESTS = original_trusted


def check_frozen_resource_root_ignores_invalid_meipass():
    from src import main

    with tempfile.TemporaryDirectory(prefix="dzfyq_resource_root_") as temp:
        root = Path(temp)
        app_root = root / "installed"
        resource_dir = app_root / "src" / "ziyuan"
        resource_dir.mkdir(parents=True)
        invalid_meipass = root / "wrong_meipass"
        (invalid_meipass / "PyQt5").mkdir(parents=True)

        original_executable = sys.executable
        original_argv0 = sys.argv[0]
        had_meipass = hasattr(sys, "_MEIPASS")
        original_meipass = getattr(sys, "_MEIPASS", None)
        had_frozen = hasattr(sys, "frozen")
        original_frozen = getattr(sys, "frozen", None)
        had_compiled = "__compiled__" in main.__dict__
        original_compiled = main.__dict__.get("__compiled__")
        try:
            sys.executable = str(app_root / "大佐翻译官.exe")
            sys.argv[0] = sys.executable
            sys._MEIPASS = str(invalid_meipass)
            sys.frozen = False
            main.__dict__["__compiled__"] = True
            assert main._is_packaged_app() is True
            assert Path(main._get_frozen_base_dir()) == app_root
            assert Path(main.get_resource_path("src/ziyuan")) == resource_dir
        finally:
            sys.executable = original_executable
            sys.argv[0] = original_argv0
            if had_meipass:
                sys._MEIPASS = original_meipass
            else:
                delattr(sys, "_MEIPASS")
            if had_frozen:
                sys.frozen = original_frozen
            else:
                delattr(sys, "frozen")
            if had_compiled:
                main.__dict__["__compiled__"] = original_compiled
            else:
                main.__dict__.pop("__compiled__", None)


def check_smoke_requires_package_signature():
    from tools import smoke_tests, verify_windows_package

    calls = []
    original_verify_package = verify_windows_package.verify_package
    original_verify_signature = verify_windows_package.verify_adjacent_signature
    verify_windows_package.verify_package = lambda *_args: calls.append("structure")
    verify_windows_package.verify_adjacent_signature = lambda *_args: calls.append("signature")
    try:
        with tempfile.TemporaryDirectory(prefix="dzfyq_signed_smoke_") as temp:
            package = Path(temp) / "package.zip"
            package.touch()
            smoke_tests.check_package(package)
    finally:
        verify_windows_package.verify_package = original_verify_package
        verify_windows_package.verify_adjacent_signature = original_verify_signature
    assert calls == ["structure", "signature"]

async def check_unapproved_deeplx_release_waits_for_client():
    from src.gongju.achord_engine import (
        AchordEngineRelease,
        AchordEngineUpdater,
    )
    from src.gui import shezhi_chuangkou
    from src.gui.shezhi_chuangkou import SheZhiChuangKou

    release = AchordEngineRelease(
        version="9.9.9",
        tag_name="v9.9.9",
        asset_name="deeplx_windows_amd64.exe",
        download_url="https://example.invalid/deeplx.exe",
        published_at="",
        release_url="",
    )

    class Button:
        def __init__(self):
            self.enabled = None

        def setEnabled(self, enabled):
            self.enabled = bool(enabled)

    updater = AchordEngineUpdater()
    updater.is_release_approved = lambda _release: False
    button = Button()
    statuses = []
    messages = []
    owner = SimpleNamespace(
        achord_engine_updater=updater,
        achord_engine_update_button=button,
        _last_achord_release_approved=True,
        _achord_engine_update_active=False,
        _refresh_achord_engine_status=lambda text: statuses.append(text),
    )
    original_message = shezhi_chuangkou.show_themed_message
    shezhi_chuangkou.show_themed_message = lambda *_args, **kwargs: (
        messages.append(kwargs)
    )
    try:
        SheZhiChuangKou._handle_achord_engine_check_result(
            owner, release, "1.2.2"
        )
    finally:
        shezhi_chuangkou.show_themed_message = original_message
    assert owner._last_achord_release_approved is False
    assert button.enabled is False
    assert statuses[-1] == "发现 v9.9.9 · 等待客户端适配"
    assert messages[-1]["title"] == "发现引擎新版本"
    assert "等待客户端适配" in messages[-1]["text"]

    updater.check_latest = AsyncMock(return_value=release)
    updater.current_engine_info = lambda: SimpleNamespace(version="1.2.2")
    updater.approved_digest = lambda _release: ""
    try:
        await updater.download_latest()
    except RuntimeError as error:
        assert "等待客户端更新" in str(error)
    else:
        raise AssertionError("unapproved DeepLX release was downloadable")

    updater.is_release_approved = lambda _release: True
    approved_button = Button()
    approved_statuses = []
    approved_messages = []
    approved_owner = SimpleNamespace(
        achord_engine_updater=updater,
        achord_engine_update_button=approved_button,
        _last_achord_release_approved=False,
        _achord_engine_update_active=False,
        _refresh_achord_engine_status=lambda text: approved_statuses.append(text),
    )
    shezhi_chuangkou.show_themed_message = lambda *_args, **kwargs: (
        approved_messages.append(kwargs)
    )
    try:
        SheZhiChuangKou._handle_achord_engine_check_result(
            approved_owner, release, "1.2.2"
        )
    finally:
        shezhi_chuangkou.show_themed_message = original_message
    assert approved_owner._last_achord_release_approved is True
    assert approved_button.enabled is True
    assert approved_statuses[-1] == "发现 v9.9.9"
    assert approved_messages[-1]["title"] == "发现引擎更新"


async def check_deeplx_download_mutex_and_ui_state():
    from src.gongju.achord_engine import (
        AchordEngineRelease,
        AchordEngineUpdater,
    )
    from src.gui.shezhi_chuangkou import SheZhiChuangKou

    updater = AchordEngineUpdater()
    check_started = asyncio.Event()
    release_check_blocker = asyncio.Event()

    async def blocked_check_latest():
        check_started.set()
        await release_check_blocker.wait()
        raise AssertionError("blocked release check unexpectedly completed")

    updater.check_latest = blocked_check_latest
    first_download = asyncio.create_task(updater.download_latest())
    await asyncio.wait_for(check_started.wait(), timeout=1)
    assert updater.download_in_progress is True
    second_updater = AchordEngineUpdater()
    assert second_updater.download_in_progress is True
    try:
        await second_updater.download_latest()
    except RuntimeError as error:
        assert "更新正在进行" in str(error)
    else:
        raise AssertionError("second DeepLX download was not rejected")
    finally:
        first_download.cancel()
        try:
            await first_download
        except asyncio.CancelledError:
            pass
    assert updater.download_in_progress is False
    assert "tempfile.mkdtemp" in inspect.getsource(
        AchordEngineUpdater._download_latest_locked
    )

    class Button:
        def __init__(self):
            self.enabled = True

        def setEnabled(self, enabled):
            self.enabled = bool(enabled)

    check_button = Button()
    update_button = Button()
    owner = SimpleNamespace(
        achord_engine_check_button=check_button,
        achord_engine_update_button=update_button,
        achord_engine_updater=SimpleNamespace(
            is_release_approved=lambda _release: True
        ),
        _last_achord_release_approved=True,
        _achord_engine_update_active=False,
        _refresh_achord_engine_status=lambda _text: None,
    )
    SheZhiChuangKou._set_achord_engine_update_active(owner, True)
    assert check_button.enabled is False
    assert update_button.enabled is False

    approved_release = AchordEngineRelease(
        version="9.9.9",
        tag_name="v9.9.9",
        asset_name="deeplx_windows_amd64.exe",
        download_url="https://example.invalid/deeplx.exe",
        published_at="",
        release_url="",
    )
    SheZhiChuangKou._handle_achord_engine_check_result(
        owner, approved_release, "1.2.2"
    )
    assert check_button.enabled is False
    assert update_button.enabled is False

    SheZhiChuangKou._set_achord_engine_update_active(owner, False)
    assert check_button.enabled is True
    assert update_button.enabled is True

async def check_same_service_config_rollback():
    from src.gui import translator_controller

    class Config:
        def __init__(self):
            self.values = {
                "translation.api": "openai_compat",
                "openai_compat.vendor": "OpenAI",
                "openai_compat.base_url": "https://bad.invalid/v1",
                "openai_compat.model": "bad-model",
                "openai_compat.api_key": "bad-key",
                "openai_compat.profiles": {
                    "OpenAI": {"api_key": "bad-key"},
                    "Other": {"api_key": "keep-other"},
                },
                "deepl.api_key": "",
                "deepl.account_type": "",
            }

        def get(self, key, default=None):
            return self.values.get(key, default)

        def update_many(self, values):
            self.values.update(copy.deepcopy(values))
            return True

    config = Config()
    working = {
        "translation.api": "openai_compat",
        "openai_compat.vendor": "OpenAI",
        "openai_compat.base_url": "https://api.openai.com/v1",
        "openai_compat.model": "gpt-4o-mini",
        "openai_compat.api_key": "working-key",
        "openai_compat.profiles": {
            "OpenAI": {
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
                "api_key": "working-key",
            }
        },
    }
    statuses = []
    owner = SimpleNamespace(
        config=config,
        _last_working_translation_configs={"openai_compat": working},
        translator_vm=SimpleNamespace(cancel_and_wait=AsyncMock()),
        status_indicator=SimpleNamespace(
            set_status=lambda *args: statuses.append(args)
        ),
        input_text=SimpleNamespace(toPlainText=lambda: ""),
        tishi=SimpleNamespace(showMessage=lambda *_args, **_kwargs: None),
        fanyi=SimpleNamespace(
            current_api_name="openai_compat",
            close_current_api=AsyncMock(),
        ),
        service_display=SimpleNamespace(setText=lambda _text: None),
    )
    candidate = SimpleNamespace(
        health_check=AsyncMock(side_effect=RuntimeError("probe failed")),
        close=AsyncMock(),
    )
    original_factory = translator_controller.build_translation_api
    translator_controller.build_translation_api = lambda _config: candidate
    try:
        await translator_controller._init_translation_api(owner)
    finally:
        translator_controller.build_translation_api = original_factory
    assert config.get("openai_compat.api_key") == "working-key"
    assert config.get("openai_compat.model") == "gpt-4o-mini"
    assert config.get("openai_compat.profiles")["Other"]["api_key"] == "keep-other"
    assert config.get("openai_compat.profiles")["OpenAI"]["api_key"] == "working-key"
    assert statuses[-1] == ("normal", "已连接")


async def check_unverified_config_does_not_pollute_snapshot():
    from src.gui import translator_controller

    class Config:
        def __init__(self):
            self.values = {
                "translation.api": "google",
                "translation.last_working_configs": {},
                "openai_compat.vendor": "OpenAI",
                "openai_compat.base_url": "https://bad.invalid/v1",
                "openai_compat.model": "bad-model",
                "openai_compat.api_key": "unverified-bad-key",
                "openai_compat.profiles": {
                    "OpenAI": {"api_key": "unverified-bad-key"}
                },
            }

        def get(self, key, default=None):
            return self.values.get(key, default)

        def update_many(self, values):
            self.values.update(copy.deepcopy(values))
            return True

    old_ai_snapshot = {
        "translation.api": "openai_compat",
        "openai_compat.vendor": "OpenAI",
        "openai_compat.base_url": "https://api.openai.com/v1",
        "openai_compat.model": "gpt-4o-mini",
        "openai_compat.api_key": "verified-key",
        "openai_compat.profiles": {
            "OpenAI": {
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
                "api_key": "verified-key",
            }
        },
    }
    config = Config()
    owner = SimpleNamespace(
        config=config,
        _last_working_translation_configs={
            "openai_compat": copy.deepcopy(old_ai_snapshot)
        },
        translator_vm=SimpleNamespace(cancel_and_wait=AsyncMock()),
        status_indicator=SimpleNamespace(set_status=lambda *_args: None),
        input_text=SimpleNamespace(toPlainText=lambda: ""),
        fanyi=SimpleNamespace(
            current_api_name="google",
            replace_fanyi_jiekou=AsyncMock(),
        ),
        service_display=SimpleNamespace(setText=lambda _text: None),
    )
    candidate = SimpleNamespace(health_check=AsyncMock(), close=AsyncMock())
    original_factory = translator_controller.build_translation_api
    translator_controller.build_translation_api = lambda _config: candidate
    try:
        await translator_controller._init_translation_api(owner)
    finally:
        translator_controller.build_translation_api = original_factory
    assert owner._last_working_translation_configs["openai_compat"] == old_ai_snapshot
    assert owner._last_working_translation_configs["google"] == {
        "translation.api": "google"
    }
    persisted = config.get("translation.last_working_configs")
    assert persisted["openai_compat"] == old_ai_snapshot
    assert persisted["google"] == {"translation.api": "google"}


async def check_cold_start_restores_failed_service_config():
    from src.gui import translator_controller

    verified_ai = {
        "translation.api": "openai_compat",
        "openai_compat.vendor": "OpenAI",
        "openai_compat.base_url": "https://api.openai.com/v1",
        "openai_compat.model": "gpt-4o-mini",
        "openai_compat.api_key": "verified-key",
        "openai_compat.profiles": {
            "OpenAI": {
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
                "api_key": "verified-key",
            }
        },
    }

    class Config:
        def __init__(self):
            self.values = {
                "translation.api": "google",
                "translation.last_working_configs": {},
                "openai_compat.vendor": "OpenAI",
                "openai_compat.base_url": "https://api.openai.com/v1",
                "openai_compat.model": "gpt-4o-mini",
                "openai_compat.api_key": "verified-key",
                "openai_compat.profiles": {
                    "OpenAI": {
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4o-mini",
                        "api_key": "verified-key",
                    },
                    "Other": {"api_key": "keep-other"},
                },
            }

        def get(self, key, default=None):
            return self.values.get(key, default)

        def update_many(self, values):
            self.values.update(copy.deepcopy(values))
            return True

    config = Config()
    rollback_configs = translator_controller.ensure_translation_rollback_snapshot(
        config, "openai_compat"
    )
    assert rollback_configs["openai_compat"] == verified_ai
    config.update_many(
        {
            "translation.api": "openai_compat",
            "translation.last_working_configs": rollback_configs,
            "openai_compat.base_url": "https://bad.invalid/v1",
            "openai_compat.model": "bad-model",
            "openai_compat.api_key": "bad-key",
            "openai_compat.profiles": {
                "OpenAI": {"api_key": "bad-key"},
                "Other": {"api_key": "keep-other"},
            },
        }
    )

    statuses = []
    owner = SimpleNamespace(
        config=config,
        translator_vm=SimpleNamespace(cancel_and_wait=AsyncMock()),
        status_indicator=SimpleNamespace(
            set_status=lambda *args: statuses.append(args)
        ),
        input_text=SimpleNamespace(toPlainText=lambda: ""),
        tishi=SimpleNamespace(showMessage=lambda *_args, **_kwargs: None),
        fanyi=SimpleNamespace(
            current_api_name="google",
            close_current_api=AsyncMock(),
        ),
        service_display=SimpleNamespace(setText=lambda _text: None),
    )
    candidate = SimpleNamespace(
        health_check=AsyncMock(side_effect=RuntimeError("probe failed")),
        close=AsyncMock(),
    )
    original_factory = translator_controller.build_translation_api
    translator_controller.build_translation_api = lambda _config: candidate
    try:
        await translator_controller._init_translation_api(owner)
    finally:
        translator_controller.build_translation_api = original_factory
    assert config.get("translation.api") == "google"
    assert config.get("openai_compat.api_key") == "verified-key"
    assert config.get("openai_compat.model") == "gpt-4o-mini"
    assert config.get("openai_compat.profiles")["Other"]["api_key"] == "keep-other"
    assert config.get("translation.last_working_configs")["openai_compat"] == verified_ai
    assert statuses[-1] == ("normal", "已连接")


def check_force_update_after_authentication():
    from src.gongju import update as update_module

    with tempfile.TemporaryDirectory(prefix="dzfyq_force_auth_") as temp:
        root = Path(temp)
        package = root / "package.zip"
        package.write_bytes(b"signed-package-placeholder")
        old_home = os.environ.get("DZFYQ_HOME")
        os.environ["DZFYQ_HOME"] = str(root / "home")
        original_verify = update_module.verify_package_authenticity
        update_module.verify_package_authenticity = lambda **_kwargs: {}
        try:
            updater = update_module.Updater()
            updater.latest_version = "1.2.10"
            updater.release_signature = "signature"
            updater.expected_asset_name = "dazuofanyiguan_full.for.windows_1.2.10.zip"
            updater._force_update_requested = True
            assert updater.force_update is False
            updater._verify_downloaded_package(str(package))
            assert updater.force_update is True
        finally:
            update_module.verify_package_authenticity = original_verify
            if old_home is None:
                os.environ.pop("DZFYQ_HOME", None)
            else:
                os.environ["DZFYQ_HOME"] = old_home


def check_pending_update_start_guard():
    from src.gongju.update import Updater, should_defer_start_for_pending_update

    with tempfile.TemporaryDirectory(prefix="dzfyq_pending_guard_") as temp:
        root = Path(temp)
        old_home = os.environ.get("DZFYQ_HOME")
        os.environ["DZFYQ_HOME"] = str(root)
        try:
            updater = Updater()
            pending = Path(updater._pending_update_path())
            pending.write_text('{"expected_version":"1.3.0"}', encoding="utf-8")
            assert should_defer_start_for_pending_update("1.2.10") is True
            assert should_defer_start_for_pending_update(
                "1.2.10", update_restart=True
            ) is False
            old_time = time.time() - 700
            os.utime(pending, (old_time, old_time))
            assert should_defer_start_for_pending_update("1.2.10") is False

            script = root / "apply_update.ps1"
            updater._write_apply_script(str(script))
            script_text = script.read_text(encoding="utf-8-sig")
            assert script_text.count('--update-restart') == 2
        finally:
            if old_home is None:
                os.environ.pop("DZFYQ_HOME", None)
            else:
                os.environ["DZFYQ_HOME"] = old_home


async def check_partial_prepare_always_restores():
    from src.gui.update_controller import UpdateCoordinator

    coordinator = object.__new__(UpdateCoordinator)
    coordinator.owner = SimpleNamespace()
    coordinator.updater = SimpleNamespace(install_update=lambda _path: None)
    restore_calls = []
    error_calls = []

    async def prepare():
        raise RuntimeError("close timed out")

    async def restore():
        restore_calls.append(True)

    coordinator._prepare_owner_for_update = prepare
    coordinator._restore_owner_after_failed_update = restore
    coordinator.on_update_error = lambda error: error_calls.append(error)
    await coordinator._install_windows_update("unused.zip")
    assert len(restore_calls) == 1
    assert len(error_calls) == 1


async def check_force_update_request_auto_downloads():
    from src.gui.update_controller import UpdateCoordinator

    coordinator = object.__new__(UpdateCoordinator)
    coordinator._modal_dialog_active = False
    coordinator._pending_update_prompt = None
    coordinator._update_operation_active = False
    coordinator.updater = SimpleNamespace(
        force_update_requested=True,
        download_in_progress=False,
        download_update=AsyncMock(),
    )
    progress_events = []
    prompt_events = []
    coordinator._ensure_progress_dialog = lambda: progress_events.append(True)
    coordinator._show_update_prompt = lambda *args: prompt_events.append(args)
    coordinator.on_update_available("9.9.9", "notes", False)
    coordinator.on_update_available("9.9.9", "notes", False)
    await asyncio.sleep(0)
    assert progress_events == [True]
    assert prompt_events == []
    coordinator.updater.download_update.assert_awaited_once()


async def check_update_download_mutex_preserves_metadata():
    from src.gongju.update import Updater

    with tempfile.TemporaryDirectory(prefix="dzfyq_update_mutex_") as temp:
        old_home = os.environ.get("DZFYQ_HOME")
        os.environ["DZFYQ_HOME"] = temp
        try:
            updater = Updater()
            updater.release_signature = "keep-signature"
            updater.expected_asset_name = "keep-package.zip"
            updater.latest_version = "9.9.9"
            updater._download_in_progress = True
            assert await updater.check_update() is False
            assert updater.release_signature == "keep-signature"
            assert updater.expected_asset_name == "keep-package.zip"
            assert updater.latest_version == "9.9.9"
            await updater.download_update()
            assert updater._download_in_progress is True
        finally:
            if old_home is None:
                os.environ.pop("DZFYQ_HOME", None)
            else:
                os.environ["DZFYQ_HOME"] = old_home


def check_popen_failure_clears_pending():
    from src.gongju import update as update_module

    with tempfile.TemporaryDirectory(prefix="dzfyq_popen_failure_") as temp:
        root = Path(temp)
        package = root / "package.zip"
        package.write_bytes(b"placeholder")
        source_dir = root / "source"
        source_dir.mkdir()
        old_home = os.environ.get("DZFYQ_HOME")
        os.environ["DZFYQ_HOME"] = str(root / "home")
        original_popen = update_module.subprocess.Popen
        try:
            updater = update_module.Updater()
            updater.latest_version = "1.3.0"
            updater._is_frozen_app = lambda: True
            updater._ensure_target_writable = lambda _path: None
            updater._prepare_full_update_source = lambda _path: (
                str(source_dir),
                "app.exe",
            )
            updater._ensure_safe_replace_paths = lambda *_args: None
            updater._write_apply_script = lambda path: Path(path).write_text(
                "placeholder", encoding="utf-8"
            )
            update_module.subprocess.Popen = Mock(
                side_effect=OSError("powershell unavailable")
            )
            try:
                updater._apply_windows_full_update(str(package))
            except OSError:
                pass
            else:
                raise AssertionError("Popen failure was not propagated")
            assert not Path(updater._pending_update_path()).exists()
        finally:
            update_module.subprocess.Popen = original_popen
            if old_home is None:
                os.environ.pop("DZFYQ_HOME", None)
            else:
                os.environ["DZFYQ_HOME"] = old_home


async def check_mini_window_uses_shared_cooldown():
    from src.gui.window_mode_controller import WindowModeController
    from src.viewmodels.translator_viewmodel import TranslatorViewModel

    class MiniWindow:
        DEFAULT_WIDTH = 320
        DEFAULT_HEIGHT = 180

        def __init__(self):
            self.output_text = SimpleNamespace(clear=lambda: None)
            self.messages = []

        def resize(self, *_args):
            pass

        def show_at_cursor(self):
            pass

        def start_loading(self):
            pass

        def stop_loading(self):
            pass

        def set_output_text(self, text):
            self.messages.append(text)

        def _adjust_window_size_for_text(self, _text):
            pass

    def build_controller(service, vm):
        main_window = SimpleNamespace(
            mini_window=MiniWindow(),
            fanyi=service,
            translator_vm=vm,
            target_lang_combo=SimpleNamespace(currentText=lambda: "简体中文"),
        )
        return WindowModeController(main_window)

    blocked_service = SimpleNamespace(
        _fanyi_jiekou=None,
        fanyi=AsyncMock(return_value=("unused", None)),
    )
    blocked_vm = TranslatorViewModel(blocked_service)
    blocked_vm.note_service_rate_limit_error("google", ValueError("HTTP 429"))
    blocked = build_controller(blocked_service, blocked_vm)
    await blocked.translate_and_show_mini(
        "x", api_name="google", api_generation=1
    )
    blocked_service.fanyi.assert_not_awaited()

    limited_service = SimpleNamespace(
        _fanyi_jiekou=None,
        fanyi=AsyncMock(side_effect=ValueError("HTTP 429")),
    )
    limited_vm = TranslatorViewModel(limited_service)
    limited = build_controller(limited_service, limited_vm)
    await limited.translate_and_show_mini(
        "x", api_name="google", api_generation=1
    )
    assert limited_vm.rate_limit_remaining_s("google") > 50


def check_legacy_mini_translation_paths_removed():
    main_source = (REPO_ROOT / "src/gui/zhuchuangkou.py").read_text(
        encoding="utf-8"
    )
    mini_source = (REPO_ROOT / "src/gui/mini_chuangkou.py").read_text(
        encoding="utf-8"
    )
    assert "_handle_mini_text_changed" not in main_source
    assert "async def translate_text" not in mini_source
    assert "self._parent.fanyi.fanyi" not in mini_source


def check_macos_signing_documented():
    text = (REPO_ROOT / "PACKAGING_AND_UPDATE.md").read_text(encoding="utf-8")
    assert "DZFYQ-SIG-MACOS" in text
    assert "tools/verify_update_signature.py" in text
    assert "signature-ok" in text
    assert "--platform macos" in text
    assert "--package-type macos_dmg_update" in text


async def main():
    await check_service_scoped_rate_limits()
    print("ok service_scoped_rate_limits")
    await check_ai_second_429_restarts_cooldown()
    print("ok ai_second_429_restarts_cooldown")
    check_packaged_deeplx_allowlist()
    print("ok packaged_deeplx_allowlist")
    check_frozen_resource_root_ignores_invalid_meipass()
    print("ok frozen_resource_root_ignores_invalid_meipass")
    check_smoke_requires_package_signature()
    print("ok smoke_requires_package_signature")
    await check_unapproved_deeplx_release_waits_for_client()
    print("ok unapproved_deeplx_release_waits_for_client")
    await check_deeplx_download_mutex_and_ui_state()
    print("ok deeplx_download_mutex_and_ui_state")
    await check_same_service_config_rollback()
    print("ok same_service_config_rollback")
    await check_unverified_config_does_not_pollute_snapshot()
    print("ok unverified_config_does_not_pollute_snapshot")
    await check_cold_start_restores_failed_service_config()
    print("ok cold_start_restores_failed_service_config")
    check_force_update_after_authentication()
    print("ok force_update_after_authentication")
    await check_force_update_request_auto_downloads()
    print("ok force_update_request_auto_downloads")
    await check_update_download_mutex_preserves_metadata()
    print("ok update_download_mutex_preserves_metadata")
    check_pending_update_start_guard()
    print("ok pending_update_start_guard")
    check_popen_failure_clears_pending()
    print("ok popen_failure_clears_pending")
    await check_mini_window_uses_shared_cooldown()
    print("ok mini_window_uses_shared_cooldown")
    await check_partial_prepare_always_restores()
    print("ok partial_prepare_always_restores")
    check_legacy_mini_translation_paths_removed()
    print("ok legacy_mini_translation_paths_removed")
    check_macos_signing_documented()
    print("ok macos_signing_documented")


if __name__ == "__main__":
    asyncio.run(main())
