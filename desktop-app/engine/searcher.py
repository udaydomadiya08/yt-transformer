import re
import json
import subprocess
import sys
import tempfile
from pathlib import Path

class Searcher:
    def __init__(self, ffmpeg_path="ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def _yt_cmd(self, *args):
        return [sys.executable, "-m", "yt_dlp"] + list(args)

    def search_videos(self, query, max_results=10):
        cmd = self._yt_cmd("--flat-playlist",
            f"ytsearch{max_results}:{query}",
            "--dump-json", "--no-download")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        videos = []
        for line in result.stdout.strip().split("\n"):
            if line:
                try:
                    videos.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return videos

    def get_video_info(self, url):
        cmd = self._yt_cmd("--dump-json", "--no-download", url)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        lines = result.stdout.strip().split("\n")
        if not lines:
            return None
        info = json.loads(lines[0])
        return info

    def get_subtitles(self, video_id):
        sub_files = list(Path().glob(f"{video_id}.*.vtt")) + list(Path().glob(f"{video_id}.*.en.vtt"))
        if not sub_files:
            return None
        raw = sub_files[0].read_text(encoding="utf-8")
        for f in sub_files:
            f.unlink(missing_ok=True)
        return self._parse_vtt(raw)

    def _parse_vtt(self, raw):
        entries = []
        raw = re.sub(r'^WEBVTT.*?(?=\n\d|\n$)', '', raw, flags=re.DOTALL).strip()
        blocks = re.split(r'\n\n+', raw)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")
            time_line = None
            text_lines = []
            for line in lines:
                line = line.strip()
                if "-->" in line:
                    time_line = line
                elif line and not line.startswith("Kind:") and not line.startswith("Language:"):
                    text_lines.append(line)
            if time_line and text_lines:
                m = re.match(r'(\d+):(\d+):(\d+)\.(\d+)\s+-->\s+(\d+):(\d+):(\d+)\.(\d+)', time_line)
                if m:
                    start = int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3)) + int(m.group(4))/1000
                    end = int(m.group(5))*3600 + int(m.group(6))*60 + int(m.group(7)) + int(m.group(8))/1000
                    text = " ".join(text_lines)
                    entries.append({"start": start, "end": end, "text": text})
        return entries

    def find_matching_timestamps(self, narration_text, subtitles):
        if not subtitles:
            return []
        narration_lower = narration_text.lower()
        narration_words = set(narration_lower.split())
        scored = []
        for entry in subtitles:
            text_lower = entry["text"].lower()
            overlap = narration_words & set(text_lower.split())
            if not overlap:
                continue
            score = len(overlap) / max(len(narration_words), 1)
            scored.append((score, entry))
        scored.sort(key=lambda x: -x[0])
        return [e for s, e in scored if s > 0.15]

    def find_clips_for_scene(self, scene_config):
        search_query = scene_config.get("search_query", "")
        narration_text = scene_config.get("narration", {}).get("text", "")
        if not search_query:
            return []
        videos = self.search_videos(search_query, max_results=5)
        candidates = []
        used_clip_keys = scene_config.get("_used_clips", set())
        for vid in videos[:5]:
            url = vid.get("webpage_url") or f"https://youtube.com/watch?v={vid.get('id')}"
            try:
                info = self.get_video_info(url)
                if not info:
                    continue
                subs = self.get_subtitles(info.get("id", ""))
                if not subs:
                    continue
                matches = self.find_matching_timestamps(narration_text, subs)
                for m in matches:
                    clip_key = f"{info['id']}_{m['start']:.1f}_{m['end']:.1f}"
                    if clip_key in used_clip_keys:
                        continue
                    duration = m["end"] - m["start"]
                    if duration < 2 or duration > 10:
                        continue
                    candidates.append({
                        "url": url,
                        "video_id": info.get("id"),
                        "title": info.get("title", ""),
                        "start": m["start"],
                        "end": m["end"],
                        "duration": duration,
                        "matched_text": m["text"],
                        "relevance_score": m.get("_score", 0.5),
                        "_clip_key": clip_key,
                    })
            except Exception:
                continue
        candidates.sort(key=lambda c: -self._score_candidate(c, narration_text))
        return candidates[:3]

    def _score_candidate(self, candidate, narration_text):
        match_len = len(candidate.get("matched_text", ""))
        dur = candidate.get("duration", 4)
        ideal_dur = len(narration_text.split()) * 0.3
        dur_score = 1.0 - min(abs(dur - ideal_dur) / ideal_dur, 0.8)
        return match_len * dur_score
