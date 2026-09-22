from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import subprocess
import time
import sys
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _write_full_package(path: Path, version: str, files: dict[str, bytes]) -> None:
    payload = dict(files)
    payload["update_manifest.json"] = (
        json.dumps(
            {
                "app_version": version,
                "package_type": "windows_full_update",
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(payload.items()):
            archive.writestr(name, content)


def _extract_install_layout(package: Path, target: Path) -> None:
    with zipfile.ZipFile(package) as archive:
        archive.extractall(target)
    payload = target / "engines" / "deeplx" / "windows" / "amd64" / "deeplx.exe.payload"
    if payload.is_file():
        executable = payload.with_suffix("")
        executable.write_bytes(payload.read_bytes())
        payload.unlink()


def _zip_files(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {
            info.filename: archive.read(info)
            for info in archive.infolist()
            if not info.is_dir()
        }


def check_delta_generation_and_reconstruction() -> None:
    from src.gongju.update_delta import (
        DeltaPackageError,
        inspect_delta_package,
        reconstruct_delta_package,
    )
    from tools.create_windows_delta_package import (
        create_delta_package,
        expected_delta_name,
    )

    with tempfile.TemporaryDirectory(prefix="dzfyq_delta_rebuild_") as temp:
        root = Path(temp)
        base = root / "base.zip"
        target = root / "target.zip"
        engine = b"engine-payload-v1"
        _write_full_package(
            base,
            "1.2.10",
            {
                "大佐翻译官.exe": b"app-v1",
                "src/ziyuan/logo.ico": b"icon",
                "keep.txt": b"same",
                "remove.txt": b"remove-me",
                "engines/deeplx/windows/amd64/deeplx.exe.payload": engine,
            },
        )
        _write_full_package(
            target,
            "1.2.11",
            {
                "大佐翻译官.exe": b"app-v2",
                "src/ziyuan/logo.ico": b"icon",
                "keep.txt": b"same",
                "added.txt": b"new",
                "engines/deeplx/windows/amd64/deeplx.exe.payload": engine,
            },
        )
        delta = root / expected_delta_name("1.2.10", "1.2.11")
        create_delta_package(base, target, delta)
        manifest = inspect_delta_package(
            delta,
            expected_base_version="1.2.10",
            expected_target_version="1.2.11",
            verify_payload_hashes=True,
        )
        changed = {record.path for record in manifest.payload_files}
        assert "大佐翻译官.exe" in changed
        assert "added.txt" in changed
        assert "update_manifest.json" in changed
        assert "keep.txt" not in changed
        assert "remove.txt" in manifest.removed_files

        install = root / "install"
        rebuilt = root / "rebuilt"
        _extract_install_layout(base, install)
        reconstruct_delta_package(
            delta,
            install_dir=install,
            output_dir=rebuilt,
            expected_base_version="1.2.10",
            expected_target_version="1.2.11",
        )
        target_files = _zip_files(target)
        rebuilt_files = {
            path.relative_to(rebuilt).as_posix(): path.read_bytes()
            for path in rebuilt.rglob("*")
            if path.is_file()
        }
        assert rebuilt_files == target_files

        (install / "keep.txt").write_bytes(b"modified")
        try:
            reconstruct_delta_package(
                delta,
                install_dir=install,
                output_dir=rebuilt,
                expected_base_version="1.2.10",
                expected_target_version="1.2.11",
            )
        except DeltaPackageError as error:
            assert "已被修改" in str(error)
        else:
            raise AssertionError("modified installed file was accepted")

        # 文件在“哈希通过”与“复制”之间被改动（TOCTOU）：复制出的字节必须再次校验
        (install / "keep.txt").write_bytes(b"same")
        from src.gongju import update_delta as update_delta_module

        original_finder = update_delta_module._find_matching_source

        def racing_finder(install_dir, record):
            source = original_finder(install_dir, record)
            if record.path == "keep.txt":
                source.write_bytes(b"swapped-after-hash")
            return source

        update_delta_module._find_matching_source = racing_finder
        try:
            try:
                reconstruct_delta_package(
                    delta,
                    install_dir=install,
                    output_dir=rebuilt,
                    expected_base_version="1.2.10",
                    expected_target_version="1.2.11",
                )
            except DeltaPackageError as error:
                assert "重建过程中发生变化" in str(error), str(error)
            else:
                raise AssertionError("file swapped after hashing was accepted")
            assert not rebuilt.exists() or not any(rebuilt.rglob("*"))
        finally:
            update_delta_module._find_matching_source = original_finder


def check_delta_case_only_rename_is_not_recorded_as_removal() -> None:
    """仅大小写变化的文件名不能同时出现在 removed_files 与 target_files 中。"""
    from src.gongju.update_delta import inspect_delta_package, reconstruct_delta_package
    from tools.create_windows_delta_package import create_delta_package, expected_delta_name

    with tempfile.TemporaryDirectory(prefix="dzfyq_delta_case_") as temp:
        root = Path(temp)
        base = root / "base.zip"
        target = root / "target.zip"
        _write_full_package(
            base,
            "1.2.10",
            {"大佐翻译官.exe": b"app-v1", "Assets/Logo.ico": b"icon", "keep.txt": b"same"},
        )
        _write_full_package(
            target,
            "1.2.11",
            {"大佐翻译官.exe": b"app-v2", "Assets/logo.ico": b"icon", "keep.txt": b"same"},
        )
        delta = root / expected_delta_name("1.2.10", "1.2.11")
        create_delta_package(base, target, delta)
        manifest = inspect_delta_package(
            delta,
            expected_base_version="1.2.10",
            expected_target_version="1.2.11",
            verify_payload_hashes=True,
        )
        assert manifest.removed_files == (), manifest.removed_files
        payload_paths = {record.path for record in manifest.payload_files}
        assert "Assets/logo.ico" in payload_paths, payload_paths
        assert {record.path for record in manifest.target_files} == {
            "大佐翻译官.exe",
            "Assets/logo.ico",
            "keep.txt",
            "update_manifest.json",
        }

        install = root / "install"
        rebuilt = root / "rebuilt"
        _extract_install_layout(base, install)
        reconstruct_delta_package(
            delta,
            install_dir=install,
            output_dir=rebuilt,
            expected_base_version="1.2.10",
            expected_target_version="1.2.11",
        )
        rebuilt_files = {
            path.relative_to(rebuilt).as_posix(): path.read_bytes()
            for path in rebuilt.rglob("*")
            if path.is_file()
        }
        assert rebuilt_files == _zip_files(target), sorted(rebuilt_files)


def check_delta_manifest_rejects_unsafe_paths() -> None:
    from src.gongju.update_delta import DeltaPackageError, inspect_delta_package

    with tempfile.TemporaryDirectory(prefix="dzfyq_delta_unsafe_") as temp:
        package = Path(temp) / "unsafe.zip"
        manifest = {
            "schema_version": 1,
            "package_type": "windows_file_delta",
            "platform": "windows",
            "base_version": "1.2.10",
            "app_version": "1.2.11",
            "created_at": "",
            "payload_files": [
                {"path": "../escape.txt", "size_bytes": 1, "sha256": "0" * 64}
            ],
            "removed_files": [],
            "target_files": [
                {"path": "../escape.txt", "size_bytes": 1, "sha256": "0" * 64}
            ],
        }
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("delta_manifest.json", json.dumps(manifest))
            archive.writestr("payload/../escape.txt", b"x")
        try:
            inspect_delta_package(package)
        except DeltaPackageError:
            pass
        else:
            raise AssertionError("unsafe delta path was accepted")


class _FakeContent:
    def __init__(self, payload: bytes):
        self.payload = payload

    async def iter_chunked(self, _size):
        yield self.payload


class _FakeResponse:
    def __init__(self, *, status=200, json_payload=None, body=b"", headers=None):
        self.status = status
        self._json_payload = json_payload
        self._body = body
        self.headers = headers or {}
        self.content = _FakeContent(body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        return self._json_payload

    async def read(self):
        return self._body


class _FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.get_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        try:
            return self.responses[url]
        except KeyError as error:
            raise ConnectionError(f"unreachable: {url}") from error


async def check_delta_asset_selection_and_threshold() -> None:
    from src.gongju import update as update_module
    from src.gongju.update import Updater

    old_platform = update_module.sys.platform
    old_session = update_module.aiohttp.ClientSession
    try:
        update_module.sys.platform = "win32"
        updater = Updater()
        updater.current_version = "1.2.11"
        api_url = updater.github_api
        full_name = "dazuofanyiguan_full.for.windows_1.2.12.zip"
        delta_name = "dazuofanyiguan_delta.for.windows_1.2.11_to_1.2.12.zip"
        full_signature = "A" * 88
        full_sig = {
            "filename": full_name,
            "app_version": "1.2.12",
            "package_type": "windows_full_update",
            "platform": "windows",
            "size_bytes": 1000,
            "sha256": "a" * 64,
            "signature": full_signature,
        }
        delta_sig = {
            "filename": delta_name,
            "app_version": "1.2.12",
            "package_type": "windows_file_delta",
            "platform": "windows",
            "size_bytes": 700,
            "sha256": "b" * 64,
            "signature": "B" * 88,
        }
        release = {
            "tag_name": "v1.2.12",
            "body": f"DZFYQ-SIG-WINDOWS:{full_signature}",
            "assets": [
                {"name": full_name, "size": 1000, "browser_download_url": "full"},
                {
                    "name": f"{full_name}.sig.json",
                    "size": 500,
                    "browser_download_url": "full-sig",
                },
                {"name": delta_name, "size": 700, "browser_download_url": "delta"},
                {
                    "name": f"{delta_name}.sig.json",
                    "size": 500,
                    "browser_download_url": "delta-sig",
                },
            ],
        }
        responses = {
            api_url: _FakeResponse(json_payload=release),
            "full-sig": _FakeResponse(body=json.dumps(full_sig).encode()),
            "delta-sig": _FakeResponse(body=json.dumps(delta_sig).encode()),
        }
        update_module.aiohttp.ClientSession = lambda **kwargs: _FakeSession(responses)
        assert await updater.check_update() is True
        assert updater.active_update_source.name == "GitHub"
        assert updater.selected_package_type == "windows_file_delta"
        assert updater.expected_asset_name == delta_name
        assert updater._fallback_full_asset.name == full_name

        release["assets"][2]["size"] = 850
        delta_sig["size_bytes"] = 850
        responses["delta-sig"] = _FakeResponse(body=json.dumps(delta_sig).encode())
        assert await updater.check_update() is True
        assert updater.selected_package_type == "windows_full_update"
        assert updater.expected_asset_name == full_name
    finally:
        update_module.aiohttp.ClientSession = old_session
        update_module.sys.platform = old_platform


async def check_update_source_falls_back_to_gitee() -> None:
    """GitHub 不可用/无 Release 时回退到 Gitee；两者都不可用时给出合并后的错误。"""
    from src.gongju import update as update_module
    from src.gongju.update import Updater

    old_platform = update_module.sys.platform
    old_session = update_module.aiohttp.ClientSession
    try:
        update_module.sys.platform = "win32"
        updater = Updater()
        updater.current_version = "1.2.11"
        assert [source.name for source in updater.update_sources] == ["GitHub", "Gitee"]
        assert "api.github.com/repos/Achordchan/dazuo-win" in updater.github_api
        assert "gitee.com/api/v5/repos/Achordchan/dazuofanyiguan" in updater.gitee_api

        full_name = "dazuofanyiguan_full.for.windows_1.2.12.zip"
        signature = "C" * 88
        release = {
            "tag_name": "v1.2.12",
            "body": f"DZFYQ-SIG-WINDOWS:{signature}",
            "assets": [{"name": full_name, "size": 1000, "browser_download_url": "full"}],
        }
        # GitHub 404（尚未发布 Release）→ 回退 Gitee
        responses = {
            updater.github_api: _FakeResponse(status=404, json_payload={"message": "Not Found"}),
            updater.gitee_api: _FakeResponse(json_payload=release),
        }
        update_module.aiohttp.ClientSession = lambda **kwargs: _FakeSession(responses)
        assert await updater.check_update() is True
        assert updater.active_update_source.name == "Gitee"
        assert updater.expected_asset_name == full_name

        # GitHub 网络不可达（无响应条目）→ 回退 Gitee
        responses = {updater.gitee_api: _FakeResponse(json_payload=release)}
        update_module.aiohttp.ClientSession = lambda **kwargs: _FakeSession(responses)
        assert await updater.check_update() is True
        assert updater.active_update_source.name == "Gitee"

        # 两个源都失败 → 报错信息包含两个源
        errors = []
        updater.update_error.connect(errors.append)
        responses = {
            updater.github_api: _FakeResponse(status=403, json_payload={}),
            updater.gitee_api: _FakeResponse(status=404, json_payload={}),
        }
        update_module.aiohttp.ClientSession = lambda **kwargs: _FakeSession(responses)
        assert await updater.check_update() is False
        assert errors and "GitHub" in errors[-1] and "Gitee" in errors[-1], errors
        assert updater.active_update_source is None
    finally:
        update_module.aiohttp.ClientSession = old_session
        update_module.sys.platform = old_platform


async def check_asset_download_falls_back_to_mirror_source() -> None:
    """GitHub API 可达但资源域名被阻断时，包与签名文件改从 Gitee 同版本 Release 下载。"""
    from src.gongju import update as update_module
    from src.gongju.update import UpdateAsset, Updater

    with tempfile.TemporaryDirectory(prefix="dzfyq_mirror_dl_") as temp:
        old_home = os.environ.get("DZFYQ_HOME")
        os.environ["DZFYQ_HOME"] = temp
        try:
            updater = Updater()
            updater.latest_version = "1.2.12"
            updater.active_update_source = updater.update_sources[0]
            full_name = "dazuofanyiguan_full.for.windows_1.2.12.zip"
            payload = b"hello"
            sig_payload = {
                "filename": full_name,
                "app_version": "1.2.12",
                "package_type": "windows_full_update",
                "platform": "windows",
                "size_bytes": len(payload),
                "sha256": "a" * 64,
                "signature": "A" * 88,
            }
            gitee_release = {
                "tag_name": "v1.2.12",
                "body": "",
                "assets": [
                    {"name": full_name, "size": len(payload), "browser_download_url": "full-gitee"},
                    {
                        "name": f"{full_name}.sig.json",
                        "size": 300,
                        "browser_download_url": "sig-gitee",
                    },
                ],
            }
            responses = {
                "full-github": _FakeResponse(status=404),
                "sig-github": _FakeResponse(status=403),
                updater.gitee_api: _FakeResponse(json_payload=gitee_release),
                "full-gitee": _FakeResponse(
                    body=payload, headers={"content-length": str(len(payload))}
                ),
                "sig-gitee": _FakeResponse(body=json.dumps(sig_payload).encode()),
            }
            session = _FakeSession(responses)
            asset = UpdateAsset(
                name=full_name,
                url="full-github",
                size_bytes=len(payload),
                package_type="windows_full_update",
                signature="A" * 88,
            )
            target = Path(temp) / "download.zip"
            await updater._download_asset_to_path(session, asset, str(target))
            assert target.read_bytes() == payload

            assets_by_name = {
                full_name.lower(): {
                    "name": full_name,
                    "size": len(payload),
                    "browser_download_url": "full-github",
                },
                f"{full_name}.sig.json".lower(): {
                    "name": f"{full_name}.sig.json",
                    "browser_download_url": "sig-github",
                },
            }
            metadata = await updater._read_signature_metadata(
                session,
                assets_by_name,
                assets_by_name[full_name.lower()],
                expected_package_type="windows_full_update",
                expected_target_version="1.2.12",
            )
            assert metadata == {
                "signature": "A" * 88,
                "sha256": "a" * 64,
                "size_bytes": len(payload),
            }
            # 签名元数据请求必须带短超时，否则资源域名被阻断时无法及时切换镜像
            for url, kwargs in session.get_calls:
                if url in ("sig-github", "sig-gitee"):
                    timeout = kwargs.get("timeout")
                    assert timeout is not None and 0 < float(timeout.total) <= 30, (url, kwargs)

            # 镜像版本与目标版本不一致时不得使用镜像资源
            gitee_release["tag_name"] = "v1.2.11"
            target.unlink()
            try:
                await updater._download_asset_to_path(session, asset, str(target))
            except RuntimeError as error:
                assert "404" in str(error), error
            else:
                raise AssertionError("mismatched mirror version was accepted")
            assert not target.exists()

            # 镜像资源大小与发布信息不一致时也要跳过
            gitee_release["tag_name"] = "v1.2.12"
            gitee_release["assets"][0]["size"] = len(payload) + 1
            try:
                await updater._download_asset_to_path(session, asset, str(target))
            except RuntimeError as error:
                assert "404" in str(error), error
            else:
                raise AssertionError("mirror asset with wrong size was accepted")
        finally:
            if old_home is None:
                os.environ.pop("DZFYQ_HOME", None)
            else:
                os.environ["DZFYQ_HOME"] = old_home


async def check_delta_failure_falls_back_before_complete() -> None:
    from src.gongju import update as update_module
    from src.gongju.update import UpdateAsset, Updater

    with tempfile.TemporaryDirectory(prefix="dzfyq_delta_fallback_") as temp:
        old_home = os.environ.get("DZFYQ_HOME")
        old_session = update_module.aiohttp.ClientSession
        os.environ["DZFYQ_HOME"] = temp
        try:
            updater = Updater()
            updater.latest_version = "1.2.12"
            delta = UpdateAsset(
                name="dazuofanyiguan_delta.for.windows_1.2.11_to_1.2.12.zip",
                url="delta",
                size_bytes=5,
                package_type="windows_file_delta",
                signature="sig",
                base_version="1.2.11",
            )
            full = UpdateAsset(
                name="dazuofanyiguan_full.for.windows_1.2.12.zip",
                url="full",
                size_bytes=4,
                package_type="windows_full_update",
                signature="sig",
            )
            updater._activate_update_asset(delta)
            updater._fallback_full_asset = full
            attempts = []

            async def fake_download(_session, asset, path):
                attempts.append(asset.package_type)
                Path(path).write_bytes(asset.url.encode())

            updater._download_asset_to_path = fake_download
            updater._verify_downloaded_package = lambda _path: None
            updater._prepare_delta_update_source = lambda _path: (_ for _ in ()).throw(
                RuntimeError("delta rebuild failed")
            )
            completed = []
            errors = []
            updater.update_complete.connect(completed.append)
            updater.update_error.connect(errors.append)
            update_module.aiohttp.ClientSession = lambda **kwargs: _FakeSession({})
            await updater.download_update()
            assert attempts == ["windows_file_delta", "windows_full_update"]
            assert updater.selected_package_type == "windows_full_update"
            assert len(completed) == 1
            assert Path(completed[0]).is_file()
            assert errors == []
        finally:
            update_module.aiohttp.ClientSession = old_session
            if old_home is None:
                os.environ.pop("DZFYQ_HOME", None)
            else:
                os.environ["DZFYQ_HOME"] = old_home


def check_delta_signature_rejects_tampering() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from src.gongju import update_trust
    from src.gongju.update_trust import (
        build_canonical_payload,
        sha256_file,
        verify_package_authenticity,
    )
    from tools.create_windows_delta_package import (
        create_delta_package,
        expected_delta_name,
    )
    from tools.verify_windows_delta_package import verify_adjacent_signature

    with tempfile.TemporaryDirectory(prefix="dzfyq_delta_signature_") as temp:
        root = Path(temp)
        base = root / "base.zip"
        target = root / "target.zip"
        _write_full_package(
            base,
            "1.2.10",
            {
                "大佐翻译官.exe": b"app-v1",
                "src/ziyuan/logo.ico": b"icon",
            },
        )
        _write_full_package(
            target,
            "1.2.11",
            {
                "大佐翻译官.exe": b"app-v2",
                "src/ziyuan/logo.ico": b"icon",
            },
        )
        delta = root / expected_delta_name("1.2.10", "1.2.11")
        create_delta_package(base, target, delta)
        key = Ed25519PrivateKey.generate()
        public_bytes = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        old_public = update_trust.UPDATE_ED25519_PUBLIC_KEY_B64
        update_trust.UPDATE_ED25519_PUBLIC_KEY_B64 = base64.b64encode(
            public_bytes
        ).decode("ascii")
        try:
            payload = {
                "app_version": "1.2.11",
                "package_type": "windows_file_delta",
                "platform": "windows",
                "filename": delta.name,
                "size_bytes": delta.stat().st_size,
                "sha256": sha256_file(str(delta)),
            }
            signature = base64.b64encode(
                key.sign(build_canonical_payload(payload))
            ).decode("ascii")
            verify_package_authenticity(
                package_path=str(delta),
                expected_version="1.2.11",
                signature_b64=signature,
                expected_filename=delta.name,
                package_type="windows_file_delta",
                platform="windows",
            )
            signature_path = Path(str(delta) + ".sig.json")
            signed_metadata = {**payload, "signature": signature}
            signature_path.write_text(
                json.dumps(signed_metadata),
                encoding="utf-8",
            )
            verify_adjacent_signature(delta, "1.2.11")
            for field, invalid_value in (
                ("app_version", "1.2.12"),
                ("platform", "macos"),
            ):
                invalid_metadata = {**signed_metadata, field: invalid_value}
                signature_path.write_text(
                    json.dumps(invalid_metadata),
                    encoding="utf-8",
                )
                try:
                    verify_adjacent_signature(delta, "1.2.11")
                except RuntimeError:
                    pass
                else:
                    raise AssertionError(f"invalid signature {field} was accepted")
            signature_path.write_text(json.dumps(signed_metadata), encoding="utf-8")
            with zipfile.ZipFile(delta, "a") as archive:
                archive.writestr("tampered.txt", b"tampered")
            try:
                verify_package_authenticity(
                    package_path=str(delta),
                    expected_version="1.2.11",
                    signature_b64=signature,
                    expected_filename=delta.name,
                    package_type="windows_file_delta",
                    platform="windows",
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("tampered delta signature was accepted")
        finally:
            update_trust.UPDATE_ED25519_PUBLIC_KEY_B64 = old_public


def check_delta_manifest_case_collision_and_empty_package() -> None:
    from src.gongju.update_delta import DeltaPackageError, inspect_delta_package

    with tempfile.TemporaryDirectory(prefix="dzfyq_delta_edges_") as temp:
        root = Path(temp)
        collision = root / "collision.zip"
        manifest = {
            "schema_version": 1,
            "package_type": "windows_file_delta",
            "platform": "windows",
            "base_version": "1.2.10",
            "app_version": "1.2.11",
            "created_at": "",
            "payload_files": [],
            "removed_files": [],
            "target_files": [
                {"path": "A.txt", "size_bytes": 0, "sha256": "0" * 64},
                {"path": "a.txt", "size_bytes": 0, "sha256": "0" * 64},
            ],
        }
        with zipfile.ZipFile(collision, "w") as archive:
            archive.writestr("delta_manifest.json", json.dumps(manifest))
        try:
            inspect_delta_package(collision)
        except DeltaPackageError:
            pass
        else:
            raise AssertionError("case-colliding target paths were accepted")

        empty = root / "empty.zip"
        manifest["target_files"] = []
        with zipfile.ZipFile(empty, "w") as archive:
            archive.writestr("delta_manifest.json", json.dumps(manifest))
        parsed = inspect_delta_package(empty)
        assert parsed.payload_files == ()
        assert parsed.removed_files == ()
        assert parsed.target_files == ()



def check_update_state_bom_and_backup_retention() -> None:
    from src.gongju.update import Updater
    from src.gui.update_controller import UpdateCoordinator

    with tempfile.TemporaryDirectory(prefix="dzfyq_update_state_bom_") as temp:
        path = Path(temp) / "last_update_result.json"
        expected = {"status": "failed", "message": "rollback"}
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps(expected).encode("utf-8"))
        coordinator = object.__new__(UpdateCoordinator)
        assert coordinator._consume_json_state(str(path)) == expected
        assert not path.exists()

    with tempfile.TemporaryDirectory(prefix="dzfyq_backup_retention_") as temp:
        old_home = os.environ.get("DZFYQ_HOME")
        os.environ["DZFYQ_HOME"] = temp
        try:
            backup_root = Path(temp) / "update_backup"
            backup_root.mkdir(parents=True)
            now = time.time()
            for index in range(4):
                backup = backup_root / f"backup_{index}"
                backup.mkdir()
                (backup / "marker.txt").write_text(str(index), encoding="utf-8")
                os.utime(backup, (now + index, now + index))
            updater = Updater()
            assert len(list(backup_root.iterdir())) == 4
            updater._prune_update_backups()
            remaining = sorted(path.name for path in backup_root.iterdir())
            assert remaining == ["backup_2", "backup_3"], remaining
        finally:
            if old_home is None:
                os.environ.pop("DZFYQ_HOME", None)
            else:
                os.environ["DZFYQ_HOME"] = old_home


def check_elevated_silent_update_is_rejected() -> None:
    from src.gongju.update import Updater

    with tempfile.TemporaryDirectory(prefix="dzfyq_elevated_update_") as temp:
        package = Path(temp) / "package.zip"
        package.write_bytes(b"placeholder")
        old_home = os.environ.get("DZFYQ_HOME")
        os.environ["DZFYQ_HOME"] = str(Path(temp) / "home")
        try:
            updater = Updater()
            updater._is_frozen_app = lambda: True
            updater._is_process_elevated = lambda: True
            for action in (
                lambda: updater._prepare_delta_update_source(str(package)),
                lambda: updater._apply_windows_full_update(str(package)),
            ):
                try:
                    action()
                except RuntimeError as error:
                    assert "管理员身份" in str(error)
                else:
                    raise AssertionError("elevated silent update was accepted")
        finally:
            if old_home is None:
                os.environ.pop("DZFYQ_HOME", None)
            else:
                os.environ["DZFYQ_HOME"] = old_home


def check_delta_rebuild_rejects_reparse_output() -> None:
    from src.gongju.update_delta import (
        DeltaPackageError,
        is_reparse_point,
        reconstruct_delta_package,
    )
    from tools.create_windows_delta_package import create_delta_package, expected_delta_name

    with tempfile.TemporaryDirectory(prefix="dzfyq_delta_reparse_") as temp:
        root = Path(temp)
        base = root / "base.zip"
        target = root / "target.zip"
        _write_full_package(base, "1.2.10", {"大佐翻译官.exe": b"old"})
        _write_full_package(target, "1.2.11", {"大佐翻译官.exe": b"new"})
        delta = root / expected_delta_name("1.2.10", "1.2.11")
        create_delta_package(base, target, delta)
        install = root / "install"
        _extract_install_layout(base, install)
        allowed = root / "cache"
        victim = root / "victim"
        allowed.mkdir()
        victim.mkdir()
        marker = victim / "marker.txt"
        marker.write_text("keep", encoding="utf-8")
        output = allowed / "rebuilt"
        if os.name == "nt":
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(output), str(victim)],
                check=False,
                capture_output=True,
            )
            if created.returncode != 0:
                raise RuntimeError(created.stderr.decode(errors="replace"))
        else:
            os.symlink(victim, output, target_is_directory=True)
        try:
            assert is_reparse_point(output)
            try:
                reconstruct_delta_package(
                    delta,
                    install_dir=install,
                    output_dir=output,
                    expected_base_version="1.2.10",
                    expected_target_version="1.2.11",
                    allowed_output_root=allowed,
                )
            except DeltaPackageError:
                pass
            else:
                raise AssertionError("reparse-point output was accepted")
            assert marker.read_text(encoding="utf-8") == "keep"
        finally:
            if os.path.lexists(output):
                if os.name == "nt":
                    # Windows junction：按目录删除，不会影响目标目录内容
                    os.rmdir(output)
                else:
                    # POSIX 符号链接：必须 unlink，rmdir 会抛 NotADirectoryError
                    os.unlink(output)


async def check_signature_metadata_size_limit() -> None:
    from src.gongju.update import Updater

    updater = Updater()
    package_name = "dazuofanyiguan_delta.for.windows_1.2.11_to_1.2.12.zip"
    signature_name = f"{package_name}.sig.json"
    package = {"name": package_name, "size": 100, "browser_download_url": "delta"}
    assets = {
        signature_name.lower(): {
            "name": signature_name,
            "browser_download_url": "signature",
        }
    }
    session = _FakeSession(
        {"signature": _FakeResponse(body=b"x" * (updater.MAX_SIGNATURE_METADATA_BYTES + 1))}
    )
    try:
        await updater._read_signature_metadata(
            session,
            assets,
            package,
            expected_package_type="windows_file_delta",
            expected_target_version="1.2.12",
        )
    except RuntimeError as error:
        assert "体积异常" in str(error)
    else:
        raise AssertionError("oversized signature metadata was accepted")


def check_delta_signer_omits_release_marker() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    with tempfile.TemporaryDirectory(prefix="dzfyq_delta_signer_") as temp:
        root = Path(temp)
        package = root / "dazuofanyiguan_delta.for.windows_1.2.10_to_1.2.11.zip"
        package.write_bytes(b"delta")
        key_path = root / "key.pem"
        key_path.write_bytes(
            Ed25519PrivateKey.generate().private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "sign_windows_update_package.py"),
                str(package),
                "--version",
                "1.2.11",
                "--package-type",
                "windows_file_delta",
                "--platform",
                "windows",
                "--private-key",
                str(key_path),
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        metadata = json.loads(Path(str(package) + ".sig.json").read_text(encoding="utf-8"))
        assert "release_notes_marker" not in metadata
        assert "release_notes_markers" not in metadata
        assert "DZFYQ-DELTA-SIG" not in result.stdout




def check_apply_script_ignores_reused_pid() -> None:
    if os.name != "nt":
        return

    from src.gongju.update import Updater

    with tempfile.TemporaryDirectory(prefix="dzfyq_pid_reuse_") as temp:
        root = Path(temp)
        source_dir = root / "source"
        target_dir = root / "target"
        backup_dir = root / "backup"
        state_dir = root / "state"
        source_dir.mkdir()
        target_dir.mkdir()
        state_dir.mkdir()

        executable = Path(os.environ["SystemRoot"]) / "System32" / "where.exe"
        shutil.copy2(executable, source_dir / "dzfyq_pid_reuse_app.exe")
        shutil.copy2(executable, target_dir / "dzfyq_pid_reuse_app.exe")
        (source_dir / "update_manifest.json").write_text(
            json.dumps({"app_version": "1.2.11"}),
            encoding="utf-8",
        )
        (target_dir / "update_manifest.json").write_text(
            json.dumps({"app_version": "1.2.10"}),
            encoding="utf-8",
        )

        log_path = state_dir / "apply.log"
        result_path = state_dir / "result.json"
        pending_path = state_dir / "pending.json"
        pending_path.write_text("{}", encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "DZFYQ_UPDATE_SOURCE_DIR": str(source_dir),
                "DZFYQ_UPDATE_TARGET_DIR": str(target_dir),
                "DZFYQ_UPDATE_EXE_NAME": "dzfyq_pid_reuse_app.exe",
                "DZFYQ_UPDATE_PROCESS_ID": str(os.getpid()),
                "DZFYQ_UPDATE_PROCESS_CREATED_FILETIME": "1",
                "DZFYQ_UPDATE_BACKUP_DIR": str(backup_dir),
                "DZFYQ_UPDATE_LOG_PATH": str(log_path),
                "DZFYQ_UPDATE_RESULT_PATH": str(result_path),
                "DZFYQ_UPDATE_PENDING_PATH": str(pending_path),
                "DZFYQ_UPDATE_EXPECTED_VERSION": "1.2.11",
            }
        )
        encoded_script = base64.b64encode(
            Updater()._build_apply_script().encode("utf-16-le")
        ).decode("ascii")
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded_script,
            ],
            env=env,
            cwd=root,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            ["taskkill.exe", "/F", "/IM", "dzfyq_pid_reuse_app.exe"],
            capture_output=True,
            check=False,
        )
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        log_text = log_path.read_text(encoding="utf-8-sig")
        assert completed.returncode == 0, (
            completed.stderr.decode(errors="replace")
            + "\nresult="
            + repr(result)
            + "\nlog="
            + log_text
        )
        assert result["status"] == "success"
        assert "has been reused" in log_text
        assert not pending_path.exists()
        target_executable = target_dir / "dzfyq_pid_reuse_app.exe"
        for _attempt in range(50):
            try:
                target_executable.unlink()
                break
            except PermissionError:
                time.sleep(0.1)
        else:
            raise AssertionError("restarted test executable did not release its image lock")


# ---------------------------------------------------------------------------
# 1.2.11 翻译服务：Google 备用接口、微软翻译、精确错误提示、未连接提示
# ---------------------------------------------------------------------------


class _JsonResponse:
    def __init__(self, status=200, payload=None, text=None):
        self.status = status
        self._payload = payload
        self._text = text if text is not None else json.dumps(payload, ensure_ascii=False)
        self.url = type("_Url", (), {"host": "cn.bing.com"})()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return self._text


class _RoutedSession:
    """按 URL 前缀返回预设响应，并记录请求顺序。"""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.closed = False

    def _pick(self, method, url):
        self.calls.append((method, url))
        for prefix, factory in self.routes:
            if url.startswith(prefix):
                return factory()
        raise AssertionError(f"unexpected request {method} {url}")

    def get(self, url, **kwargs):
        return self._pick("GET", url)

    def post(self, url, **kwargs):
        return self._pick("POST", url)

    async def close(self):
        self.closed = True


def check_google_falls_back_to_secondary_endpoint() -> None:
    from src.gongju.fanyi import TranslationServiceError
    from src.gongju.fanyi_api.google import GoogleAPI

    api = GoogleAPI()
    session = _RoutedSession(
        [
            (GoogleAPI.PRIMARY_URL, lambda: _JsonResponse(status=429, payload=None, text="<html>Sorry</html>")),
            (GoogleAPI.FALLBACK_URL, lambda: _JsonResponse(payload=[["你好世界", "en"]])),
        ]
    )
    api.session = session

    async def scenario():
        await api.health_check()
        assert api._prefer_fallback is True, "备用接口成功后应优先使用备用接口"
        translated, detected = await api.fanyi("hello world", "自动检测", "简体中文")
        assert translated == "你好世界" and detected == "en", (translated, detected)
        # 第二次请求不应再打主接口
        primary_calls = [url for _, url in session.calls if url.startswith(GoogleAPI.PRIMARY_URL)]
        assert len(primary_calls) == 1, session.calls

        # 两个接口都被限流时，错误应为精确的 429 提示并给出替代方案
        api2 = GoogleAPI()
        api2.session = _RoutedSession(
            [
                (GoogleAPI.PRIMARY_URL, lambda: _JsonResponse(status=429, payload=None, text="x")),
                (GoogleAPI.FALLBACK_URL, lambda: _JsonResponse(status=429, payload=None, text="x")),
            ]
        )
        try:
            await api2.health_check()
        except TranslationServiceError as error:
            assert error.kind == "rate_limited", error.kind
            assert "429" in str(error) and "微软翻译" in str(error), str(error)
        else:
            raise AssertionError("expected rate limited error")

    asyncio.run(scenario())

    # 主接口域名超时/连不上时仍要尝试备用接口（分流代理、DNS 故障等场景）
    api3 = GoogleAPI()

    def primary_unreachable():
        raise asyncio.TimeoutError()

    api3.session = _RoutedSession(
        [
            (GoogleAPI.PRIMARY_URL, primary_unreachable),
            (GoogleAPI.FALLBACK_URL, lambda: _JsonResponse(payload=[["你好", "en"]])),
        ]
    )

    async def scenario_timeout():
        await api3.health_check()
        assert api3._prefer_fallback is True
        assert (await api3.fanyi("hello", "自动检测", "简体中文")) == ("你好", "en")

    asyncio.run(scenario_timeout())

    # 主接口 HTTP 200 但返回验证页（非 JSON）时也要切到备用接口
    class _HtmlResponse(_JsonResponse):
        async def json(self, content_type=None):
            raise json.JSONDecodeError("Expecting value", "<html>", 0)

    api5 = GoogleAPI()
    api5.session = _RoutedSession(
        [
            (GoogleAPI.PRIMARY_URL, lambda: _HtmlResponse(payload=None, text="<html>captcha</html>")),
            (GoogleAPI.FALLBACK_URL, lambda: _JsonResponse(payload=[["你好", "en"]])),
        ]
    )

    async def scenario_html():
        await api5.health_check()
        assert (await api5.fanyi("hello", "自动检测", "简体中文")) == ("你好", "en")

    asyncio.run(scenario_html())

    api6 = GoogleAPI()
    api6.session = _RoutedSession(
        [
            (GoogleAPI.PRIMARY_URL, lambda: _HtmlResponse(payload=None, text="<html>")),
            (GoogleAPI.FALLBACK_URL, lambda: _HtmlResponse(payload=None, text="<html>")),
        ]
    )
    try:
        asyncio.run(api6.health_check())
    except TranslationServiceError as error:
        assert error.kind == "server" and "无法识别" in str(error), str(error)
    else:
        raise AssertionError("expected server error for invalid JSON")

    api4 = GoogleAPI()
    api4.session = _RoutedSession(
        [
            (GoogleAPI.PRIMARY_URL, primary_unreachable),
            (GoogleAPI.FALLBACK_URL, primary_unreachable),
        ]
    )
    try:
        asyncio.run(api4.health_check())
    except TranslationServiceError as error:
        assert error.kind == "network_blocked", error.kind
        assert "海外网站" in str(error)
    else:
        raise AssertionError("expected network_blocked error")

    assert GoogleAPI.parse_fallback_response(["こんにちは"], False) == ("こんにちは", None)
    assert GoogleAPI.parse_primary_response([[["你好", "hello", None, None]], None, "en"]) == ("你好", "en")


def check_google_blocked_network_message_mentions_overseas_access() -> None:
    import aiohttp

    from src.gongju.fanyi import describe_connection_error, describe_http_status

    blocked = describe_connection_error(
        asyncio.TimeoutError(),
        "Google 翻译",
        overseas_required=True,
        alternatives="微软翻译",
    )
    assert blocked.kind == "network_blocked", blocked.kind
    message = str(blocked)
    assert "海外网站" in message and "代理" in message and "微软翻译" in message, message

    plain = describe_connection_error(asyncio.TimeoutError(), "微软翻译", overseas_required=False)
    assert plain.kind == "timeout", plain.kind
    assert "海外" not in str(plain)

    key = aiohttp.client_reqrep.ConnectionKey("x", 443, True, None, None, None, None)
    connector_error = aiohttp.ClientConnectorError(key, OSError("refused"))
    described = describe_connection_error(connector_error, "微软翻译")
    assert described.kind == "network", described.kind

    auth = describe_http_status(401, "DeepL", detail="Wrong key")
    assert auth.kind == "auth" and "API Key" in str(auth), str(auth)
    server = describe_http_status(503, "微软翻译")
    assert server.kind == "server" and "503" in str(server)


def check_not_connected_translation_error_explains_reason() -> None:
    from src.gongju.fanyi import DaZaoFanYi, TranslationServiceError

    fanyi = DaZaoFanYi()

    async def attempt():
        return await fanyi.fanyi("hello", "自动检测", "简体中文")

    try:
        asyncio.run(attempt())
    except TranslationServiceError as error:
        assert "未设置翻译接口" not in str(error)
        assert error.kind == "not_connected"
        assert "重试" in str(error) and "设置" in str(error), str(error)
    else:
        raise AssertionError("expected not_connected error")

    fanyi.set_connection_state("connecting")
    try:
        asyncio.run(attempt())
    except TranslationServiceError as error:
        assert "正在连接" in str(error), str(error)
    else:
        raise AssertionError("expected connecting error")

    reason = "无法连接到 Google 翻译。Google 翻译在中国大陆无法直接访问，请确认已开启可以访问海外网站的网络。"
    fanyi.set_connection_state("error", reason)
    try:
        asyncio.run(attempt())
    except TranslationServiceError as error:
        assert reason in str(error), str(error)
        assert "翻译服务未连接" in str(error)
    else:
        raise AssertionError("expected error with reason")


def check_microsoft_web_translation_flow() -> None:
    from src.gongju.fanyi import TranslationServiceError
    from src.gongju.fanyi_api.microsoft import (
        MicrosoftAPI,
        WEB_CHUNK_LIMIT,
        split_text_for_translation,
    )

    page = (
        '<html><script>IG:"ABCDEF123"</script>'
        '<div data-iid="translator.5028"></div>'
        "<script>var params_AbusePreventionHelper = [1790041388956,\"tok-en_1\",3600000];</script></html>"
    )
    ig, iid, key, token, expiry = MicrosoftAPI.parse_web_page(page)
    assert (ig, iid, key, token, expiry) == ("ABCDEF123", "translator.5028", 1790041388956, "tok-en_1", 3600000)
    try:
        MicrosoftAPI.parse_web_page("<html>changed</html>")
    except TranslationServiceError as error:
        assert error.kind == "server"
    else:
        raise AssertionError("expected parse failure")

    payload = [
        {
            "detectedLanguage": {"language": "en", "score": 1.0},
            "translations": [{"text": "你好，世界", "to": "zh-Hans"}],
        }
    ]
    assert MicrosoftAPI.parse_translation_response(payload) == ("你好，世界", "en")
    try:
        MicrosoftAPI.parse_translation_response({"statusCode": 205})
    except TranslationServiceError as error:
        assert error.short == "令牌过期"
    else:
        raise AssertionError("expected token expiry error")

    api = MicrosoftAPI()
    assert api.mode == "web"
    state = {"translate_calls": 0}

    def translate_response():
        state["translate_calls"] += 1
        if state["translate_calls"] == 1:
            # 第一次返回空体：模拟令牌失效，应刷新令牌后重试
            return _JsonResponse(status=200, payload=None, text="")
        return _JsonResponse(payload=payload)

    session = _RoutedSession(
        [
            (MicrosoftAPI.WEB_ENTRY_URL, lambda: _JsonResponse(payload=None, text=page)),
            ("https://cn.bing.com/ttranslatev3", translate_response),
        ]
    )
    api.session = session

    async def scenario():
        await api.health_check()
        assert api._host == "cn.bing.com"
        translated, detected = await api.fanyi("Hello world", "自动检测", "简体中文")
        assert translated == "你好，世界" and detected == "en", (translated, detected)
        assert state["translate_calls"] == 3, state
        page_loads = [url for _, url in session.calls if url == MicrosoftAPI.WEB_ENTRY_URL]
        assert len(page_loads) == 2, session.calls
        # 不支持的目标语言应给出配置类错误而非崩溃
        try:
            await api.fanyi("hello", "自动检测", "自动检测")
        except TranslationServiceError as error:
            assert error.kind == "config"
        else:
            raise AssertionError("expected config error")

    asyncio.run(scenario())

    azure = MicrosoftAPI(api_key="k" * 32, region="eastasia")
    assert azure.mode == "azure"

    # 分段边界的空格/换行必须保留：服务端返回去掉首尾空白的译文时不能把相邻分段粘连
    from src.gongju.fanyi_api import microsoft as microsoft_module

    sep_api = MicrosoftAPI()
    seen_chunks = []

    async def fake_chunk(chunk_text, _source, _target):
        seen_chunks.append(chunk_text)
        assert chunk_text == chunk_text.strip(), repr(chunk_text)
        return f"T{chunk_text}", "en"

    sep_api._translate_web_chunk = fake_chunk
    old_limit = microsoft_module.WEB_CHUNK_LIMIT
    microsoft_module.WEB_CHUNK_LIMIT = 40
    try:
        source_text = "Hello world. " * 6 + "\n\n" + "Second paragraph here. " * 4
        joined, _ = asyncio.run(sep_api._translate_text(source_text, "en", "zh-Hans"))
    finally:
        microsoft_module.WEB_CHUNK_LIMIT = old_limit
    assert len(seen_chunks) > 2, seen_chunks
    assert "world.T" not in joined and ".T" not in joined, joined
    assert "\n\n" in joined, repr(joined)
    assert joined.count("THello") + joined.count("TSecond") == len(seen_chunks), joined

    # 中文按“。”切分后译成英文：源边界没有空格，拼接时必须补空格
    from src.gongju.fanyi_api.microsoft import join_translated_chunks

    zh_api = MicrosoftAPI()
    zh_chunks = []

    async def fake_zh_to_en(chunk_text, _source, _target):
        zh_chunks.append(chunk_text)
        return f"Sentence {len(zh_chunks)} is here.", "zh-Hans"

    zh_api._translate_web_chunk = fake_zh_to_en
    microsoft_module.WEB_CHUNK_LIMIT = 12
    try:
        zh_joined, _ = asyncio.run(zh_api._translate_text("这是第一句话。这是第二句话。这是第三句话。", "zh-Hans", "en"))
    finally:
        microsoft_module.WEB_CHUNK_LIMIT = old_limit
    assert len(zh_chunks) >= 2, zh_chunks
    assert ".S" not in zh_joined, zh_joined
    assert zh_joined == " ".join(f"Sentence {i} is here." for i in range(1, len(zh_chunks) + 1)), zh_joined

    # 中日韩目标语言之间不补空格；源边界空白原样保留
    assert join_translated_chunks([("", "第一句。", ""), ("", "第二句。", "")]) == "第一句。第二句。"
    assert join_translated_chunks([("", "Hello.", ""), ("", "World.", "")]) == "Hello. World."
    assert join_translated_chunks([("", "Hello.", " "), ("", "World.", "")]) == "Hello. World."
    assert join_translated_chunks([("", "第一段", "\n\n"), ("", "第二段", "")]) == "第一段\n\n第二段"
    assert join_translated_chunks([("", "Hello", ""), ("", "，世界", "")]) == "Hello，世界"

    chunks = split_text_for_translation("句子一。" * 400, WEB_CHUNK_LIMIT)
    assert all(len(chunk) <= WEB_CHUNK_LIMIT for chunk in chunks)
    assert "".join(chunks) == "句子一。" * 400
    assert split_text_for_translation("short", 1000) == ["short"]
    assert MicrosoftAPI.DETECTED_LANG_CODES["zh-Hans"] == "简体中文"


def check_microsoft_service_is_registered_everywhere() -> None:
    from src.gongju.fanyi_api.microsoft import MicrosoftAPI
    from src.gongju.fanyi_factory import SERVICE_DISPLAY_NAMES, build_translation_api
    from src.gui.translator_controller import (
        _snapshot_translation_config,
        service_display_name,
        status_label_for_error,
    )
    from src.shezhi.config_defaults import build_default_config
    from src.viewmodels.translator_viewmodel import REMOTE_COOLDOWN_SERVICES

    defaults = build_default_config()
    assert defaults["microsoft"] == {"api_key": "", "region": ""}

    class ConfigStub:
        def __init__(self, values):
            self.values = values

        def get(self, key, default=None):
            return self.values.get(key, default)

    config = ConfigStub({"translation.api": "microsoft", "microsoft.api_key": "secret-key", "microsoft.region": "eastasia"})
    api = build_translation_api(config)
    assert isinstance(api, MicrosoftAPI) and api.mode == "azure" and api.region == "eastasia"
    snapshot = _snapshot_translation_config(config, "microsoft")
    assert snapshot["microsoft.api_key"] == "secret-key" and snapshot["microsoft.region"] == "eastasia"
    assert SERVICE_DISPLAY_NAMES["microsoft"] == "微软翻译"
    assert service_display_name(config) == "微软翻译"
    assert "microsoft" in REMOTE_COOLDOWN_SERVICES

    from src.gongju.fanyi import TranslationServiceError

    assert status_label_for_error(TranslationServiceError("x", kind="network_blocked"), "x") == "连接失败：需海外网络"
    assert status_label_for_error(None, "Google 翻译暂时限制了当前网络的访问（HTTP 429）", prefix="翻译失败") == "翻译失败：请求受限"
    assert status_label_for_error(None, "未设置DeepL API密钥") == "未设置或密钥无效"
    assert status_label_for_error(None, "翻译服务未连接：xxx") == "服务未连接"


def main() -> int:
    check_delta_generation_and_reconstruction()
    print("ok delta_generation_and_reconstruction")
    check_delta_manifest_rejects_unsafe_paths()
    print("ok delta_manifest_rejects_unsafe_paths")
    check_delta_case_only_rename_is_not_recorded_as_removal()
    print("ok delta_case_only_rename_is_not_recorded_as_removal")
    asyncio.run(check_delta_asset_selection_and_threshold())
    print("ok delta_asset_selection_and_threshold")
    asyncio.run(check_update_source_falls_back_to_gitee())
    print("ok update_source_falls_back_to_gitee")
    asyncio.run(check_asset_download_falls_back_to_mirror_source())
    print("ok asset_download_falls_back_to_mirror_source")
    asyncio.run(check_delta_failure_falls_back_before_complete())
    print("ok delta_failure_falls_back_before_complete")
    check_delta_signature_rejects_tampering()
    print("ok delta_signature_rejects_tampering")
    check_delta_manifest_case_collision_and_empty_package()
    print("ok delta_manifest_case_collision_and_empty_package")
    check_update_state_bom_and_backup_retention()
    print("ok update_state_bom_and_backup_retention")
    check_elevated_silent_update_is_rejected()
    print("ok elevated_silent_update_is_rejected")
    check_delta_rebuild_rejects_reparse_output()
    print("ok delta_rebuild_rejects_reparse_output")
    asyncio.run(check_signature_metadata_size_limit())
    print("ok signature_metadata_size_limit")
    check_apply_script_ignores_reused_pid()
    print("ok apply_script_ignores_reused_pid")
    check_delta_signer_omits_release_marker()
    print("ok delta_signer_omits_release_marker")
    check_google_falls_back_to_secondary_endpoint()
    print("ok google_falls_back_to_secondary_endpoint")
    check_google_blocked_network_message_mentions_overseas_access()
    print("ok google_blocked_network_message_mentions_overseas_access")
    check_not_connected_translation_error_explains_reason()
    print("ok not_connected_translation_error_explains_reason")
    check_microsoft_web_translation_flow()
    print("ok microsoft_web_translation_flow")
    check_microsoft_service_is_registered_everywhere()
    print("ok microsoft_service_is_registered_everywhere")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
