# YT Downloader — Desktop App

## macOS

- **App**: `dist/YTDownloader.app` (93MB)
- **Installer**: `dist/YTDownloader.dmg` (123MB)
- Open the DMG, drag YTDownloader.app to Applications

## Windows

Build on a Windows machine:
```cmd
pip install -r requirements.txt
pip install pyinstaller
python build.py
```
Output: `dist/YTDownloader.exe`

## Linux

Build on Linux:
```bash
pip install -r requirements.txt
pip install pyinstaller
python build.py
```
Output: `dist/YTDownloader/`

## First run

The app auto-downloads ffmpeg (~50MB) on first use if not found on your system.

## Requirements

- Python 3.9+
- Chrome browser (for cookies)
- Internet connection
