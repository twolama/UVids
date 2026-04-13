import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import importlib
from io import BytesIO
from tkinter import filedialog, messagebox, ttk

import urllib.request
from PIL import Image, ImageTk

from app import __version__
from app.core.downloader import create_download_options, run_download
from app.core.ffmpeg import get_ffmpeg_dir, get_ffmpeg_path
from app.core.utils import (
    format_size,
    format_time,
    resource_path,
    sanitize_filename,
    truncate_for_windows,
)
from app.services.metadata import fetch_metadata
from app.services.settings import load_settings, save_settings
from app.services.updater import (
    check_latest_release,
    download_asset,
    launch_windows_installer,
    open_release_page,
)
from app.ui.components import create_modern_button, update_button_theme


THUMBNAIL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


THEMES = {
    "light": {
        "bg": "#f0f0f0",
        "surface": "#ffffff",
        "surface_lighter": "#fafafa",
        "accent": "#2196F3",
        "accent_hover": "#1976D2",
        "accent_active": "#0D47A1",
        "warning": "#FF9800",
        "error": "#F44336",
        "error_hover": "#D32F2F",
        "text": "#212121",
        "text_secondary": "#757575",
        "success": "#4CAF50",
        "border": "#e0e0e0",
        "toolbar_bg": "#e9edf1",
        "toolbar_button": "#607D8B",
        "toolbar_button_hover": "#455A64",
        "neutral_button": "#757575",
        "neutral_button_hover": "#616161",
    },
    "dark": {
        "bg": "#1e1f22",
        "surface": "#2b2d31",
        "surface_lighter": "#353841",
        "accent": "#4FC3F7",
        "accent_hover": "#29B6F6",
        "accent_active": "#03A9F4",
        "warning": "#FFB74D",
        "error": "#EF5350",
        "error_hover": "#E53935",
        "text": "#ECEFF1",
        "text_secondary": "#B0BEC5",
        "success": "#66BB6A",
        "border": "#42464f",
        "toolbar_bg": "#22242a",
        "toolbar_button": "#546E7A",
        "toolbar_button_hover": "#455A64",
        "neutral_button": "#5f6368",
        "neutral_button_hover": "#4d5156",
    },
    "ocean": {
        "bg": "#eaf4f8",
        "surface": "#ffffff",
        "surface_lighter": "#f4fbff",
        "accent": "#0077b6",
        "accent_hover": "#005f91",
        "accent_active": "#004d76",
        "warning": "#ff9f1c",
        "error": "#d62828",
        "error_hover": "#b72222",
        "text": "#102a43",
        "text_secondary": "#486581",
        "success": "#2a9d8f",
        "border": "#c8d8e4",
        "toolbar_bg": "#dff0f7",
        "toolbar_button": "#3f72af",
        "toolbar_button_hover": "#2e5f98",
        "neutral_button": "#6c757d",
        "neutral_button_hover": "#5c636a",
    },
}


class UniversalVideoDownloader:
    def __init__(self):
        self.settings = load_settings()
        self.theme_name = self.settings.get("theme", "light")
        if self.theme_name not in THEMES:
            self.theme_name = "light"
        self.colors = dict(THEMES[self.theme_name])

        self.root = tk.Tk()
        self.root.title("UVids Downloader")
        self.root.geometry("900x540")
        self.root.minsize(800, 520)
        self.root.configure(bg=self.colors["bg"])
        self._apply_app_icon()

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.setup_styles()

        self.url_var = tk.StringVar()
        self.download_type = tk.StringVar(value="video")
        self.quality_var = tk.StringVar(value="1080p")
        self.playlist_var = tk.BooleanVar(value=False)
        self.is_downloading = False
        self.cancel_entire = False
        self.skip_current = False
        self.current_info = None
        self.playlist_detected = False
        self.thumbnail_image = None
        self.url_timer = None

        self.download_start_time = 0
        self.total_bytes_downloaded = 0
        self.last_bytes = 0
        self.last_time = 0
        self.current_speed = 0
        self.remaining_bytes = 0
        self.last_percent = 0

        self.total_videos = 0
        self.completed_videos = 0
        self.current_video_index = 0
        self.video_left_count = 0
        self.current_video_size = 0
        self.last_percent = 0
        self.last_download_folder = None

        self.ffmpeg_path = get_ffmpeg_path()
        self.ffmpeg_dir = get_ffmpeg_dir()
        self.ffmpeg_available = bool(self.ffmpeg_path)
        self.update_in_progress = False
        if self.ffmpeg_dir and self.ffmpeg_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = f"{os.environ.get('PATH', '')}{os.pathsep}{self.ffmpeg_dir}"

        self.quality_options = {
            "Best (highest)": "best",
            "2160p (4K)": "2160",
            "1440p (2K)": "1440",
            "1080p": "1080",
            "720p": "720",
            "480p": "480",
            "360p": "360",
            "240p": "240",
            "144p": "144",
        }

        self._verify_dependencies()
        self.create_ui()
        self.setup_url_trace()

    def _verify_dependencies(self):
        try:
            importlib.import_module("yt_dlp")
        except ModuleNotFoundError as exc:
            self.root.withdraw()
            if getattr(sys, "frozen", False):
                message = (
                    "Bundled yt-dlp is missing from this build.\n\n"
                    "Rebuild after installing requirements in the build environment:\n"
                    "  python -m pip install -r requirements.txt"
                )
            else:
                message = (
                    "yt-dlp is not installed for this Python environment.\n\n"
                    "Run:\n"
                    "  python -m pip install -r requirements.txt"
                )
            if getattr(exc, "name", None) not in (None, "yt_dlp"):
                message += f"\n\nImport error: {exc}"
            messagebox.showerror("Missing Dependency", message)
            raise SystemExit(1)
        except Exception as exc:
            self.root.withdraw()
            messagebox.showerror(
                "Dependency Error",
                "yt-dlp failed to load in this environment.\n\n"
                f"Details: {exc}\n\n"
                "Try:\n"
                "  python -m pip install -r requirements.txt",
            )
            raise SystemExit(1)

    def _apply_app_icon(self):
        icon_candidates = [
            os.path.join("assets", "icons", "uvids.ico"),
            os.path.join("app", "assets", "icons", "uvids.ico"),
        ]
        for icon_rel in icon_candidates:
            icon_path = resource_path(icon_rel)
            if os.path.isfile(icon_path):
                try:
                    self.root.iconbitmap(icon_path)
                    return
                except Exception:
                    continue

    def setup_styles(self):
        default_font = ("Segoe UI", 9)
        heading_font = ("Segoe UI", 10, "bold")

        self.style.configure(".", font=default_font, background=self.colors["bg"])
        self.style.configure("TFrame", background=self.colors["bg"])
        self.style.configure("Toolbar.TFrame", background=self.colors["toolbar_bg"])
        self.style.configure(
            "Card.TFrame", background=self.colors["surface"], relief="solid", borderwidth=1
        )
        self.style.configure(
            "TLabel", background=self.colors["bg"], foreground=self.colors["text_secondary"]
        )
        self.style.configure(
            "Header.TLabel",
            font=heading_font,
            foreground=self.colors["text"],
            background=self.colors["surface"],
        )
        self.style.configure(
            "ToolbarTitle.TLabel",
            font=heading_font,
            foreground=self.colors["text"],
            background=self.colors["toolbar_bg"],
        )
        self.style.configure(
            "Accent.TLabel",
            foreground=self.colors["accent"],
            background=self.colors["surface"],
            font=("Segoe UI", 8),
        )
        self.style.configure(
            "TEntry",
            fieldbackground=self.colors["surface"],
            foreground=self.colors["text"],
            insertcolor=self.colors["text"],
            padding=6,
        )
        self.style.map(
            "TEntry",
            fieldbackground=[("focus", self.colors["surface"])],
            foreground=[("focus", self.colors["text"])],
        )
        self.style.configure(
            "TCombobox",
            padding=4,
            fieldbackground=self.colors["surface"],
            foreground=self.colors["text"],
            background=self.colors["surface"],
            arrowcolor=self.colors["text"],
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.colors["surface"]), ("focus", self.colors["surface"])],
            foreground=[("readonly", self.colors["text"]), ("focus", self.colors["text"])],
            selectbackground=[("readonly", self.colors["surface"])],
            selectforeground=[("readonly", self.colors["text"])],
            background=[("active", self.colors["surface_lighter"]), ("readonly", self.colors["surface"])],
            arrowcolor=[("readonly", self.colors["text"]), ("active", self.colors["text"])],
        )
        self.style.configure(
            "TRadiobutton", background=self.colors["bg"], foreground=self.colors["text"]
        )
        self.style.map(
            "TRadiobutton",
            foreground=[
                ("disabled", self.colors["text_secondary"]),
                ("active", self.colors["text"]),
                ("selected", self.colors["accent"]),
                ("!selected", self.colors["text"]),
            ],
            background=[("active", self.colors["bg"])],
        )
        self.style.configure(
            "TCheckbutton",
            background=self.colors["bg"],
            foreground=self.colors["text"],
            focuscolor="",
            font=("Segoe UI", 9, "bold"),
        )
        self.style.map(
            "TCheckbutton",
            foreground=[
                ("disabled", self.colors["text_secondary"]),
                ("active", self.colors["text"]),
                ("selected", self.colors["accent"]),
            ],
            background=[("selected", self.colors["bg"])],
        )
        self.style.configure(
            "TProgressbar",
            background=self.colors["accent"],
            troughcolor=self.colors["border"],
            thickness=5,
        )

        # Keep popdown list and text-cursor colors readable on dark/light themes.
        self.root.option_add("*TCombobox*Listbox*Background", self.colors["surface"])
        self.root.option_add("*TCombobox*Listbox*Foreground", self.colors["text"])
        self.root.option_add("*TCombobox*Listbox*selectBackground", self.colors["accent"])
        self.root.option_add("*TCombobox*Listbox*selectForeground", "white")
        self.root.option_add("*Entry*insertBackground", self.colors["text"])
        self.root.option_add("*TEntry*insertBackground", self.colors["text"])
        self.root.option_add("*Text*insertBackground", self.colors["text"])

    def create_ui(self):
        self.create_menu_bar()

        main = ttk.Frame(self.root, padding="10")
        main.pack(fill="both", expand=True)
        self.main_frame = main

        top_frame = ttk.Frame(main, style="Toolbar.TFrame")
        top_frame.pack(fill="x", pady=(0, 10))
        top_frame.columnconfigure(0, weight=1)
        top_frame.columnconfigure(2, weight=1)
        ttk.Label(top_frame, text="URL:", style="ToolbarTitle.TLabel").grid(
            row=0, column=0, padx=(0, 5), sticky="e"
        )
        self.url_entry = ttk.Entry(top_frame, textvariable=self.url_var, width=60)
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=5, ipady=4)
        self._apply_entry_cursor_theme(self.url_entry)
        self.load_btn = create_modern_button(
            top_frame,
            text="Load Info",
            command=self.fetch_info_manual,
            bg=self.colors["toolbar_button"],
            hover=self.colors["toolbar_button_hover"],
            fg="white",
        )
        self.load_btn.grid(row=0, column=2, padx=(5, 0))
        top_frame.columnconfigure(1, weight=1)

        paned = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, pady=(0, 10))

        left_frame = ttk.Frame(paned, width=240)
        paned.add(left_frame, weight=0)
        left_frame.pack_propagate(False)

        type_card = ttk.Frame(left_frame, style="Card.TFrame")
        type_card.pack(fill="x", pady=(0, 10))
        ttk.Label(type_card, text="Download Type", style="Header.TLabel").pack(
            anchor="w", padx=10, pady=(8, 5)
        )
        type_inner = ttk.Frame(type_card)
        type_inner.pack(fill="x", padx=10, pady=(0, 8))
        self.video_rb = ttk.Radiobutton(
            type_inner,
            text="Video",
            variable=self.download_type,
            value="video",
            command=self.toggle_quality,
        )
        self.video_rb.pack(side="left", padx=(0, 20))
        self.audio_rb = ttk.Radiobutton(
            type_inner,
            text="Audio",
            variable=self.download_type,
            value="audio",
            command=self.toggle_quality,
        )
        self.audio_rb.pack(side="left")
        if not self.ffmpeg_available:
            self.audio_rb.config(state="disabled")
            self.download_type.set("video")

        self.quality_card = ttk.Frame(left_frame, style="Card.TFrame")
        ttk.Label(self.quality_card, text="Quality Settings", style="Header.TLabel").pack(
            anchor="w", padx=10, pady=(8, 5)
        )
        qual_inner = ttk.Frame(self.quality_card)
        qual_inner.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(qual_inner, text="Quality:").pack(side="left", padx=(0, 10))
        quality_keys = list(self.quality_options.keys())
        self.quality_combo = ttk.Combobox(
            qual_inner,
            textvariable=self.quality_var,
            values=quality_keys,
            state="readonly",
            width=16,
        )
        self.quality_combo.current(quality_keys.index("1080p") if "1080p" in quality_keys else 0)
        self.quality_combo.pack(side="left")
        if not self.ffmpeg_available:
            allowed = [
                k for k, v in self.quality_options.items() if v in ["720", "480", "360", "240", "144"]
            ]
            self.quality_combo.config(values=allowed)
            if "720p" in allowed:
                self.quality_var.set("720p")
        self.quality_card.pack(fill="x", pady=(0, 10))

        self.playlist_card = ttk.Frame(left_frame, style="Card.TFrame")
        self.playlist_cb = ttk.Checkbutton(
            self.playlist_card,
            text="Download entire playlist",
            variable=self.playlist_var,
            style="TCheckbutton",
        )
        self.playlist_cb.pack(anchor="w", padx=10, pady=8)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill="x", pady=(15, 0))

        self.download_btn = create_modern_button(
            btn_frame,
            text="START DOWNLOAD",
            command=self.start_download,
            bg=self.colors["accent"],
            hover=self.colors["accent_hover"],
            fg="white",
            active_bg=self.colors["accent_active"],
        )
        self.download_btn.pack(fill="x", pady=(0, 8))

        self.cancel_btn = create_modern_button(
            btn_frame,
            text="CANCEL",
            command=self.cancel_download_action,
            bg=self.colors["error"],
            hover=self.colors["error_hover"],
            fg="white",
            hover_fg="white",
            active_fg="white",
            state="disabled",
        )
        self.cancel_btn.pack(fill="x", pady=(0, 8))

        self.exit_btn = create_modern_button(
            btn_frame,
            text="EXIT",
            command=self.root.quit,
            bg=self.colors["neutral_button"],
            hover=self.colors["neutral_button_hover"],
            fg="white",
        )
        self.exit_btn.pack(fill="x")

        right_frame = ttk.Frame(paned, style="Card.TFrame")
        paned.add(right_frame, weight=1)

        self.thumbnail_label = ttk.Label(right_frame, text="No video loaded", anchor="center")
        self.thumbnail_label.pack(pady=(12, 8))

        meta_frame = ttk.Frame(right_frame)
        meta_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.metadata_text = tk.Text(
            meta_frame,
            wrap="word",
            height=8,
            font=("Segoe UI", 9),
            bg=self.colors["surface"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(meta_frame, orient="vertical", command=self.metadata_text.yview)
        self.metadata_text.configure(yscrollcommand=scrollbar.set)
        self.metadata_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        progress_card = ttk.Frame(main, style="Card.TFrame")
        progress_card.pack(fill="x", pady=(0, 0))
        ttk.Label(progress_card, text="Download Progress", style="Header.TLabel").pack(
            anchor="w", padx=10, pady=(8, 5)
        )

        self.status_label = ttk.Label(progress_card, text="Ready", style="Accent.TLabel")
        self.status_label.pack(anchor="w", padx=10, pady=(0, 5))

        self.progress_bar = ttk.Progressbar(progress_card, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", padx=10, pady=(0, 5))

        self.percent_label = tk.Label(
            progress_card,
            text="0%",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["surface"],
            fg=self.colors["accent"],
        )
        self.percent_label.pack(pady=(0, 5))

        info_frame = ttk.Frame(progress_card)
        info_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.time_label = ttk.Label(info_frame, text="Time left: --:--", style="TLabel")
        self.time_label.pack(side="left", padx=(0, 15))
        self.videos_left_label = ttk.Label(info_frame, text="Videos left: --", style="TLabel")
        self.videos_left_label.pack(side="left", padx=(0, 15))
        self.size_label = ttk.Label(info_frame, text="Size: --", style="TLabel")
        self.size_label.pack(side="left")

        footer = ttk.Label(main, text="Powered by YoYa", font=("Segoe UI", 7))
        footer.pack(pady=(8, 0))
        self.footer_label = footer

        # Overlay version text in the corner without changing pack/grid layout flow.
        self.version_label = tk.Label(
            main,
            text=f"v{__version__}",
            font=("Segoe UI", 7),
            bg=self.colors["bg"],
            fg=self.colors["text_secondary"],
        )
        self.version_label.place(relx=1.0, rely=1.0, x=-10, y=-6, anchor="se")

        self.playlist_card.pack_forget()

    def create_menu_bar(self):
        self.menu_theme_var = tk.StringVar(value=self.theme_name)

        self.menubar = tk.Menu(self.root, tearoff=0)
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.download_menu = tk.Menu(self.menubar, tearoff=0)
        self.settings_menu = tk.Menu(self.menubar, tearoff=0)
        self.theme_menu = tk.Menu(self.settings_menu, tearoff=0)
        self.help_menu = tk.Menu(self.menubar, tearoff=0)

        self.file_menu.add_command(label="Load Info", command=self.fetch_info_manual)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self.root.quit)

        self.download_menu.add_command(label="Start Download", command=self.start_download)
        self.download_menu.add_command(label="Cancel Current", command=self.cancel_download_action)

        self.theme_menu.add_radiobutton(
            label="Light",
            value="light",
            variable=self.menu_theme_var,
            command=self._apply_menu_theme,
        )
        self.theme_menu.add_radiobutton(
            label="Dark",
            value="dark",
            variable=self.menu_theme_var,
            command=self._apply_menu_theme,
        )
        self.theme_menu.add_radiobutton(
            label="Ocean",
            value="ocean",
            variable=self.menu_theme_var,
            command=self._apply_menu_theme,
        )

        self.settings_menu.add_command(label="Preferences...", command=self.open_settings_dialog)
        self.settings_menu.add_cascade(label="Theme", menu=self.theme_menu)

        self.help_menu.add_command(
            label="Check for Updates...",
            command=self.check_for_updates,
        )
        self.help_menu.add_command(
            label="Update Now",
            command=self.update_now,
        )
        self.help_menu.add_separator()
        self.help_menu.add_command(
            label="About",
            command=lambda: messagebox.showinfo(
                "About",
                f"UVids Downloader v{__version__}\n\nPowered by YoYa\n\nWebsite: https://twolama.me\n",
            ),
        )

        self.menubar.add_cascade(label="File", menu=self.file_menu)
        self.menubar.add_cascade(label="Download", menu=self.download_menu)
        self.menubar.add_cascade(label="Settings", menu=self.settings_menu)
        self.menubar.add_cascade(label="Help", menu=self.help_menu)

        self.root.config(menu=self.menubar)
        self._refresh_menu_colors()

    def _refresh_menu_colors(self):
        menus = [
            getattr(self, "menubar", None),
            getattr(self, "file_menu", None),
            getattr(self, "download_menu", None),
            getattr(self, "settings_menu", None),
            getattr(self, "theme_menu", None),
            getattr(self, "help_menu", None),
        ]
        for menu in menus:
            if menu is None:
                continue
            try:
                menu.config(
                    bg=self.colors["surface"],
                    fg=self.colors["text"],
                    activebackground=self.colors["accent"],
                    activeforeground="white",
                )
            except tk.TclError:
                # Some platforms render native menu colors and reject custom color options.
                pass

    def _apply_menu_theme(self):
        self.apply_theme(self.menu_theme_var.get(), persist=True)

    def check_for_updates(self):
        self._start_update_flow(auto_update=False)

    def update_now(self):
        self._start_update_flow(auto_update=True)

    def _start_update_flow(self, auto_update=False):
        if self.update_in_progress:
            messagebox.showinfo("Update", "An update check is already in progress.")
            return

        self.update_in_progress = True
        self.status_label.config(text="Checking for updates...", foreground=self.colors["accent"])
        threading.Thread(
            target=self._check_updates_worker,
            args=(auto_update,),
            daemon=True,
        ).start()

    def _check_updates_worker(self, auto_update):
        result = check_latest_release(__version__)
        self.root.after(0, lambda: self._handle_update_check_result(result, auto_update))

    def _handle_update_check_result(self, result, auto_update):
        if not result.get("ok"):
            self.update_in_progress = False
            self.status_label.config(text="Ready", foreground=self.colors["accent"])
            messagebox.showerror("Update", result.get("message", "Update check failed."))
            return

        if not result.get("update_available"):
            self.update_in_progress = False
            self.status_label.config(text="Ready", foreground=self.colors["accent"])
            messagebox.showinfo(
                "Update",
                f"You are up to date (v{result.get('current_version', __version__)}).",
            )
            return

        latest_version = result.get("latest_version", "latest")
        should_update = auto_update or messagebox.askyesno(
            "Update Available",
            f"Version v{latest_version} is available.\n\nInstall now?",
        )
        if not should_update:
            self.update_in_progress = False
            self.status_label.config(text="Ready", foreground=self.colors["accent"])
            return

        self.status_label.config(text="Downloading update...", foreground=self.colors["accent"])
        threading.Thread(
            target=self._download_and_launch_update,
            args=(result,),
            daemon=True,
        ).start()

    def _on_update_download_progress(self, downloaded, total):
        if total > 0:
            percent = int((downloaded * 100) / total)
            self.status_label.config(text=f"Downloading update... {percent}%", foreground=self.colors["accent"])
        else:
            self.status_label.config(
                text=f"Downloading update... {format_size(downloaded)}",
                foreground=self.colors["accent"],
            )

    def _download_and_launch_update(self, result):
        try:
            asset = result.get("asset") or {}
            release_url = result.get("release_url")
            asset_url = asset.get("url")
            asset_name = asset.get("name") or "uvids-update.bin"

            if asset_url:
                downloaded_path = download_asset(
                    asset_url,
                    asset_name,
                    progress_callback=lambda done, total: self.root.after(
                        0, self._on_update_download_progress, done, total
                    ),
                )
            else:
                downloaded_path = None

            if os.name == "nt" and downloaded_path:
                launch_windows_installer(downloaded_path)
                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Update",
                        "Installer started. The app will close so the update can continue.",
                    ),
                )
                self.root.after(500, self.root.quit)
            else:
                open_release_page(release_url or asset_url)
                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Update",
                        "Update package is ready. Opened the release page for installation instructions.",
                    ),
                )
                self.root.after(0, lambda: self.status_label.config(text="Ready", foreground=self.colors["accent"]))
        except Exception as exc:
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Update",
                    self._friendly_error_message(str(exc)),
                ),
            )
            self.root.after(0, lambda: self.status_label.config(text="Ready", foreground=self.colors["accent"]))
        finally:
            self.update_in_progress = False

    def _apply_entry_cursor_theme(self, entry_widget):
        try:
            entry_widget.tk.call(entry_widget._w, "configure", "-insertbackground", self.colors["text"])
        except tk.TclError:
            pass

    def _friendly_error_message(self, message):
        text = (message or "").lower()
        if (
            "failed to resolve" in text
            or "getaddrinfo failed" in text
            or "name or service not known" in text
            or "temporary failure in name resolution" in text
        ):
            return "No internet connection detected (DNS lookup failed). Please reconnect and try again."
        if "network is unreachable" in text or "no route to host" in text:
            return "No network route available. Please check your internet connection and try again."
        if "timed out" in text:
            return "Connection timed out. The network is unstable or the host is temporarily unavailable."
        if "remote component challenge solver" in text or "n challenge solving failed" in text:
            return (
                "Site challenge verification failed. Install a JavaScript runtime (Node/Deno) or update yt-dlp."
            )
        return message

    def apply_theme(self, theme_name, persist=False):
        if theme_name not in THEMES:
            return

        self.theme_name = theme_name
        self.colors = dict(THEMES[theme_name])
        self.root.configure(bg=self.colors["bg"])
        self.setup_styles()

        if hasattr(self, "menu_theme_var"):
            self.menu_theme_var.set(theme_name)
        self._refresh_menu_colors()

        if hasattr(self, "metadata_text"):
            self.metadata_text.config(
                bg=self.colors["surface"],
                fg=self.colors["text"],
                insertbackground=self.colors["text"],
            )
        if hasattr(self, "url_entry"):
            self._apply_entry_cursor_theme(self.url_entry)
        if hasattr(self, "percent_label"):
            self.percent_label.config(bg=self.colors["surface"], fg=self.colors["accent"])
        if hasattr(self, "version_label"):
            self.version_label.config(bg=self.colors["bg"], fg=self.colors["text_secondary"])

        if hasattr(self, "load_btn"):
            update_button_theme(
                self.load_btn,
                bg=self.colors["toolbar_button"],
                hover=self.colors["toolbar_button_hover"],
                fg="white",
            )
        if hasattr(self, "download_btn"):
            update_button_theme(
                self.download_btn,
                bg=self.colors["accent"],
                hover=self.colors["accent_hover"],
                active_bg=self.colors["accent_active"],
                fg="white",
            )
        if hasattr(self, "cancel_btn"):
            update_button_theme(
                self.cancel_btn,
                bg=self.colors["error"],
                hover=self.colors["error_hover"],
                fg="white",
                hover_fg="white",
                active_fg="white",
            )
        if hasattr(self, "exit_btn"):
            update_button_theme(
                self.exit_btn,
                bg=self.colors["neutral_button"],
                hover=self.colors["neutral_button_hover"],
                fg="white",
            )

        if persist:
            self.settings["theme"] = self.theme_name
            save_settings(self.settings)

    def open_download_location(self):
        target = self.last_download_folder
        if not target or not os.path.isdir(target):
            messagebox.showinfo("Open Folder", "No downloaded folder is available yet.")
            return

        try:
            if os.name == "nt":
                os.startfile(target)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as exc:
            messagebox.showerror("Open Folder", f"Could not open folder:\n{exc}")

    def show_success_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Success")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg=self.colors["bg"])

        self.root.update_idletasks()
        width, height = 460, 220
        x_pos = self.root.winfo_x() + (self.root.winfo_width() // 2) - (width // 2)
        y_pos = self.root.winfo_y() + (self.root.winfo_height() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{max(0, x_pos)}+{max(0, y_pos)}")

        card = tk.Frame(
            dialog,
            bg=self.colors["surface"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)

        title = tk.Label(
            card,
            text="Download Completed",
            font=("Segoe UI", 14, "bold"),
            bg=self.colors["surface"],
            fg=self.colors["text"],
        )
        title.pack(anchor="w", padx=16, pady=(14, 6))

        subtitle = tk.Label(
            card,
            text="Your file was downloaded successfully.",
            font=("Segoe UI", 10),
            bg=self.colors["surface"],
            fg=self.colors["text_secondary"],
        )
        subtitle.pack(anchor="w", padx=16)

        if self.last_download_folder and os.path.isdir(self.last_download_folder):
            path_label = tk.Label(
                card,
                text=f"Location: {self.last_download_folder}",
                font=("Consolas", 9),
                bg=self.colors["surface_lighter"],
                fg=self.colors["text"],
                anchor="w",
                padx=10,
                pady=6,
            )
            path_label.pack(fill="x", padx=16, pady=(12, 6))

        btn_row = tk.Frame(card, bg=self.colors["surface"])
        btn_row.pack(anchor="e", padx=16, pady=(8, 14))

        if self.last_download_folder and os.path.isdir(self.last_download_folder):
            open_btn = create_modern_button(
                btn_row,
                text="OPEN FOLDER",
                command=lambda: self._open_folder_and_close(dialog),
                bg=self.colors["accent"],
                hover=self.colors["accent_hover"],
                fg="white",
                active_bg=self.colors["accent_active"],
            )
            open_btn.pack(side="left", padx=(0, 8))

        done_btn = create_modern_button(
            btn_row,
            text="DONE",
            command=dialog.destroy,
            bg=self.colors["neutral_button"],
            hover=self.colors["neutral_button_hover"],
            fg="white",
        )
        done_btn.pack(side="left")

    def _open_folder_and_close(self, dialog):
        self.open_download_location()
        if dialog.winfo_exists():
            dialog.destroy()

    def open_settings_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Preferences")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.geometry("440x260")
        dialog.minsize(440, 260)
        dialog.configure(bg=self.colors["bg"])

        # Center preferences dialog over the main window.
        self.root.update_idletasks()
        x_pos = self.root.winfo_x() + (self.root.winfo_width() // 2) - 220
        y_pos = self.root.winfo_y() + (self.root.winfo_height() // 2) - 130
        dialog.geometry(f"440x260+{max(0, x_pos)}+{max(0, y_pos)}")

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Preferences", style="Header.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(
            frame,
            text="Choose your app appearance settings.",
            style="TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(0, 14))

        ttk.Label(frame, text="Theme", style="Header.TLabel").grid(row=2, column=0, sticky="w")

        theme_names = {
            "Light": "light",
            "Dark": "dark",
            "Ocean": "ocean",
        }
        reverse_names = {v: k for k, v in theme_names.items()}
        theme_var = tk.StringVar(value=reverse_names.get(self.theme_name, "Light"))

        combo = ttk.Combobox(
            frame,
            textvariable=theme_var,
            values=list(theme_names.keys()),
            state="readonly",
            width=24,
        )
        combo.grid(row=3, column=0, sticky="w", pady=(6, 18))

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=4, column=0, sticky="e")

        apply_btn = create_modern_button(
            btn_row,
            text="Apply",
            command=lambda: self._apply_preferences(dialog, theme_names.get(theme_var.get(), "light")),
            bg=self.colors["accent"],
            hover=self.colors["accent_hover"],
            fg="white",
            active_bg=self.colors["accent_active"],
        )
        apply_btn.pack(side="left", padx=(0, 6))

        close_btn = create_modern_button(
            btn_row,
            text="Close",
            command=dialog.destroy,
            bg=self.colors["neutral_button"],
            hover=self.colors["neutral_button_hover"],
            fg="white",
        )
        close_btn.pack(side="left")

    def _apply_preferences(self, dialog, theme_name):
        self.apply_theme(theme_name, persist=True)
        dialog.destroy()

    def setup_url_trace(self):
        def on_url_change(*_args):
            if self.url_timer:
                self.root.after_cancel(self.url_timer)
            self.url_timer = self.root.after(800, self.fetch_info_async)

        self.url_var.trace_add("write", on_url_change)

    def fetch_info_manual(self):
        self.fetch_info_async()

    def fetch_info_async(self):
        url = self.url_var.get().strip()
        if not url:
            return
        self.metadata_text.delete(1.0, tk.END)
        self.metadata_text.insert(tk.END, "Loading information...")
        self.thumbnail_label.config(text="Loading preview...")
        self.playlist_card.pack_forget()
        self.playlist_detected = False
        self.playlist_var.set(False)
        threading.Thread(target=self._fetch_info, args=(url,), daemon=True).start()

    def _fetch_info(self, url):
        try:
            info = fetch_metadata(url)
            if not info:
                raise ValueError("No metadata returned for URL")
            self.current_info = info
            is_playlist = "entries" in info and info["entries"] is not None
            self.playlist_detected = is_playlist
            self.root.after(0, self._update_preview, info, is_playlist)
        except Exception as exc:
            error_msg = self._friendly_error_message(str(exc))
            if "Private video" in error_msg or "Sign in" in error_msg:
                error_msg = (
                    "This video is private. You need to log in.\n\n"
                    "Workaround:\n1. Use cookies from your browser\n2. Or try a different video"
                )
            self.root.after(0, self._show_error, error_msg)

    def _update_preview(self, info, is_playlist):
        self.metadata_text.delete(1.0, tk.END)

        thumbnail_url = self._resolve_thumbnail_url(info, is_playlist)

        page_url = info.get("webpage_url") or info.get("original_url") or info.get("url")

        if thumbnail_url:
            self._load_thumbnail(thumbnail_url, page_url=page_url)
        else:
            self.thumbnail_label.config(text="No thumbnail", image="")

        if is_playlist:
            title = info.get("title", "Unknown Playlist")
            entries = info.get("entries", []) or []
            total_count = len(entries)
            available_count = sum(1 for entry in entries if entry is not None)
            meta = f"PLAYLIST: {title}\n"
            meta += f"Videos: {total_count}\n"
            if available_count != total_count:
                meta += f"Available: {available_count} (some private/unavailable)\n"
            if info.get("uploader"):
                meta += f"Uploader: {info.get('uploader')}\n"
            meta += "Size: will be shown per video during download\n"
            self.metadata_text.insert(tk.END, meta)
            self.total_videos = available_count
            self.videos_left_label.config(text=f"Videos left: {self.total_videos}")
            self.size_label.config(text="Size: per video")
            self.playlist_var.set(True)
            self.playlist_card.pack(fill="x", pady=(0, 10), before=self.download_btn.master)
        else:
            title = info.get("title", "Unknown")
            duration = info.get("duration", 0)
            if duration:
                try:
                    dur_int = int(duration)
                    duration_str = f"{dur_int // 60}:{dur_int % 60:02d}"
                except Exception:
                    duration_str = "N/A"
            else:
                duration_str = "N/A"

            uploader = info.get("uploader", "N/A")
            views = info.get("view_count", "N/A")
            if isinstance(views, (int, float)):
                views = f"{int(views):,}"
            like_count = info.get("like_count", "N/A")
            if isinstance(like_count, (int, float)):
                like_count = f"{int(like_count):,}"
            upload_date = info.get("upload_date", "")
            if upload_date and len(upload_date) == 8:
                upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

            file_size = 0
            target_quality = self.quality_options.get(self.quality_var.get(), "720")
            formats = info.get("formats", [])
            if target_quality != "best":
                for fmt in formats:
                    if fmt.get("height") == int(target_quality):
                        file_size = fmt.get("filesize", 0)
                        break
            else:
                for fmt in formats:
                    if fmt.get("filesize", 0) > file_size:
                        file_size = fmt.get("filesize", 0)
            if file_size == 0:
                file_size = info.get("filesize", 0)
            size_str = format_size(file_size) if file_size > 0 else "Unknown"

            meta = f"TITLE: {title}\n"
            meta += f"DURATION: {duration_str}\n"
            meta += f"UPLOADER: {uploader}\n"
            meta += f"VIEWS: {views}\n"
            meta += f"LIKES: {like_count}\n"
            if upload_date:
                meta += f"UPLOAD DATE: {upload_date}\n"
            meta += f"SIZE: {size_str}\n"
            self.metadata_text.insert(tk.END, meta)
            self.playlist_card.pack_forget()
            self.playlist_var.set(False)
            self.total_videos = 1
            self.videos_left_label.config(text="Videos left: 1")
            self.size_label.config(text=f"Size: {size_str}")

    def _resolve_thumbnail_url(self, info, is_playlist):
        candidates = []

        def add_candidate(value):
            if value and value not in candidates:
                candidates.append(value)

        if is_playlist:
            for thumb in info.get("thumbnails", []) or []:
                add_candidate(thumb.get("url"))
            add_candidate(info.get("thumbnail"))
            for entry in info.get("entries", []) or []:
                if not entry:
                    continue
                add_candidate(entry.get("thumbnail"))
                for thumb in entry.get("thumbnails", []) or []:
                    add_candidate(thumb.get("url"))
                if candidates:
                    break
        else:
            for thumb in info.get("thumbnails", []) or []:
                add_candidate(thumb.get("url"))
            add_candidate(info.get("thumbnail"))

        for candidate in candidates:
            if candidate:
                return candidate

        page_url = info.get("webpage_url") or info.get("original_url") or info.get("url")
        if page_url:
            og_image = self._fetch_og_image(page_url)
            if og_image:
                return og_image

        return None

    def _fetch_og_image(self, page_url):
        try:
            request = urllib.request.Request(page_url, headers={
                **THUMBNAIL_HEADERS,
                "Referer": page_url,
            })
            with urllib.request.urlopen(request, timeout=8) as response:
                html = response.read().decode("utf-8", errors="ignore")
            match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if match:
                return match.group(1)
            match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I)
            if match:
                return match.group(1)
        except Exception:
            return None
        return None

    def _load_thumbnail(self, url, page_url=None):
        try:
            headers = dict(THUMBNAIL_HEADERS)
            if page_url:
                headers["Referer"] = page_url
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=8) as response:
                img_data = response.read()
            img = Image.open(BytesIO(img_data))
            img.thumbnail((240, 150))
            self.thumbnail_image = ImageTk.PhotoImage(img)
            self.thumbnail_label.config(image=self.thumbnail_image, text="")
        except Exception:
            self.thumbnail_label.config(text="Thumbnail failed", image="")

    def _show_error(self, error_msg):
        self.metadata_text.delete(1.0, tk.END)
        self.metadata_text.insert(tk.END, f"Error loading info:\n{error_msg}")
        self.thumbnail_label.config(text="No preview")
        self.playlist_card.pack_forget()

    def toggle_quality(self):
        if self.download_type.get() == "video":
            if not self.quality_card.winfo_ismapped():
                before_widget = (
                    self.playlist_card if self.playlist_card.winfo_ismapped() else self.download_btn.master
                )
                self.quality_card.pack(fill="x", pady=(0, 10), before=before_widget)
        else:
            self.quality_card.pack_forget()

    def reset_progress_tracking(self):
        self.download_start_time = time.time()
        self.total_bytes_downloaded = 0
        self.last_bytes = 0
        self.last_time = self.download_start_time
        self.current_speed = 0
        self.remaining_bytes = 0
        self.completed_videos = 0
        self.current_video_index = 0
        self.video_left_count = self.total_videos if self.playlist_detected and self.playlist_var.get() else 1
        self.cancel_entire = False
        self.skip_current = False
        self.current_video_size = 0

    def progress_hook(self, data):
        if self.cancel_entire:
            raise Exception("Download cancelled entirely")
        if self.skip_current:
            raise Exception("Skip current video")

        if data["status"] == "downloading":
            try:
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                downloaded = data.get("downloaded_bytes", 0)
                now = time.time()

                if self.last_bytes > 0:
                    elapsed = now - self.last_time
                    if elapsed > 0:
                        byte_delta = max(0, downloaded - self.last_bytes)
                        instant_speed = byte_delta / elapsed
                        self.current_speed = self.current_speed * 0.75 + instant_speed * 0.25

                self.last_bytes = downloaded
                self.last_time = now

                if total > 0:
                    percent = int(downloaded * 100 / total)
                    percent = max(self.last_percent, min(100, percent))
                    self.last_percent = percent
                    self.remaining_bytes = total - downloaded

                    time_left_secs = 0
                    if self.current_speed > 0 and self.remaining_bytes > 0:
                        time_left_secs = self.remaining_bytes / self.current_speed
                    time_left_str = format_time(int(time_left_secs))

                    if total != self.current_video_size:
                        self.current_video_size = total
                        self.root.after(
                            0, lambda: self.size_label.config(text=f"Size: {format_size(total)}")
                        )

                    self.root.after(0, self.update_progress, percent, "Downloading...", time_left_str)
                else:
                    self.root.after(0, self.update_progress, self.last_percent, "Downloading...", "??:??")
            except Exception:
                self.root.after(0, self.update_progress, self.last_percent, "Downloading...", "??:??")

        elif data["status"] == "finished":
            self.last_percent = 100
            self.completed_videos += 1
            self.video_left_count = max(0, self.total_videos - self.completed_videos)
            self.root.after(0, self.update_videos_left)
            self.root.after(0, self.update_progress, 100, "Processing...", "Finalizing")

        elif data["status"] == "error":
            self.root.after(0, self.update_progress, 0, "Error occurred", "N/A")

    def update_videos_left(self):
        self.videos_left_label.config(text=f"Videos left: {self.video_left_count}")

    def update_progress(self, percent, text, time_left=None):
        self.progress_bar["value"] = percent
        self.percent_label.config(text=f"{percent}%")
        self.status_label.config(text=text)
        if time_left:
            self.time_label.config(text=f"Time left: {time_left}")

    def cancel_download_action(self):
        result = messagebox.askquestion(
            "Cancel Download",
            "What would you like to cancel?\n\n"
            "Yes = Cancel current video only (skip to next)\n"
            "No = Cancel entire download",
            icon="question",
        )
        if result == "yes":
            self.skip_current = True
            self.status_label.config(text="Skipping current video...", foreground=self.colors["warning"])
            self.cancel_btn.config(state="disabled")
        else:
            self.cancel_entire = True
            self.status_label.config(
                text="Cancelling entire download...", foreground=self.colors["warning"]
            )
            self.cancel_btn.config(state="disabled")

    def finish_download(self, success=True, msg=""):
        self.is_downloading = False
        self.download_btn.config(state="normal", text="START DOWNLOAD")
        self.cancel_btn.config(state="disabled")

        if success and not self.cancel_entire and not self.skip_current:
            self.status_label.config(text="Completed", foreground=self.colors["success"])
            self.progress_bar["value"] = 0
            self.percent_label.config(text="0%")
            self.time_label.config(text="Time left: 00:00")
            self.videos_left_label.config(text="Videos left: 0")
            self.show_success_dialog()
        elif self.cancel_entire:
            self.status_label.config(text="Cancelled", foreground=self.colors["warning"])
            messagebox.showinfo("Cancelled", "Download cancelled by user.")
        elif self.skip_current:
            self.status_label.config(text="Skipped current video", foreground=self.colors["warning"])
        else:
            messagebox.showerror("Error", f"Failed: {msg}")
            self.status_label.config(text="Failed", foreground=self.colors["error"])

    def start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a valid URL")
            return
        if self.is_downloading:
            return

        folder = filedialog.askdirectory(title="Select Download Folder")
        if not folder:
            return

        need_ffmpeg = False
        if self.download_type.get() == "audio":
            need_ffmpeg = True
        elif self.download_type.get() == "video":
            qual = self.quality_var.get()
            val = self.quality_options.get(qual, "720")
            if val in ["1080", "1440", "2160", "best"]:
                need_ffmpeg = True

        if need_ffmpeg and not self.ffmpeg_available:
            messagebox.showerror(
                "Missing FFmpeg",
                "FFmpeg is required for this download.\n\nInstall FFmpeg and restart.\n"
                "Or select 720p or lower.",
            )
            return

        self.is_downloading = True
        self.reset_progress_tracking()
        self.download_btn.config(state="disabled", text="DOWNLOADING...")
        self.cancel_btn.config(state="normal")
        self.progress_bar["value"] = 0
        self.percent_label.config(text="0%")
        self.status_label.config(text="Starting...", foreground=self.colors["accent"])
        self.time_label.config(text="Time left: --:--")

        if self.playlist_detected and self.playlist_var.get():
            self.videos_left_label.config(text=f"Videos left: {self.total_videos}")
        else:
            self.videos_left_label.config(text="Videos left: 1")

        threading.Thread(target=self.download_thread, args=(url, folder), daemon=True).start()

    def download_thread(self, url, folder):
        try:
            debug_mode = os.getenv("UVIDS_DEBUG", "0").lower() in {"1", "true", "yes", "on"}
            max_network_attempts = int(os.getenv("UVIDS_MAX_NETWORK_ATTEMPTS", "4"))
            use_playlist = self.playlist_detected and self.playlist_var.get()
            playlist_title = None
            if use_playlist and self.current_info:
                playlist_title = sanitize_filename(self.current_info.get("title", "Playlist"))

            if use_playlist and playlist_title:
                out_dir = os.path.join(folder, playlist_title)
                os.makedirs(out_dir, exist_ok=True)
                template = truncate_for_windows(out_dir, "mp4")
                outtmpl = os.path.join(out_dir, template)
                self.last_download_folder = out_dir
            else:
                os.makedirs(folder, exist_ok=True)
                template = truncate_for_windows(folder, "mp4")
                outtmpl = os.path.join(folder, template)
                self.last_download_folder = folder

            quality_label = self.quality_var.get()
            quality_value = self.quality_options.get(quality_label, "720")
            ydl_opts = create_download_options(
                download_type=self.download_type.get(),
                quality_value=quality_value,
                ffmpeg_available=self.ffmpeg_available,
                ffmpeg_location=self.ffmpeg_dir,
                outtmpl=outtmpl,
                use_playlist=use_playlist,
                progress_hook=self.progress_hook,
                debug=debug_mode,
            )

            run_download(
                url,
                ydl_opts,
                max_network_attempts=max_network_attempts,
                debug=debug_mode,
            )

            if not self.cancel_entire and not self.skip_current:
                self.root.after(0, lambda: self.finish_download(True))
            else:
                self.root.after(0, lambda: self.finish_download(False, "Cancelled"))
        except Exception as exc:
            err = str(exc)
            if "Skip current video" in err:
                self.root.after(0, lambda: self.finish_download(False, "Skipped current video"))
                return
            if "cancelled" in err.lower() or self.cancel_entire:
                self.root.after(0, lambda: self.finish_download(False, "Cancelled"))
                return
            if "Unsupported URL" in err:
                err = "URL not supported. Try a direct video page link."
            elif "No video formats" in err:
                err = "No downloadable formats found. Site may require login or DRM."
            elif "Private video" in err:
                err = "This video is private. Use cookies to authenticate (see docs)."
            else:
                err = self._friendly_error_message(err)
            self.root.after(0, lambda: self.finish_download(False, err))

    def run(self):
        self.root.mainloop()
