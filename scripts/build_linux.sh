#!/bin/bash

pyinstaller \
  --onefile \
  --windowed \
  --name uvids \
  --add-data "app/assets:app/assets" \
  --hidden-import yt_dlp \
  --hidden-import PIL \
  --hidden-import PIL.Image \
  --hidden-import PIL.ImageTk \
  app/main.py
