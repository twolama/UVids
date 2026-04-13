import logging
import os
import shutil


LOGGER = logging.getLogger(__name__)
DEFAULT_MAX_NETWORK_ATTEMPTS = 4


class _YTDLPLogger:
    """Minimal yt-dlp logger that forwards messages into Python logging.

    This keeps yt-dlp from writing raw extractor errors directly to stderr,
    which makes failures look like terminal crashes even when they are handled.
    """

    def __init__(self, debug=False):
        self._debug_enabled = debug

    def debug(self, msg):
        LOGGER.debug(msg)

    def info(self, msg):
        LOGGER.info(msg)

    def warning(self, msg):
        text = str(msg)
        if not self._debug_enabled and "No supported JavaScript runtime could be found" in text:
            return
        if not self._debug_enabled and "YouTube extraction without a JS runtime has been deprecated" in text:
            return
        if self._debug_enabled:
            LOGGER.warning(msg)

    def error(self, msg):
        LOGGER.error(msg)


def _build_cookie_config(cookie_browser=None, cookie_file=None):
    """Build yt-dlp cookie options from args or environment values."""
    browser = cookie_browser or os.getenv("UVIDS_COOKIES_BROWSER", "").strip()
    browser_profile = os.getenv("UVIDS_COOKIES_PROFILE", "").strip()
    file_path = cookie_file or os.getenv("UVIDS_COOKIES_FILE", "").strip()

    cookie_opts = {}
    if browser:
        cookie_opts["cookiesfrombrowser"] = (
            browser,
            browser_profile,
            None,
            None,
        )
    if file_path and os.path.isfile(file_path):
        cookie_opts["cookiefile"] = file_path
    return cookie_opts


def _build_js_runtime_config():
    """Return yt-dlp js_runtimes values from env or installed executables.

    yt-dlp can use Node, Deno, Bun, or QuickJS for YouTube's JS challenge flow.
    We prefer explicitly configured runtimes, then auto-detect installed ones.
    """
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

    detected = {}
    runtime_names = ("deno", "node", "bun", "quickjs", "qjs")
    for runtime_name in runtime_names:
        executable = shutil.which(runtime_name)
        if executable:
            if runtime_name == "qjs":
                detected["quickjs"] = {"path": executable}
            else:
                detected[runtime_name] = {"path": executable}

    return detected


def create_download_options(
    download_type,
    quality_value,
    ffmpeg_available,
    ffmpeg_location,
    outtmpl,
    use_playlist,
    progress_hook,
    max_retries=None,
    force_ipv4=False,
    debug=False,
    cookie_browser=None,
    cookie_file=None,
):
    """Create production-hardened yt-dlp options with network resilience defaults."""
    retry_count = max_retries
    if retry_count is None:
        retry_count = int(os.getenv("UVIDS_DOWNLOAD_RETRIES", "8"))

    concurrent_fragments = int(os.getenv("UVIDS_CONCURRENT_FRAGMENT_DOWNLOADS", "4"))
    concurrent_fragments = max(1, min(16, concurrent_fragments))

    speed_mode = os.getenv("UVIDS_DOWNLOAD_SPEED", "fast").strip().lower()
    fast_mode = speed_mode != "stable"

    if fast_mode:
        retry_sleep_http = lambda n: min(3, 0.5 + (n * 0.25))
        retry_sleep_fragment = lambda n: min(2, 0.25 + (n * 0.25))
        retry_sleep_extractor = lambda n: min(2, 0.5 + (n * 0.25))
    else:
        retry_sleep_http = lambda n: min(10, 1 + n)
        retry_sleep_fragment = lambda n: min(8, 1 + n)
        retry_sleep_extractor = lambda n: min(6, 1 + n)

    user_agent = os.getenv(
        "UVIDS_USER_AGENT",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
    )
    js_runtimes = _build_js_runtime_config()

    ydl_opts = {
        "outtmpl": outtmpl,
        "progress_hooks": [progress_hook],
        "logger": _YTDLPLogger(debug=debug),
        "noplaylist": not use_playlist,
        "quiet": not debug,
        "no_warnings": not debug,
        "no_color": True,
        "verbose": bool(debug),
        "socket_timeout": 35,
        "retries": retry_count,
        "fragment_retries": max(15, retry_count * 2),
        "extractor_retries": max(5, retry_count),
        "file_access_retries": 5,
        "retry_sleep_functions": {
            "http": retry_sleep_http,
            "fragment": retry_sleep_fragment,
            "extractor": retry_sleep_extractor,
        },
        "continuedl": True,
        "concurrent_fragment_downloads": concurrent_fragments,
        "restrictfilenames": True,
        "windows_filenames": True,
        "ignoreerrors": True,
        "http_headers": {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Mode": "navigate",
        },
    }

    if js_runtimes:
        ydl_opts["js_runtimes"] = js_runtimes

    if force_ipv4:
        ydl_opts["source_address"] = "0.0.0.0"

    if ffmpeg_location:
        ydl_opts["ffmpeg_location"] = ffmpeg_location

    ydl_opts.update(_build_cookie_config(cookie_browser=cookie_browser, cookie_file=cookie_file))

    if download_type == "audio":
        ydl_opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
        )
    else:
        if not ffmpeg_available:
            ydl_opts["format"] = (
                f"best[ext=mp4][height<={quality_value}]/best[height<={quality_value}]/best"
                if quality_value != "best"
                else "best[ext=mp4]/best"
            )
        else:
            ydl_opts["format"] = (
                f"bestvideo[ext=mp4][height<={quality_value}]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={quality_value}]+bestaudio/"
                f"best[ext=mp4][height<={quality_value}]/best[height<={quality_value}]/best"
                if quality_value != "best"
                else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
            )
            ydl_opts["merge_output_format"] = "mp4"
            ydl_opts["remux_video"] = "mp4"

    return ydl_opts


def _classify_download_error(message):
    text = (message or "").lower()

    if (
        "failed to resolve" in text
        or "name or service not known" in text
        or "getaddrinfo failed" in text
        or "temporary failure in name resolution" in text
        or "nodename nor servname provided" in text
    ):
        return (
            "dns_failure",
            "Unable to resolve the video host. Your internet connection or DNS appears offline.",
        )

    if "network is unreachable" in text or "no route to host" in text:
        return (
            "offline",
            "No network route is available. Check your internet connection and retry.",
        )

    if "handshake operation timed out" in text or "_ssl.c:" in text:
        return (
            "ssl_timeout",
            "Secure connection timed out while handshaking with the site. "
            "This often means unstable network, blocked TLS traffic, or anti-bot filtering.",
        )
    if "ssl" in text and "timeout" in text and "handshake" in text:
        return (
            "ssl_timeout",
            "Secure connection timed out while handshaking with the site. "
            "This often means unstable network, blocked TLS traffic, or anti-bot filtering.",
        )
    if "timed out" in text or "transporterror" in text or "connection reset" in text:
        return (
            "network_timeout",
            "Network timeout while downloading. The connection appears unstable.",
        )
    if "geo" in text and "restricted" in text:
        return (
            "geo_blocked",
            "This content is geo-restricted in your region. Try a VPN or a different network.",
        )
    if "http error 403" in text or "forbidden" in text or "access denied" in text:
        return (
            "blocked",
            "The site denied access (403/forbidden). Cookies or a VPN may be required.",
        )
    if "unsupported url" in text or "no suitable extractor" in text:
        return (
            "extractor_failure",
            "This URL is not supported by the current extractor.",
        )
    if "unable to download webpage" in text or "unable to extract" in text:
        return (
            "extractor_failure",
            "The site changed or blocked extraction. Update yt-dlp and retry.",
        )
    if "private video" in text or "sign in" in text or "login" in text:
        return (
            "auth_required",
            "This content requires authentication. Retry using browser cookies.",
        )
    return ("unknown", "Download failed due to a network or site error.")


def _build_attempt_profiles(base_opts, max_network_attempts):
    """Return ordered attempt profiles with increasingly aggressive networking workarounds."""
    profiles = []

    def clone_opts():
        cloned = dict(base_opts)
        if "progress_hooks" in cloned and cloned["progress_hooks"] is not None:
            cloned["progress_hooks"] = list(cloned["progress_hooks"])
        return cloned

    profiles.append(("default", clone_opts()))

    if max_network_attempts >= 2:
        ipv4_opts = clone_opts()
        ipv4_opts["source_address"] = "0.0.0.0"
        ipv4_opts["socket_timeout"] = max(45, int(base_opts.get("socket_timeout", 35)))
        ipv4_opts["retries"] = max(int(base_opts.get("retries", 8)), 10)
        ipv4_opts["concurrent_fragment_downloads"] = min(
            16, max(4, int(base_opts.get("concurrent_fragment_downloads", 4)))
        )
        profiles.append(("ipv4", ipv4_opts))

    has_cookie = bool(base_opts.get("cookiefile") or base_opts.get("cookiesfrombrowser"))
    if max_network_attempts >= 3 and has_cookie:
        cookie_opts = clone_opts()
        cookie_opts["source_address"] = "0.0.0.0"
        cookie_opts["socket_timeout"] = max(50, int(base_opts.get("socket_timeout", 35)))
        cookie_opts["retries"] = max(int(base_opts.get("retries", 8)), 12)
        cookie_opts["concurrent_fragment_downloads"] = min(
            16, max(6, int(base_opts.get("concurrent_fragment_downloads", 4)))
        )
        profiles.append(("cookie_ipv4", cookie_opts))

    if max_network_attempts >= 4:
        resilient_opts = clone_opts()
        resilient_opts["source_address"] = "0.0.0.0"
        resilient_opts["socket_timeout"] = max(60, int(base_opts.get("socket_timeout", 35)))
        resilient_opts["retries"] = max(int(base_opts.get("retries", 8)), 15)
        resilient_opts["fragment_retries"] = max(int(base_opts.get("fragment_retries", 15)), 25)
        resilient_opts["concurrent_fragment_downloads"] = min(
            16, max(8, int(base_opts.get("concurrent_fragment_downloads", 4)))
        )
        profiles.append(("resilient", resilient_opts))

    return profiles[: max(1, max_network_attempts)]


def run_download(url, ydl_opts, max_network_attempts=None, debug=False):
    """Run download with fallback profiles and user-friendly error mapping."""
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError(f"yt-dlp is not available: {exc}") from exc

    if max_network_attempts is None:
        max_network_attempts = int(
            os.getenv("UVIDS_MAX_NETWORK_ATTEMPTS", str(DEFAULT_MAX_NETWORK_ATTEMPTS))
        )
    max_network_attempts = max(1, min(6, int(max_network_attempts)))

    if debug and not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO)

    attempts = _build_attempt_profiles(ydl_opts, max_network_attempts=max_network_attempts)
    errors = []

    for index, (profile_name, opts) in enumerate(attempts, start=1):
        try:
            LOGGER.info("Download attempt %s/%s using profile=%s", index, len(attempts), profile_name)
            with YoutubeDL(opts) as ydl:
                ydl.download([url])
            return
        except Exception as exc:
            raw_error = str(exc)
            error_code, friendly = _classify_download_error(raw_error)
            errors.append((profile_name, error_code, friendly, raw_error))
            LOGGER.warning(
                "Attempt %s failed profile=%s code=%s error=%s",
                index,
                profile_name,
                error_code,
                raw_error,
            )

            # Avoid futile retries for unsupported URLs or extractor-level hard failures.
            if error_code in {"extractor_failure", "auth_required"} and profile_name != "default":
                break

    if not errors:
        raise RuntimeError("Download failed for unknown reason")

    last_profile, last_code, last_friendly, _last_raw = errors[-1]
    detail = f"Final profile: {last_profile}. Attempts: {len(errors)}."

    if last_code in {"geo_blocked", "blocked"}:
        raise RuntimeError(f"{last_friendly}\n\nSuggestion: enable VPN/proxy or provide cookies. {detail}")
    if last_code == "ssl_timeout":
        raise RuntimeError(
            f"{last_friendly}\n\nMitigations tried: IPv4 fallback, higher timeout, retry backoff. {detail}"
        )
    if last_code in {"dns_failure", "offline"}:
        raise RuntimeError(
            f"{last_friendly}\n\nPlease reconnect to the internet and try again. {detail}"
        )
    if last_code == "network_timeout":
        raise RuntimeError(f"{last_friendly}\n\nMitigations tried: retry/backoff and resilient profile. {detail}")

    raise RuntimeError(f"{last_friendly} {detail}")
