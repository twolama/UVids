import os
import shutil
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


def fetch_metadata(url):
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed") from exc

    ydl_opts: dict[str, Any] = {
        "logger": _YTDLPLogger(),
        "quiet": True,
        "no_warnings": True,
        "no_color": True,
        "extract_flat": "in_playlist",
        "ignoreerrors": True,
        "socket_timeout": 25,
        "retries": 5,
        "extractor_retries": 3,
        "source_address": "0.0.0.0",
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        },
    }
    js_runtimes = _metadata_js_runtime_opts()
    if js_runtimes:
        ydl_opts["js_runtimes"] = js_runtimes
    ydl_opts.update(_metadata_cookie_opts())
    with YoutubeDL(cast(Any, ydl_opts)) as ydl:
        return ydl.extract_info(url, download=False)
