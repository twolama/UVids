# UVids Downloader

Tkinter-based universal video downloader powered by yt-dlp.

## Requirements

- Python 3.10+ (project currently tested on newer Python versions)
- pip
- FFmpeg binaries placed inside this repository (see FFmpeg section)

## Setup

### Windows

1. Open PowerShell in the project root.
2. Create a virtual environment:

```powershell
python -m venv .venvwin
```

3. Activate it:

```powershell
.\.venvwin\Scripts\Activate.ps1
```

4. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

### Linux

1. Open a terminal in the project root.
2. Create a virtual environment:

```bash
python3 -m venv .venlin
```

3. Activate it:

```bash
source .venlin/bin/activate
```

4. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## Run The App

Use module mode from the project root:

### Windows

```powershell
python -m app.main
```

### Linux

```bash
python3 -m app.main
```

On startup, the app checks GitHub Releases for a newer version and prompts you only when an update is available.

## Build Packages (PyInstaller)

The project uses a shared spec file: `uvids.spec`

Install PyInstaller in your active environment before building:

### Windows

```powershell
python -m pip install pyinstaller
```

Build:

```powershell
scripts\build_windows.bat
```

### Linux

```bash
python3 -m pip install pyinstaller
```

Build:

```bash
bash scripts/build_linux.sh
```

Build output is generated in:

- `dist/uvids/`
- `build/`

## Release / Upgraded Version Workflow

When you want to package a new upgraded version:

1. Update version in `app/__init__.py`:

```python
__version__ = "X.Y.Z"
```

2. Ensure dependencies are up to date:

```bash
python -m pip install -r requirements.txt
```

3. Rebuild using the platform script:
- Windows: `scripts\build_windows.bat`
- Linux: `bash scripts/build_linux.sh`

4. Validate the built executable from `dist/uvids/`.

Installed users can update in-app by launching the app and accepting the update prompt.
Windows can download and launch the updater automatically after confirmation.
Linux will open the release/download page so the new build can be installed manually.

## FFmpeg

Place FFmpeg binaries here before packaging:

- Windows: `app/assets/ffmpeg/win/ffmpeg.exe`
- Linux: `app/assets/ffmpeg/linux/ffmpeg`

Linux binary must be executable:

```bash
chmod +x app/assets/ffmpeg/linux/ffmpeg
```

These binaries are intentionally not committed to Git.
