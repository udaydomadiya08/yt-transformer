import shutil
import subprocess
import sys
from pathlib import Path

class Clipper:
    def __init__(self, ffmpeg_path=None, output_dir=None):
        self.ffmpeg_path = self._resolve_ffmpeg(ffmpeg_path)
        self.output_dir = Path(output_dir) if output_dir else Path("/tmp/yttransform_clips")
        self._browser = None

    def _resolve_ffmpeg(self, hint):
        if hint and hint != "ffmpeg":
            p = shutil.which(hint)
            if p:
                return p
        p = shutil.which("ffmpeg")
        if p:
            return p
        return None

    def _detect_browser(self):
        from utils.cookies import detect_browser as db
        return db()

    def _yt(self, *args):
        return [sys.executable, "-m", "yt_dlp"] + list(args)

    def download_segment(self, url, start, end, output_path, mode="video+audio"):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = Path(output_path)
        tmp_dir = self.output_dir / "tmp_dl"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        if mode == "audio_only":
            fmt = "bestaudio/best"
        elif mode == "video_only":
            fmt = "bv[height<=1080][ext=mp4]"
        else:
            fmt = "bv[height<=1080][ext=mp4]+ba/b"

        browser = self._detect_browser()
        start_str = self._fmt_time(start)
        dur_sec = end - start
        dur_str = self._fmt_time(dur_sec)

        # Try download-sections first (downloads only the needed segment)
        try:
            return self._download_sections(url, start_str, dur_str, output_path, fmt, browser, tmp_dir, mode)
        except Exception as e:
            pass

        # Fallback: download full video then ffmpeg trim
        tmp_raw = tmp_dir / f"raw_{output_path.stem}.%(ext)s"
        dl_cmd = self._yt("-f", fmt, "-o", str(tmp_raw),
                          "--no-write-info-json", "--no-write-thumbnail",
                          "--no-embed-metadata", "--no-embed-thumbnail",
                          "--no-embed-chapters", "--no-part")
        if self.ffmpeg_path:
            dl_cmd += ["--ffmpeg-location", self.ffmpeg_path]
        if browser:
            dl_cmd += ["--cookies-from-browser", browser]
        dl_cmd.append(url)

        result = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp full download failed: {result.stderr[:500]}")

        raw_files = list(tmp_dir.glob(f"raw_{output_path.stem}.*"))
        if not raw_files:
            raise FileNotFoundError(f"No downloaded file found for {output_path.stem}")

        raw_path = raw_files[0]
        ffmpeg_cmd = [self.ffmpeg_path or "ffmpeg", "-y",
                      "-i", str(raw_path),
                      "-ss", start_str,
                      "-t", dur_str,
                      "-c:v", "libx264", "-preset", "fast",
                      "-c:a", "aac",
                      "-pix_fmt", "yuv420p",
                      "-movflags", "+faststart",
                      str(output_path)]
        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=120)

        for f in raw_files:
            f.unlink(missing_ok=True)

        if not output_path.exists():
            raise FileNotFoundError(f"Clip not created: {output_path}")
        return output_path

    def _download_sections(self, url, start_str, dur_str, output_path, fmt, browser, tmp_dir, mode):
        tmp_sec = tmp_dir / f"sec_{output_path.stem}.%(ext)s"
        dl_cmd = self._yt("-f", fmt, "-o", str(tmp_sec),
                          "--download-sections", f"*{start_str}-{dur_str}",
                          "--no-write-info-json", "--no-write-thumbnail",
                          "--no-embed-metadata", "--no-embed-thumbnail",
                          "--no-embed-chapters", "--no-part",
                          "--force-keyframes-at-cuts")
        if self.ffmpeg_path:
            dl_cmd += ["--ffmpeg-location", self.ffmpeg_path]
        if browser:
            dl_cmd += ["--cookies-from-browser", browser]
        dl_cmd.append(url)

        result = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError(f"download-sections failed: {result.stderr[:200]}")

        sec_files = list(tmp_dir.glob(f"sec_{output_path.stem}.*"))
        if not sec_files:
            raise FileNotFoundError("No section file found")

        sec_path = sec_files[0]
        if sec_path.suffix != output_path.suffix:
            out = output_path.with_suffix(sec_path.suffix)
            sec_path.rename(out)
        else:
            sec_path.rename(output_path)

        for f in tmp_dir.glob(f"sec_{output_path.stem}.*"):
            f.unlink(missing_ok=True)

        if not output_path.exists():
            raise FileNotFoundError(f"Sections clip not created: {output_path}")
        return output_path

    def download_video_segment(self, url, start, end, clip_id):
        clip_path = self.output_dir / f"{clip_id}.mp4"
        return self.download_segment(url, start, end, clip_path, mode="video+audio")

    def download_audio_segment(self, url, start, end, clip_id):
        audio_path = self.output_dir / f"{clip_id}.m4a"
        return self.download_segment(url, start, end, audio_path, mode="audio_only")

    def _fmt_time(self, seconds):
        if isinstance(seconds, float) and seconds > 3600:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = seconds % 60
        elif isinstance(seconds, str):
            return seconds
        else:
            h = 0
            m = int(seconds // 60)
            s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}"
