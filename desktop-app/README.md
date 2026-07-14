# YTTransformer Desktop App

Cross-platform desktop app for AI-powered video creation from YouTube clips.

## Build

```bash
pip install -r requirements.txt
pip install pyinstaller
python build.py
```

Output: `dist/` — platform archives.

## CLI

```bash
python cli.py "your topic" --orientation vertical --api-key "$KEY"
python cli.py --demo
```

## Dev

```bash
python main.py  # launch GUI
```
