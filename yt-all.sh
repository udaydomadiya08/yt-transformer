#!/bin/bash
set -euo pipefail

OUTDIR="${YT_DOWNLOAD_DIR:-$HOME/Downloads}"

# ─── Auto-find or install yt-dlp ───
YT_DLP="$(command -v yt-dlp || true)"
if [ -z "$YT_DLP" ]; then
  echo "==> yt-dlp not found, installing via pip..."
  python3 -m pip install -q yt-dlp
  YT_DLP="$(command -v yt-dlp)" || { echo "ERROR: yt-dlp install failed"; exit 1; }
fi

# ─── Auto-find or download ffmpeg ───
FFMPEG="$(command -v ffmpeg || true)"
if [ -z "$FFMPEG" ]; then
  echo "==> ffmpeg not found, downloading..."
  case "$(uname -s)" in
    Darwin)
      curl -sL "https://evermeet.cx/ffmpeg/ffmpeg/6.1/ffmpeg-6.1.zip" -o /tmp/ffmpeg.zip
      unzip -o /tmp/ffmpeg.zip -d /tmp/ >/dev/null 2>&1
      FFMPEG="/tmp/ffmpeg";;
    Linux)
      curl -sL "https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz" -o /tmp/ffmpeg.tar.xz
      tar xf /tmp/ffmpeg.tar.xz -C /tmp/ >/dev/null 2>&1
      FFMPEG="$(ls /tmp/ffmpeg-*-static/ffmpeg 2>/dev/null || echo '/tmp/ffmpeg')";;
    *)
      echo "ERROR: install ffmpeg manually (brew install ffmpeg / apt install ffmpeg)"
      exit 1;;
  esac
  chmod +x "$FFMPEG" 2>/dev/null || true
fi

# ─── Parse flags ───
comments=0; split_ch=0; sponsor=0; all_thumbs=0; list_only=0; keep_thumbs=0
url=""
while [ $# -gt 0 ]; do
  case "$1" in
    --comments) comments="${2:-50}"; shift 2 ;;
    --all) comments=50; shift ;;
    --split) split_ch=1; shift ;;
    --sponsorblock) sponsor=1; shift ;;
    --all-thumbnails) all_thumbs=1; shift ;;
    --list) list_only=1; shift ;;
    --keep-thumbnails) keep_thumbs=1; shift ;;
    *) url="$1"; shift ;;
  esac
done

# ─── List mode ───
if [ "$list_only" -eq 1 ]; then
  [ -z "$url" ] && { echo "Usage: $0 --list <url>"; exit 1; }
  COOKIE_ARG="$(cat "$HOME/.cache/ytdl-browser" 2>/dev/null || true)"
  if [ -n "$COOKIE_ARG" ]; then
    "$YT_DLP" --cookies-from-browser "$COOKIE_ARG" --list-formats "$url"
  else
    "$YT_DLP" --list-formats "$url"
  fi
  exit 0
fi

[ -z "$url" ] && {
  echo "Usage: $0 <url> [options]"
  echo "  --all               + top 50 comments"
  echo "  --comments N        + top N comments"
  echo "  --sponsorblock      mark sponsor/intro/outro chapters"
  echo "  --split             split into chapter files"
  echo "  --all-thumbnails    download all thumbnail sizes"
  echo "  --keep-thumbnails   keep thumbnail files"
  echo "  --list              show available formats only"
  exit 1
}

# ─── Detect playlist vs single ───
if [[ "$url" == *"list="* ]] || [[ "$url" == *"playlist"* ]]; then
  outtmpl="$OUTDIR/%(playlist_title)s/%(playlist_index)02d - %(title)s.%(ext)s"
else
  outtmpl="$OUTDIR/%(id)s.%(ext)s"
fi
if [ "$split_ch" -eq 1 ]; then
  outtmpl="$OUTDIR/%(id)s/%(section_number)02d - %(section_title)s.%(ext)s"
fi

# ─── Build yt-dlp command ───
yt_args=(
  -f "bv[height<=1080][vcodec^=avc1][ext=mp4]+ba[ext=m4a]"
  --write-auto-subs --sub-langs en --sub-format "vtt"
  --embed-metadata --embed-thumbnail --embed-chapters
  --write-info-json
  -o "$outtmpl"
  "$url"
)

if [ "$comments" -gt 0 ]; then
  yt_args=(--write-comments --extractor-args "youtube:max_comments=$comments,comment_sort=top" "${yt_args[@]}")
fi
if [ "$sponsor" -eq 1 ]; then
  yt_args=(--sponsorblock-mark all "${yt_args[@]}")
fi
if [ "$all_thumbs" -eq 1 ]; then
  yt_args=(--write-all-thumbnails "${yt_args[@]}")
else
  yt_args=(--write-thumbnail "${yt_args[@]}")
fi
if [ "$split_ch" -eq 1 ]; then
  yt_args=(--split-chapters "${yt_args[@]}")
fi

# ─── Auto-detect browser for cookies (cached, re-checks every 24h) ───
COOKIE_CACHE="$HOME/.cache/ytdl-browser"
COOKIE_TS="$HOME/.cache/ytdl-browser-ts"
COOKIE_ARG=""
now=$(date +%s)
recheck=86400
if [ -f "$COOKIE_CACHE" ] && [ -f "$COOKIE_TS" ]; then
  last=$(cat "$COOKIE_TS" 2>/dev/null || echo 0)
  elapsed=$((now - last))
  if [ "$elapsed" -lt "$recheck" ]; then
    cached=$(cat "$COOKIE_CACHE")
    if [ "$cached" != "none" ]; then
      COOKIE_ARG="--cookies-from-browser $cached"
    fi
  fi
fi
if [ -z "$COOKIE_ARG" ] && { [ ! -f "$COOKIE_TS" ] || [ $((now - $(cat "$COOKIE_TS" 2>/dev/null || echo 0))) -ge "$recheck" ]; }; then
  for b in chrome firefox edge brave opera chromium vivaldi safari; do
    if "$YT_DLP" --cookies-from-browser "$b" --dump-json >/dev/null 2>&1 <<< "" 2>/dev/null; then
      COOKIE_ARG="--cookies-from-browser $b"
      mkdir -p "$(dirname "$COOKIE_CACHE")"
      echo "$b" > "$COOKIE_CACHE"
      echo "$now" > "$COOKIE_TS"
      break
    fi
  done
  if [ -z "$COOKIE_ARG" ]; then
    mkdir -p "$(dirname "$COOKIE_CACHE")"
    echo "none" > "$COOKIE_CACHE"
    echo "$now" > "$COOKIE_TS"
  fi
fi

echo "==> Downloading..." | tr '\n' ' '
[ "$sponsor" -eq 1 ] && echo -n " + sponsorblock"
echo ""
"$YT_DLP" $COOKIE_ARG "${yt_args[@]}"

# ─── For split-chapter mode: done (no post-processing) ───
if [ "$split_ch" -eq 1 ]; then
  echo ""
  echo "==> DONE (chapter files in $OUTDIR/$(echo "$url" | sed -E 's/.*(v=|youtu\.be\/|shorts\/)([a-zA-Z0-9_-]+).*/\2/')/)"
  exit 0
fi

# ─── Extract video ID for post-processing ───
safe=$(echo "$url" | sed -E 's/.*(v=|youtu\.be\/|shorts\/)([a-zA-Z0-9_-]+).*/\2/')

# ─── MP3 via ffmpeg ───
mp4="$OUTDIR/${safe}.mp4"
mp3="$OUTDIR/${safe}.mp3"
if [ -f "$mp4" ]; then
  echo "==> Extracting MP3 (320kbps)..."
  $FFMPEG -y -i "$mp4" -vn -c:a libmp3lame -b:a 320k "$mp3" < /dev/null 2>&1 | grep -E "size=|Output"
fi

# ─── VTT → SRT ───
vf="$OUTDIR/${safe}.en.vtt"
if [ -f "$vf" ]; then
  echo "==> Converting transcript to SRT..."
  python3 -c "
import re, sys
od, sf = sys.argv[1], sys.argv[2]
with open(f'{od}/{sf}.en.vtt') as f:
    raw = f.read()
raw = re.sub(r'^WEBVTT.*?(?=\n\d|\n\$)', '', raw, flags=re.DOTALL).strip()
raw = re.sub(r'^Kind:.*?\n', '', raw, flags=re.MULTILINE)
raw = re.sub(r'^Language:.*?\n', '', raw, flags=re.MULTILINE)
raw = re.sub(r'\n{3,}', '\n\n', raw)
raw = raw.replace('.', ',')
n = raw.count('-->')
with open(f'{od}/{sf}.srt', 'w') as out:
    out.write(raw)
print(f'{n} entries')
" "$OUTDIR" "$safe"
  rm -f "$vf"
fi

# ─── Full metadata + comments → meta.txt ───
info="$OUTDIR/${safe}.info.json"
if [ -f "$info" ]; then
  echo "==> Writing meta.txt..."
  python3 -c "
import json, sys
od, sf = sys.argv[1], sys.argv[2]
with open(f'{od}/{sf}.info.json') as f:
    d = json.load(f)
o = []

def fmt(ms):
    s=ms//1000;h=s//3600;m=(s%3600)//60;se=s%60
    return f'{h:02d}:{m:02d}:{se:02d}' if h else f'{m:02d}:{se:02d}'
def ts(sec):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(sec, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if sec else 'N/A'

o.append('=== TITLE ===')
o.append(d.get('title','')); o.append('')

o.append(f\"Channel: {d.get('channel','')} ({d.get('channel_follower_count',0):,} subs)\")
o.append(f\"Views: {d.get('view_count',0):,}  |  Likes: {d.get('like_count',0):,}  |  Comments: {d.get('comment_count',0)}\")
o.append(f\"Duration: {d.get('duration_string','')} ({d.get('duration',0)}s)  |  Uploaded: {d.get('upload_date','')}\")
o.append(f\"Published: {ts(d.get('timestamp',0))}  |  Live status: {d.get('live_status','N/A')}\")
o.append(f\"Age: {d.get('age_limit',0)}+  |  License: {d.get('license','N/A')}  |  Category: {', '.join(d.get('categories',[])) or 'N/A'}\")
o.append(f\"Availability: {d.get('availability','N/A')}\")

# Location
loc = d.get('location', '')
if not loc: loc = d.get('coordinates', '')
if loc: o.append(f\"Location: {loc}\")

# URL
o.append(f\"{d.get('webpage_url','')}\")

# Playlist info
pl = d.get('playlist_title', '')
if pl:
    pli = d.get('playlist_index', '')
    plc = d.get('playlist_count', '')
    o.append(f\"Playlist: {pl}  (#{plc} videos, video #{pli})\")

# Selected format
fmt_selected = ''
for f in d.get('formats', []):
    if f.get('format_id') == d.get('format_id'):
        fmt_selected = f
        break
if fmt_selected:
    o.append(f\"Format: {fmt_selected.get('format','N/A')}  |  {fmt_selected.get('width','?')}x{fmt_selected.get('height','?')} @ {fmt_selected.get('fps','?')}fps\")
    o.append(f\"Video: {fmt_selected.get('vcodec','N/A')} @ {fmt_selected.get('vbr','?')}kbps  |  Audio: {fmt_selected.get('acodec','N/A')} @ {fmt_selected.get('abr','?')}kbps\")
    o.append(f\"Dynamic range: {fmt_selected.get('dynamic_range','N/A')}  |  Filesize: {fmt_selected.get('filesize_approx',0)//1024//1024}MB\")

o.append('')

# Chapters
ch = d.get('chapters', [])
if ch:
    o.append(f'=== CHAPTERS ({len(ch)}) ===')
    for i, c in enumerate(ch):
        t = c.get('start_time', 0)
        o.append(f'  {i+1}. {fmt(t)} - {c.get(\"title\",\"\")}')
    o.append('')

# Sponsorblock chapters
sp = [c for c in ch if c.get('category','') != '']
if sp:
    spam_map = {'sponsor':'sponsor','intro':'intro','outro':'outro','selfpromo':'self-promo','filler':'filler','interaction':'interaction','music_offtopic':'music'}
    o.append('=== SPONSORBLOCK ===')
    for c in sp:
        cat = spam_map.get(c.get('category'), c.get('category'))
        t = c.get('start_time', 0)
        o.append(f'  {fmt(t)} - {cat}')
    o.append('')

# Heatmap (most replayed)
hm = d.get('heatmap', [])
if hm:
    peaks = sorted(hm, key=lambda x: x.get('value',0), reverse=True)[:5]
    o.append('=== MOST REPLAYED (top 5) ===')
    for hh in peaks:
        st = hh.get('start_time', 0)/1000
        en = st + hh.get('end_time', 0)/1000
        o.append(f'  {fmt(int(st*1000))} - {fmt(int(en*1000))}')
    o.append('')

# Tags
tags = d.get('tags', [])
if tags:
    o.append('=== TAGS ===')
    for t in tags: o.append(f'  #{t}')
    o.append('')

# Description
desc = d.get('description', '')
if desc:
    o.append('=== DESCRIPTION ===')
    o.append(desc); o.append('')

# Comments
cmts = d.get('comments', [])
if cmts:
    o.append(f'=== TOP COMMENTS ({len(cmts)}) ===')
    for c in cmts:
        author = c.get('author', c.get('name', '?'))
        text = c.get('text', '').replace(chr(10), ' ')
        likes = c.get('like_count', 0)
        o.append(f'{author} (+{likes}): {text}'); o.append('')

open(f'{od}/{sf}.meta.txt','w').write('\n'.join(o))
print(f'Meta written ({len(cmts)} comments)')
" "$OUTDIR" "$safe"
  rm -f "$info"
fi

# ─── Clean up thumbnails ───
if [ "$keep_thumbs" -eq 0 ]; then
  rm -f "$OUTDIR/${safe}".webp "$OUTDIR/${safe}".jpg "$OUTDIR/${safe}".png
fi

echo ""
echo "==> DONE:"
ls -lh "$OUTDIR/${safe}".mp4 "$OUTDIR/${safe}".mp3 \
      "$OUTDIR/${safe}".srt "$OUTDIR/${safe}".meta.txt 2>/dev/null || true
