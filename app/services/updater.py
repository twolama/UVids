import json
import hashlib
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser

try:
    from packaging import version as packaging_version  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency fallback
    packaging_version = None

GITHUB_OWNER = "twolama"
GITHUB_REPO = "UVids"
GITHUB_LATEST_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


def _normalize_version(version):
    value = (version or "").strip().lower()
    if value.startswith("v"):
        value = value[1:]
    return value


def _version_key(version):
    normalized = _normalize_version(version)
    parts = re.findall(r"\d+", normalized)
    if not parts:
        return (0,)
    return tuple(int(part) for part in parts)


def is_newer_version(latest_version, current_version):
    if packaging_version is not None:
        try:
            return packaging_version.parse(latest_version) > packaging_version.parse(current_version)
        except Exception:
            pass
    return _version_key(latest_version) > _version_key(current_version)


def _request_json(url, timeout=10):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "UVids-Downloader-Updater",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _pick_asset(assets):
    assets = assets or []
    if not assets:
        return None

    candidates = []
    for asset in assets:
        name = (asset.get("name") or "").lower()
        score = 0

        if sys.platform.startswith("win"):
            if name.endswith(".exe"):
                score += 100
            elif name.endswith(".msi"):
                score += 90
            elif name.endswith(".zip"):
                score += 70
        elif sys.platform.startswith("linux"):
            if name.endswith(".appimage"):
                score += 100
            elif name.endswith(".tar.gz") or name.endswith(".tar.xz"):
                score += 85
            elif name.endswith(".zip"):
                score += 60
        elif sys.platform == "darwin":
            if name.endswith(".dmg"):
                score += 100
            elif name.endswith(".pkg"):
                score += 90
            elif name.endswith(".zip"):
                score += 70

        if "setup" in name:
            score += 20
        if "installer" in name:
            score += 20
        if "release" in name:
            score += 10
        if any(token in name for token in ("debug", "symbols", "sha256", "checksums", "sig")):
            score -= 40

        candidates.append((score, asset))

    # Keep deterministic behavior when scores tie by preserving original order.
    return max(candidates, key=lambda entry: entry[0])[1]


def check_latest_release(current_version, timeout=10):
    try:
        release = _request_json(GITHUB_LATEST_API, timeout=timeout)
        latest_version = release.get("tag_name") or release.get("name") or ""
        latest_version = _normalize_version(latest_version)
        current_version = _normalize_version(current_version)

        asset = _pick_asset(release.get("assets", []))
        update_available = bool(latest_version) and is_newer_version(latest_version, current_version)

        return {
            "ok": True,
            "current_version": current_version,
            "latest_version": latest_version,
            "update_available": update_available,
            "release_url": release.get("html_url"),
            "asset": {
                "name": asset.get("name"),
                "url": asset.get("browser_download_url"),
                "size": asset.get("size", 0),
            }
            if asset
            else None,
        }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "message": f"Update check failed (HTTP {exc.code}).",
        }
    except urllib.error.URLError:
        return {
            "ok": False,
            "message": "Could not reach GitHub. Check your internet connection and try again.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Update check failed: {exc}",
        }


def _sha256_file(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(8192)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_file_checksum(path, expected_sha256):
    if not expected_sha256:
        return True
    expected = expected_sha256.strip().lower()
    return _sha256_file(path).lower() == expected


def download_asset(
    asset_url,
    asset_name,
    progress_callback=None,
    timeout=20,
    max_retries=3,
    retry_backoff=1.5,
    expected_sha256=None,
):
    if not asset_url:
        raise ValueError("Missing asset URL")

    temp_dir = os.path.join(tempfile.gettempdir(), "uvids-updater")
    os.makedirs(temp_dir, exist_ok=True)
    file_name = asset_name or "uvids-update.bin"
    target_path = os.path.join(temp_dir, file_name)

    last_error = None
    attempts = max(1, int(max_retries))
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                asset_url,
                headers={
                    "User-Agent": "UVids-Downloader-Updater",
                    "Accept": "*/*",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                total = int(response.headers.get("Content-Length", "0") or 0)
                downloaded = 0
                with open(target_path, "wb") as handle:
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total)

            if not verify_file_checksum(target_path, expected_sha256):
                raise RuntimeError("Downloaded update failed checksum verification")
            return target_path
        except Exception as exc:
            last_error = exc
            if os.path.isfile(target_path):
                try:
                    os.remove(target_path)
                except OSError:
                    pass
            if attempt < attempts:
                delay = max(0.0, float(retry_backoff)) * attempt
                time.sleep(delay)

    raise RuntimeError(f"Failed to download update asset: {last_error}")


def launch_windows_installer(path):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
        return

    if sys.platform.startswith("linux"):
        current_mode = os.stat(path).st_mode
        os.chmod(path, current_mode | stat.S_IXUSR)
        subprocess.Popen([path])
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
        return

    raise RuntimeError(f"Unsupported platform for installer launch: {sys.platform}")


def open_release_page(url):
    if url:
        webbrowser.open(url)
