"""Mirror a GitHub Release to Gitee (same tag, same notes, same asset files).

Gitee is kept as the secondary update source: clients <= 1.2.10 only read Gitee, and newer
clients fall back to Gitee when GitHub is unreachable. Every version must therefore be
published to both sides with byte-identical packages and identical signature markers.

Usage:
    set GITEE_TOKEN=<gitee personal access token with "projects" scope>
    python tools/publish_gitee_release.py --version 1.2.11 --assets-dir output

    # or download the GitHub Release assets first:
    gh release download v1.2.11 --repo Achordchan/dazuo-win --dir release_1.2.11
    python tools/publish_gitee_release.py --version 1.2.11 --assets-dir release_1.2.11

The notes are taken from release_notes_<version>.md inside the assets dir when present,
otherwise from --notes-file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

GITEE_API = "https://gitee.com/api/v5"
DEFAULT_OWNER = "Achordchan"
DEFAULT_REPO = "dazuofanyiguan"
ASSET_SUFFIXES = (".zip", ".zip.sig.json", ".exe", ".dmg")


def _request(method: str, url: str, *, data=None, headers=None, timeout=600):
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return response.status, body
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def _json(body: bytes):
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return {"raw": body[:500].decode("utf-8", errors="replace")}


def list_release_assets(assets_dir: Path) -> list[Path]:
    files = []
    for path in sorted(assets_dir.iterdir()):
        if path.is_file() and path.name.lower().endswith(ASSET_SUFFIXES):
            files.append(path)
    return files


def find_release(token: str, owner: str, repo: str, tag: str) -> dict | None:
    query = urllib.parse.urlencode({"access_token": token})
    status, body = _request("GET", f"{GITEE_API}/repos/{owner}/{repo}/releases/tags/{tag}?{query}")
    if status == 200:
        payload = _json(body)
        return payload if isinstance(payload, dict) and payload.get("id") else None
    if status == 404:
        return None
    raise SystemExit(f"查询 Gitee Release 失败: HTTP {status} {_json(body)}")


def create_release(token: str, owner: str, repo: str, tag: str, notes: str, target: str) -> dict:
    payload = urllib.parse.urlencode(
        {
            "access_token": token,
            "tag_name": tag,
            "name": tag,
            "body": notes,
            "prerelease": "false",
            "target_commitish": target,
        }
    ).encode("utf-8")
    status, body = _request(
        "POST",
        f"{GITEE_API}/repos/{owner}/{repo}/releases",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if status not in (200, 201):
        raise SystemExit(f"创建 Gitee Release 失败: HTTP {status} {_json(body)}")
    return _json(body)


def update_release_notes(token: str, owner: str, repo: str, release_id: int, tag: str, notes: str) -> None:
    payload = urllib.parse.urlencode(
        {"access_token": token, "tag_name": tag, "name": tag, "body": notes, "prerelease": "false"}
    ).encode("utf-8")
    status, body = _request(
        "PATCH",
        f"{GITEE_API}/repos/{owner}/{repo}/releases/{release_id}",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if status not in (200, 201):
        raise SystemExit(f"更新 Gitee Release 说明失败: HTTP {status} {_json(body)}")


def existing_attachments(token: str, owner: str, repo: str, release_id: int) -> dict[str, dict]:
    query = urllib.parse.urlencode({"access_token": token, "page": 1, "per_page": 100})
    status, body = _request(
        "GET", f"{GITEE_API}/repos/{owner}/{repo}/releases/{release_id}/attach_files?{query}"
    )
    if status != 200:
        return {}
    payload = _json(body)
    result = {}
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("name"):
                result[str(item["name"]).lower()] = item
    return result


def delete_attachment(token: str, owner: str, repo: str, release_id: int, attach_id: int) -> None:
    query = urllib.parse.urlencode({"access_token": token})
    status, body = _request(
        "DELETE",
        f"{GITEE_API}/repos/{owner}/{repo}/releases/{release_id}/attach_files/{attach_id}?{query}",
    )
    if status not in (200, 204):
        raise SystemExit(f"删除旧附件失败: HTTP {status} {_json(body)}")


def upload_attachment(token: str, owner: str, repo: str, release_id: int, path: Path) -> dict:
    boundary = f"----dzfyq{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="access_token"\r\n\r\n{token}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = head + path.read_bytes() + tail
    status, response = _request(
        "POST",
        f"{GITEE_API}/repos/{owner}/{repo}/releases/{release_id}/attach_files",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        timeout=1800,
    )
    if status not in (200, 201):
        raise SystemExit(f"上传附件失败 {path.name}: HTTP {status} {_json(response)}")
    return _json(response)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_signature_sidecars(assets: list[Path]) -> None:
    """Refuse to publish if a .sig.json does not describe the ZIP next to it."""
    by_name = {path.name: path for path in assets}
    for path in assets:
        if not path.name.endswith(".zip.sig.json"):
            continue
        package = by_name.get(path.name[: -len(".sig.json")])
        if package is None:
            raise SystemExit(f"缺少与签名文件对应的包: {path.name}")
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if payload.get("filename") != package.name:
            raise SystemExit(f"签名文件名不匹配: {path.name}")
        if int(payload.get("size_bytes") or 0) != package.stat().st_size:
            raise SystemExit(f"签名文件大小不匹配: {package.name}")
        if str(payload.get("sha256") or "").lower() != sha256_of(package):
            raise SystemExit(f"签名文件 SHA256 不匹配: {package.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True)
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--notes-file", type=Path, default=None)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--target", default="main", help="branch/commit the tag is created on when the tag is new")
    parser.add_argument("--token", default=None, help="Gitee token; defaults to env GITEE_TOKEN")
    args = parser.parse_args()

    token = (args.token or os.environ.get("GITEE_TOKEN") or "").strip()
    if not token:
        raise SystemExit("缺少 Gitee 令牌：请设置环境变量 GITEE_TOKEN 或传 --token。")

    version = args.version.strip().lstrip("vV")
    tag = f"v{version}"
    assets_dir = args.assets_dir.resolve()
    if not assets_dir.is_dir():
        raise SystemExit(f"资源目录不存在: {assets_dir}")

    notes_file = args.notes_file or (assets_dir / f"release_notes_{version}.md")
    if not notes_file.is_file():
        raise SystemExit(f"缺少 Release 说明文件: {notes_file}")
    notes = notes_file.read_text(encoding="utf-8")
    if "DZFYQ-SIG" not in notes:
        raise SystemExit("Release 说明缺少 DZFYQ-SIG 签名标记，旧客户端会拒绝更新。")

    assets = [path for path in list_release_assets(assets_dir) if version in path.name]
    if not any(path.name == f"dazuofanyiguan_full.for.windows_{version}.zip" for path in assets):
        raise SystemExit(f"缺少全量包 dazuofanyiguan_full.for.windows_{version}.zip")
    verify_signature_sidecars(assets)

    release = find_release(token, args.owner, args.repo, tag)
    if release is None:
        release = create_release(token, args.owner, args.repo, tag, notes, args.target)
        print(f"已创建 Gitee Release {tag} (id={release.get('id')})")
    else:
        update_release_notes(token, args.owner, args.repo, int(release["id"]), tag, notes)
        print(f"Gitee Release {tag} 已存在 (id={release.get('id')})，已刷新说明")
    release_id = int(release["id"])

    existing = existing_attachments(token, args.owner, args.repo, release_id)
    for path in assets:
        old = existing.get(path.name.lower())
        if old and old.get("id"):
            delete_attachment(token, args.owner, args.repo, release_id, int(old["id"]))
            print(f"已删除旧附件 {path.name}")
        result = upload_attachment(token, args.owner, args.repo, release_id, path)
        print(f"已上传 {path.name} ({path.stat().st_size} bytes) -> {result.get('browser_download_url') or result.get('name')}")

    print(f"完成：https://gitee.com/{args.owner}/{args.repo}/releases/tag/{tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
