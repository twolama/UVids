import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import urllib.request
from typing import Any, cast


class _YTDLPLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


WEB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _metadata_cookie_opts():
    opts = {}
    browser = os.getenv("UVIDS_COOKIES_BROWSER", "").strip()
    profile = os.getenv("UVIDS_COOKIES_PROFILE", "").strip()
    cookie_file = os.getenv("UVIDS_COOKIES_FILE", "").strip()

    if browser:
        opts["cookiesfrombrowser"] = (browser, profile, None, None)
    if cookie_file and os.path.isfile(cookie_file):
        opts["cookiefile"] = cookie_file
    return opts


def _metadata_js_runtime_opts():
    configured = os.getenv("UVIDS_JS_RUNTIMES", "").strip()
    if configured:
        runtimes = {}
        for item in configured.split(","):
            runtime_spec = item.strip()
            if not runtime_spec:
                continue
            runtime_name, runtime_path = (runtime_spec.split(":", 1) + [""])[:2]
            runtime_name = runtime_name.strip().lower()
            if runtime_name == "qjs":
                runtime_name = "quickjs"
            runtime_config = {}
            runtime_path = runtime_path.strip()
            if runtime_path:
                runtime_config["path"] = runtime_path
            runtimes[runtime_name] = runtime_config
        return runtimes

    runtimes = {}
    for runtime_name in ("deno", "node", "bun", "quickjs", "qjs"):
        executable = shutil.which(runtime_name)
        if executable:
            if runtime_name == "qjs":
                runtimes["quickjs"] = {"path": executable}
            else:
                runtimes[runtime_name] = {"path": executable}
    return runtimes


def _extract_html_preview(url):
    request = urllib.request.Request(
        url,
        headers={
            **WEB_HEADERS,
            "Referer": url,
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        html = response.read().decode("utf-8", errors="ignore")

    def pick(patterns):
        for pattern in patterns:
            match = re.search(pattern, html, re.I | re.S)
            if match:
                value = match.group(1).strip()
                if value:
                    return value
        return None

    title = pick(
        [
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\']([^"\']+)["\']',
            r'<title[^>]*>([^<]+)</title>',
        ]
    )
    thumbnail = pick(
        [
            r'<meta[^>]+property=["\']og:image(?:[:\w-]*)?["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image(?:[:\w-]*)?["\'][^>]+content=["\']([^"\']+)["\']',
        ]
    )
    description = pick(
        [
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        ]
    )

    if title or thumbnail or description:
        return {
            "title": title or url,
            "thumbnail": thumbnail,
            "thumbnails": [{"url": thumbnail}] if thumbnail else [],
            "description": description,
            "webpage_url": url,
            "original_url": url,
            "url": url,
            "extractor": "webpage",
        }
    return None


def fetch_metadata(url):
    """
    Fetch video/playlist metadata with smart extraction strategy.
    - Playlists: Use extract_flat for fast loading (metadata only, ~3-5s)
    - Videos: Use full extraction for detailed info (~2-5s)
    """
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError(f"yt-dlp is not available: {exc}") from exc

    # Detect if URL is likely a playlist
    is_playlist_url = (
        "playlist?list=" in url or "&list=" in url or "/playlist" in url
    )
    
    # Base options for metadata-only extraction.
    base_opts: dict[str, Any] = {
        "logger": _YTDLPLogger(),
        "quiet": True,
        "no_warnings": True,
        "no_color": True,
        "ignoreerrors": False,
        "socket_timeout": 12,
        "retries": 1,
        "extractor_retries": 1,
        "http_headers": {
            **WEB_HEADERS,
            "Referer": url,
        },
        "noplaylist": False,
    }

    fast_opts = dict(base_opts)
    if is_playlist_url:
        # Fast playlist metadata path: do not resolve every video deeply.
        fast_opts["extract_flat"] = "in_playlist"

    full_opts = dict(base_opts)

    js_runtimes = _metadata_js_runtime_opts()
    if js_runtimes:
        fast_opts["js_runtimes"] = js_runtimes
        full_opts["js_runtimes"] = js_runtimes
    cookie_opts = _metadata_cookie_opts()
    fast_opts.update(cookie_opts)
    full_opts.update(cookie_opts)

    default_timeout = 14 if is_playlist_url else 10
    timeout_seconds = int(os.getenv("UVIDS_METADATA_TIMEOUT", str(default_timeout)))

    def _extract_with_opts(opts):
        with YoutubeDL(cast(Any, opts)) as ydl:
            return ydl.extract_info(url, download=False)

    def _run_with_timeout(opts, timeout):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_extract_with_opts, opts)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise RuntimeError(f"metadata request timed out after {timeout}s") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    errors = []
    attempts = [("fast", fast_opts, timeout_seconds)]

    # For playlists, fall back to a deeper extraction if fast mode fails.
    if is_playlist_url:
        attempts.append(("full", full_opts, max(timeout_seconds, 18)))

    for label, opts, timeout in attempts:
        try:
            info = _run_with_timeout(opts, timeout)
            if info:
                return info
            errors.append(f"{label} attempt returned no metadata")
        except Exception as exc:
            errors.append(f"{label} attempt failed: {exc}")

    try:
        fallback = _extract_html_preview(url)
        if fallback:
            return fallback
    except Exception:
        pass

    tail = "; ".join(errors[-2:]) if errors else "unknown metadata failure"
    raise RuntimeError(f"Failed to fetch metadata: {tail}")
