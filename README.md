# YTTransformer

AI-powered video creation from YouTube clips. Enter a topic, Gemini generates a script, matching clips are extracted, and a new video is rendered with narration, audio mixing, and word-level subtitles. All in a cross-platform desktop app.

## Download

[macOS (56 MB)](https://github.com/udaydomadiya08/yt-transformer/releases/latest/download/YTTransformer-macOS.tar.gz) · [Windows (77 MB)](https://github.com/udaydomadiya08/yt-transformer/releases/latest/download/YTTransformer-Windows.zip) · [Linux (94 MB)](https://github.com/udaydomadiya08/yt-transformer/releases/latest/download/YTTransformer-Linux.tar.gz)

CLI: [macOS](https://github.com/udaydomadiya08/yt-transformer/releases/latest/download/YTTransformer-cli-macOS.tar.gz) · [Windows](https://github.com/udaydomadiya08/yt-transformer/releases/latest/download/YTTransformer-cli-Windows.zip) · [Linux](https://github.com/udaydomadiya08/yt-transformer/releases/latest/download/YTTransformer-cli-Linux.tar.gz)

## How it works

1. Enter a topic or description
2. Gemini generates a script with per-scene configuration (search query, narration, audio mix, transitions, subtitles)
3. YouTube search finds clips matching the narration via transcript timestamps
4. 3-4 sec segments downloaded (download-sections first, fallback to full + ffmpeg trim)
5. Edge TTS narration generated, mixed with original audio and optional background music
6. Vantix-style word-level subtitles applied (yellow passive + green active highlighting)
7. Scenes assembled with transitions and rendered as H.264/AAC

## Features

- **3 tabs**: Download (MP4/MP3/SRT/Meta from any YouTube URL), Create (AI video generation), Settings (API key, output dir, resolution)
- **Orientations**: vertical (1080×1920, ≤58s), horizontal (1920×1080, ≤120s), square (1080×1080, ≤88s)
- **Cookie cache**: auto-detects browser cookies (24h disk cache), no rate limiting
- **UPX compressed**: builds reduced from ~140 MB to 56-94 MB
- **CLI mode**: `yttransformer --topic "quantum computing" --demo`

## Tech stack

Python 3.11, MoviePy 1.0.3, yt-dlp, google-genai, Edge TTS, CustomTkinter, PyInstaller

## CLI

Download the CLI binary for your OS from the release page, then:

```bash
# Quick demo (no API key needed)
./YTTransformer-cli --demo

# Generate a real video
./YTTransformer-cli "quantum computing" --orientation vertical --api-key "YOUR_KEY"

# Use env var instead of --api-key
export GEMINI_API_KEY="YOUR_KEY"
./YTTransformer-cli "your topic" --orientation horizontal

# Options
./YTTransformer-cli --help
```

If you want to run from source instead:

```bash
cd desktop-app
pip install -r requirements.txt
python cli.py "your topic" --api-key "$GEMINI_API_KEY"
```

## Building from source

```bash
cd desktop-app
pip install -r requirements.txt
pip install pyinstaller
python build.py           # GUI + CLI
python build.py --cli-only # CLI only
```

## License

MIT
