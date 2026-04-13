import os
import shutil
import sys


from app.core.utils import resource_path


def _bundled_ffmpeg_candidates():
    if sys.platform == "win32":
        return [
            os.path.join("assets", "ffmpeg", "win", "ffmpeg.exe"),
            os.path.join("app", "assets", "ffmpeg", "win", "ffmpeg.exe"),
        ]
    return [
        os.path.join("assets", "ffmpeg", "linux", "ffmpeg"),
        os.path.join("app", "assets", "ffmpeg", "linux", "ffmpeg"),
    ]


def get_ffmpeg_path():
    for candidate in _bundled_ffmpeg_candidates():
        bundled = resource_path(candidate)
        if os.path.exists(bundled):
            return bundled

    return shutil.which("ffmpeg")


def get_ffmpeg_dir():
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        return None
    return os.path.dirname(ffmpeg_path)
