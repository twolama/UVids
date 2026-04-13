import os
import re
import sys


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def format_time(seconds):
    if seconds < 0:
        seconds = 0
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"


def format_size(bytes_val):
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} TB"


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip(". ") or "download"


def truncate_for_windows(folder, ext="mp4", max_total=240):
    reserved = len(folder) + len(ext) + 10
    room = max(30, max_total - reserved)
    return f"%(title).{room}s.%(ext)s"
