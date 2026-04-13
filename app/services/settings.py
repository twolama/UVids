import json
import os


DEFAULT_SETTINGS = {
    "theme": "light",
}


def _settings_dir():
    home = os.path.expanduser("~")
    if os.name == "nt":
        base = os.getenv("APPDATA", home)
        return os.path.join(base, "UVidsDownloader")
    return os.path.join(home, ".config", "uvids_downloader")


def settings_path():
    return os.path.join(_settings_dir(), "settings.json")


def load_settings():
    merged = dict(DEFAULT_SETTINGS)
    path = settings_path()
    if not os.path.exists(path):
        return merged

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return merged

    if isinstance(data, dict):
        for key, value in data.items():
            if key in merged:
                merged[key] = value
    return merged


def save_settings(settings):
    payload = dict(DEFAULT_SETTINGS)
    if isinstance(settings, dict):
        payload.update({k: v for k, v in settings.items() if k in payload})

    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
