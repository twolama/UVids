@echo off

pyinstaller ^
  --onefile ^
  --windowed ^
  --name uvids ^
  --icon "app/assets/icons/uvids.ico" ^
  --add-data "app/assets;app/assets" ^
  --add-data "app/assets/ffmpeg/win;assets/ffmpeg/win" ^
  --hidden-import yt_dlp ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageTk ^
  app/main.py

pause
