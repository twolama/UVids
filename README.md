# UVids Downloader

Tkinter-based universal video downloader powered by yt-dlp.

## Development

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
python app/main.py
```

## Packaging

### Windows

Run:

```bat
scripts\\build_windows.bat
```

### Linux

Run:

```bash
bash scripts/build_linux.sh
```

## FFmpeg

Place FFmpeg binaries here:

- app/assets/ffmpeg/win/ffmpeg.exe
- app/assets/ffmpeg/linux/ffmpeg
