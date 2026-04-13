@echo off

if not exist "app\assets\ffmpeg\win\ffmpeg.exe" (
	echo Missing app\assets\ffmpeg\win\ffmpeg.exe. Place the Windows FFmpeg binary there before building.
	exit /b 1
)

python -m PyInstaller --clean --noconfirm uvids.spec

pause
