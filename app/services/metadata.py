import os
import re
import shutil
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
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError(f"yt-dlp is not available: {exc}") from exc

    ydl_opts: dict[str, Any] = {
        "logger": _YTDLPLogger(),
        "quiet": True,
        "no_warnings": True,
        "no_color": True,
        "ignoreerrors": False,
        "socket_timeout": 25,
        "retries": 5,
        "extractor_retries": 3,
        "source_address": "0.0.0.0",
        "http_headers": {
            **WEB_HEADERS,
            "Referer": url,
        },
    }
    js_runtimes = _metadata_js_runtime_opts()
    if js_runtimes:
        ydl_opts["js_runtimes"] = js_runtimes
    ydl_opts.update(_metadata_cookie_opts())

    try:
        with YoutubeDL(cast(Any, ydl_opts)) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return info
    except Exception:
        pass

    fallback = _extract_html_preview(url)
    if fallback:
        return fallback

    raise RuntimeError("No metadata returned for URL")
