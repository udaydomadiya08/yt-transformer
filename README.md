# yt-all.sh

One command to download everything from any YouTube video.

## Requirements

- **yt-dlp** (Python 3.11) at `~/.pyenv/versions/3.11.14/bin/yt-dlp`
- **ffmpeg** at `/opt/homebrew/bin/ffmpeg`
- **Deno** (JS runtime for YouTube challenge solving)
- **Chrome** browser (for cookies)

## Usage

```
bash yt-all.sh <url> [options]
```

### Options

| Flag | What it does |
|---|---|
| *(none)* | MP4 + MP3 + SRT + metadata |
| `--all` | + top 50 comments |
| `--comments N` | + top N comments |
| `--sponsorblock` | mark sponsor/intro/outro chapters |
| `--split` | split into per-chapter files |
| `--all-thumbnails` | download all thumbnail sizes |
| `--keep-thumbnails` | keep thumbnail image files |
| `--list` | only list available formats (no download) |
| *(playlist URL)* | auto-downloads all videos |

### Examples

```bash
# Single video — everything
bash yt-all.sh "https://youtu.be/VIDEO_ID"

# With top 100 comments
bash yt-all.sh "https://youtu.be/VIDEO_ID" --comments 100

# With sponsorblock segments
bash yt-all.sh "https://youtu.be/VIDEO_ID" --sponsorblock

# Split into chapters
bash yt-all.sh "https://youtu.be/VIDEO_ID" --split

# Full playlist
bash yt-all.sh "https://youtube.com/playlist?list=PLAYLIST_ID"

# Just check available formats
bash yt-all.sh "https://youtu.be/VIDEO_ID" --list
```

## Output (`~/Downloads/`)

| File | Content |
|---|---|
| `{id}.mp4` | 1080p H.264 video (metadata, thumbnail, chapters embedded) |
| `{id}.mp3` | 320kbps audio (extracted locally via ffmpeg, no 2nd download) |
| `{id}.srt` | Transcript with timestamps (`00:00:00,000 --> 00:00:03,120`) |
| `{id}.meta.txt` | Title, channel, stats, description, tags, chapters, heatmap, comments |
| `{playlist}/` | Subfolder for playlists, one file per video |

### meta.txt fields

Title, channel, subscriber count, views, likes, comment count, duration, upload date, published timestamp, live status, age restriction, license, category, availability, location, selected format details (resolution, codec, fps, bitrate), chapter list, sponsorblock segments, most-replayed heatmap, tags, full description, top comments (with like counts).

## How it works

1. **yt-dlp** downloads best 1080p H.264 video + AAC audio, merges into MP4
2. **Metadata** (title, thumbnail, chapters) embedded into MP4
3. **MP3** extracted locally via ffmpeg (no second network download)
4. **VTT** auto-captions downloaded and converted to SRT with timestamps
5. **info.json** parsed into readable meta.txt (auto-generated captions, comments, chapters, heatmap)
