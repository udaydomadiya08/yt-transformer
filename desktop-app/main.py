#!/usr/bin/env python3
import customtkinter as ctk
from tkinter import messagebox
import yt_dlp
import threading
import asyncio
import os
import sys
import re
import json
import shutil
import subprocess
import platform
import zipfile
import tarfile
import urllib.request
import io
from pathlib import Path
from PIL import Image
import requests
import time
from datetime import datetime, timezone

from utils.config import Config
from pipeline import VideoPipeline

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

APP_NAME = "YTTransformer"

def appdata_dir():
    home = Path.home()
    sys_name = platform.system()
    if sys_name == "Darwin":
        return home / "Library" / "Application Support" / APP_NAME
    elif sys_name == "Windows":
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / APP_NAME
    else:
        return home / ".config" / APP_NAME

def open_file(path):
    p = str(path)
    sys_name = platform.system()
    if sys_name == "Darwin":
        subprocess.Popen(["open", p])
    elif sys_name == "Windows":
        os.startfile(p)
    else:
        subprocess.Popen(["xdg-open", p])

def open_folder(path):
    p = str(path)
    sys_name = platform.system()
    if sys_name == "Darwin":
        subprocess.Popen(["open", "-R", p])
    elif sys_name == "Windows":
        subprocess.Popen(["explorer", "/select,", p])
    else:
        subprocess.Popen(["xdg-open", str(Path(p).parent)])

def _detect_browser():
    from utils.cookies import detect_browser as db
    return db()

class FFmpegManager:
    def __init__(self):
        self.app_dir = appdata_dir()
        self.ff_dir = self.app_dir / "ffmpeg"
        self.ff_path = None
        self._find_or_download()

    def _find_or_download(self):
        exe = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
        which = shutil.which("ffmpeg")
        if which:
            self.ff_path = Path(which)
            return
        local = self.ff_dir / exe
        if local.exists():
            self.ff_path = local
            return
        self.ff_dir.mkdir(parents=True, exist_ok=True)
        self._download_ffmpeg(exe)

    def _download_ffmpeg(self, exe_name):
        sys_name = platform.system()
        print(f"[ffmpeg] Downloading for {sys_name}...")
        if sys_name == "Darwin":
            url = "https://evermeet.cx/ffmpeg/ffmpeg-7.1.zip"
            tmp = self.ff_dir / "ffmpeg.zip"
            urllib.request.urlretrieve(url, tmp)
            with zipfile.ZipFile(tmp, "r") as z:
                z.extract("ffmpeg", str(self.ff_dir))
            tmp.unlink()
            (self.ff_dir / "ffmpeg").chmod(0o755)
        elif sys_name == "Windows":
            url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            tmp = self.ff_dir / "ffmpeg.zip"
            urllib.request.urlretrieve(url, tmp)
            with zipfile.ZipFile(tmp, "r") as z:
                for m in z.namelist():
                    if m.endswith("ffmpeg.exe"):
                        z.extract(m, str(self.ff_dir))
                        src = self.ff_dir / m
                        src.rename(self.ff_dir / "ffmpeg.exe")
                        break
            tmp.unlink()
        else:
            url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
            tmp = self.ff_dir / "ffmpeg.tar.xz"
            urllib.request.urlretrieve(url, tmp)
            with tarfile.open(tmp, "r:xz") as t:
                for m in t.getmembers():
                    if m.name.endswith("ffmpeg") and not m.isdir():
                        t.extract(m, str(self.ff_dir))
                        src = self.ff_dir / m.name
                        src.rename(self.ff_dir / "ffmpeg")
                        break
            tmp.unlink()
            (self.ff_dir / "ffmpeg").chmod(0o755)
        print(f"[ffmpeg] -> {self.ff_dir / exe_name}")

    def path(self):
        return str(self.ff_path) if self.ff_path else "ffmpeg"

class DownloadWorker:
    def __init__(self, url, outdir, opts, progress_cb):
        self.url = url
        self.outdir = outdir
        self.opts = opts
        self.progress_cb = progress_cb
        self.cancelled = False
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        self.cancelled = True

    def _run(self):
        m = re.search(r'(?:v=|youtu\.be/|shorts/)([\w-]+)', self.url)
        vid = m.group(1) if m else "video"
        ff_path = FFmpegManager().path()
        outtmpl = str(self.outdir / f"{vid}.%(ext)s")
        results = []
        postprocessors = []
        formats = []
        vq = self.opts.get("vid_quality", "1080p")
        aq = self.opts.get("aud_quality", "320")
        if self.opts.get("mp4"):
            height = vq.replace("p", "")
            formats.append(f"bv[height<={height}][vcodec^=avc1][ext=mp4]+ba[ext=m4a]")
        if self.opts.get("mp3"):
            if not formats:
                formats.append("bestaudio/best")
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": aq,
            })
        format_sel = "/".join(formats) if formats else "bv*+ba/b"
        browser = _detect_browser()
        opts = {
            "format": format_sel,
            "outtmpl": outtmpl,
            "ffmpeg_location": ff_path,
            "writesubtitles": False,
            "writeautomaticsub": self.opts.get("srt", False),
            "subtitleslangs": ["en"],
            "subtitlesformat": "vtt",
            "writeinfojson": True,
            "writethumbnail": True,
            "embedmetadata": True,
            "embedthumbnail": True,
            "embedchapters": True,
            "postprocessors": postprocessors,
            "keepvideo": self.opts.get("mp4") and self.opts.get("mp3"),
            "postprocessor_args": {"ffmpeg": ["-y"]},
        }
        if browser:
            opts["cookiesfrombrowser"] = (browser,)
        if self.opts.get("comments", 0) > 0:
            opts["writecomments"] = True
            opts["extractor_args"] = {
                "youtube": {
                    "max_comments": [str(self.opts["comments"])],
                    "comment_sort": ["top"],
                }
            }
        opts["progress_hooks"] = [self._make_hook()]
        try:
            self.progress_cb({"status": "fetching"})
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
            title = info.get("title", vid)
            mp4 = self.outdir / f"{vid}.mp4"
            mp3 = self.outdir / f"{vid}.mp3"
            vtt = self.outdir / f"{vid}.en.vtt"
            srt = self.outdir / f"{vid}.srt"
            meta = self.outdir / f"{vid}.meta.txt"
            info_json = self.outdir / f"{vid}.info.json"
            if mp4.exists():
                results.append(("MP4", str(mp4), mp4.stat().st_size))
            if mp3.exists():
                results.append(("MP3", str(mp3), mp3.stat().st_size))
            if self.opts.get("srt") and vtt.exists():
                self.progress_cb({"status": "converting_srt"})
                raw = vtt.read_text(encoding="utf-8")
                raw = re.sub(r'^WEBVTT.*?(?=\n\d|\n$)', "", raw, flags=re.DOTALL).strip()
                raw = re.sub(r'^Kind:.*?\n', "", raw, flags=re.MULTILINE)
                raw = re.sub(r'^Language:.*?\n', "", raw, flags=re.MULTILINE)
                raw = re.sub(r'\n{3,}', "\n\n", raw)
                raw = raw.replace(".", ",")
                srt.write_text(raw, encoding="utf-8")
                results.append(("SRT", str(srt), srt.stat().st_size))
                vtt.unlink(missing_ok=True)
            if self.opts.get("meta") and info_json.exists():
                self.progress_cb({"status": "writing_meta"})
                with open(info_json) as f:
                    d = json.load(f)
                o = []
                def fmt_ms(ms):
                    s = ms // 1000
                    h = s // 3600
                    m = (s % 3600) // 60
                    se = s % 60
                    return f"{h:02d}:{m:02d}:{se:02d}" if h else f"{m:02d}:{se:02d}"
                def ts(sec):
                    if not sec:
                        return "N/A"
                    return datetime.fromtimestamp(sec, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                o.append("=== TITLE ===")
                o.append(d.get("title", ""))
                o.append("")
                o.append(f"Channel: {d.get('channel','')} ({d.get('channel_follower_count',0):,} subs)")
                o.append(f"Views: {d.get('view_count',0):,}  |  Likes: {d.get('like_count',0):,}  |  Comments: {d.get('comment_count',0)}")
                o.append(f"Duration: {d.get('duration_string','')}  |  Uploaded: {d.get('upload_date','')}")
                o.append(f"Published: {ts(d.get('timestamp',0))}  |  Live: {d.get('live_status','N/A')}")
                o.append(f"Age: {d.get('age_limit',0)}+  |  License: {d.get('license','N/A')}  |  Category: {', '.join(d.get('categories',[])) or 'N/A'}")
                o.append(f"Availability: {d.get('availability','N/A')}")
                loc = d.get("location", d.get("coordinates", ""))
                if loc:
                    o.append(f"Location: {loc}")
                o.append(f"{d.get('webpage_url','')}")
                pl = d.get("playlist_title", "")
                if pl:
                    o.append(f"Playlist: {pl}  (#{d.get('playlist_count','?')} videos, #{d.get('playlist_index','?')})")
                for f_info in d.get("formats", []):
                    if f_info.get("format_id") == d.get("format_id"):
                        w = f_info.get("width", "?")
                        h = f_info.get("height", "?")
                        o.append(f"Format: {f_info.get('format','N/A')}  |  {w}x{h} @ {f_info.get('fps','?')}fps")
                        o.append(f"Video: {f_info.get('vcodec','N/A')} @ {f_info.get('vbr','?')}kbps  |  Audio: {f_info.get('acodec','N/A')} @ {f_info.get('abr','?')}kbps")
                        break
                o.append("")
                ch = d.get("chapters", [])
                if ch:
                    o.append(f"=== CHAPTERS ({len(ch)}) ===")
                    for i, c in enumerate(ch):
                        o.append(f"  {i+1}. {fmt_ms(c.get('start_time',0)*1000)} - {c.get('title','')}")
                    o.append("")
                hm = d.get("heatmap", [])
                if hm:
                    peaks = sorted(hm, key=lambda x: x.get("value", 0), reverse=True)[:5]
                    o.append("=== MOST REPLAYED (top 5) ===")
                    for hh in peaks:
                        st = hh.get("start_time", 0) / 1000
                        en = st + hh.get("end_time", 0) / 1000
                        o.append(f"  {fmt_ms(int(st*1000))} - {fmt_ms(int(en*1000))}")
                    o.append("")
                tags = d.get("tags", [])
                if tags:
                    o.append("=== TAGS ===")
                    for t in tags:
                        o.append(f"  #{t}")
                    o.append("")
                desc = d.get("description", "")
                if desc:
                    o.append("=== DESCRIPTION ===")
                    o.append(desc)
                    o.append("")
                cmts = d.get("comments", [])
                if cmts:
                    o.append(f"=== TOP COMMENTS ({len(cmts)}) ===")
                    for c in cmts:
                        author = c.get("author", c.get("name", "?"))
                        text = c.get("text", "").replace("\n", " ")
                        likes = c.get("like_count", 0)
                        o.append(f"{author} (+{likes}): {text}")
                        o.append("")
                meta.write_text("\n".join(o), encoding="utf-8")
                results.append(("Meta", str(meta), meta.stat().st_size))
                info_json.unlink(missing_ok=True)
            for p in [self.outdir / f"{vid}.webp", self.outdir / f"{vid}.jpg", self.outdir / f"{vid}.png"]:
                p.unlink(missing_ok=True)
            self.progress_cb({"status": "done", "results": results, "title": title})
        except Exception as e:
            if not self.cancelled:
                self.progress_cb({"status": "error", "message": str(e)})

    def _make_hook(self):
        def hook(d):
            if self.cancelled:
                raise Exception("Cancelled")
            self.progress_cb(d)
        return hook


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("860x700")
        self.minsize(720, 600)

        self.config = Config()
        self.ffmpeg = FFmpegManager()
        self.worker = None
        self.pipeline = None
        self.info = None

        self._setup_ui()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self, anchor="nw")
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.tab_download = self.tabview.add("Download")
        self.tab_create = self.tabview.add("Create")
        self.tab_settings = self.tabview.add("Settings")

        self._setup_download_tab()
        self._setup_create_tab()
        self._setup_settings_tab()

    def _setup_download_tab(self):
        t = self.tab_download
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(t, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text="Download", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w")

        url_frame = ctk.CTkFrame(top, fg_color="transparent")
        url_frame.pack(fill="x", pady=(8, 0))
        url_frame.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(url_frame, placeholder_text="Paste YouTube URL here...", height=38)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.url_entry.bind("<Return>", lambda e: self._fetch())

        self.fetch_btn = ctk.CTkButton(url_frame, text="Fetch", width=90, height=38, command=self._fetch)
        self.fetch_btn.grid(row=0, column=1)

        self.scroll = ctk.CTkScrollableFrame(t, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(8, 10))
        self.scroll.grid_columnconfigure(0, weight=1)

        self.info_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.progress_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.results_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")

        self.status_label = ctk.CTkLabel(self.scroll, text="Paste a YouTube URL and click Fetch", font=ctk.CTkFont(size=13), text_color="gray")
        self.status_label.grid(row=0, column=0, pady=60)

    def _fetch(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("URL required", "Please paste a YouTube URL.")
            return
        self.fetch_btn.configure(state="disabled", text="Loading...")
        self.status_label.configure(text="Fetching video info...")
        self._clear_frame(self.info_frame)
        self._clear_frame(self.progress_frame)
        self._clear_frame(self.results_frame)
        self.info_frame.grid_remove()
        self.progress_frame.grid_remove()
        self.results_frame.grid_remove()
        threading.Thread(target=self._fetch_thread, args=(url,), daemon=True).start()

    def _fetch_thread(self, url):
        try:
            ff_path = self.ffmpeg.path()
            with yt_dlp.YoutubeDL({"format": "best", "ffmpeg_location": ff_path}) as ydl:
                info = ydl.extract_info(url, download=False)
            self.info = info
            self.after(0, self._show_preview, info)
        except Exception as e:
            self.after(0, self._fetch_error, str(e))

    def _fetch_error(self, msg):
        self.fetch_btn.configure(state="normal", text="Fetch")
        self.status_label.configure(text=f"Error: {msg}")

    def _show_preview(self, info):
        self.fetch_btn.configure(state="normal", text="Fetch")
        self.info_frame.grid(row=0, column=0, sticky="ew")
        self.info_frame.grid_columnconfigure(1, weight=1)
        for w in self.info_frame.winfo_children():
            w.destroy()
        thumb_url = None
        if info.get("thumbnail"):
            thumb_url = info["thumbnail"]
        elif info.get("thumbnails"):
            thumbs = sorted(info["thumbnails"], key=lambda t: t.get("preference", 0) or t.get("width", 0) or 0, reverse=True)
            if thumbs:
                thumb_url = thumbs[0].get("url")
        if thumb_url:
            try:
                resp = requests.get(thumb_url, timeout=10)
                img = Image.open(io.BytesIO(resp.content))
                img.thumbnail((200, 120))
                self._thumb_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                thumb_lbl = ctk.CTkLabel(self.info_frame, image=self._thumb_img, text="")
                thumb_lbl.grid(row=0, column=0, rowspan=4, sticky="nw", padx=(0, 14), pady=2)
            except Exception:
                pass
        title = info.get("title", "Unknown")
        channel = info.get("channel", info.get("uploader", "Unknown"))
        dur = info.get("duration_string", f"{info.get('duration',0)}s")
        views = f"{info.get('view_count',0):,}"
        cmt_count = info.get("comment_count", 0)
        ctk.CTkLabel(self.info_frame, text=title, font=ctk.CTkFont(size=16, weight="bold"), wraplength=420, justify="left").grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(self.info_frame, text=f"{channel}  |  {dur}  |  {views} views", font=ctk.CTkFont(size=13), text_color="gray").grid(row=1, column=1, sticky="w")
        opt_frame = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        opt_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 4))
        opt_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self._mp4_var = ctk.BooleanVar(value=True)
        self._mp3_var = ctk.BooleanVar(value=False)
        self._srt_var = ctk.BooleanVar(value=True)
        self._meta_var = ctk.BooleanVar(value=True)
        self._cmt_var = ctk.BooleanVar(value=0 < cmt_count <= 200)
        self._vid_q = ctk.StringVar(value="1080p")
        self._aud_q = ctk.StringVar(value="320kbps")
        r0 = ctk.CTkFrame(opt_frame, fg_color="transparent")
        r0.grid(row=0, column=0, columnspan=3, sticky="ew", pady=3)
        ctk.CTkCheckBox(r0, text="MP4", variable=self._mp4_var).pack(side="left")
        vid_menu = ctk.CTkOptionMenu(r0, values=["1080p", "720p", "480p", "360p"], variable=self._vid_q, width=90)
        vid_menu.pack(side="left", padx=(6, 0))
        r1 = ctk.CTkFrame(opt_frame, fg_color="transparent")
        r1.grid(row=1, column=0, columnspan=3, sticky="ew", pady=3)
        ctk.CTkCheckBox(r1, text="MP3", variable=self._mp3_var).pack(side="left")
        aud_menu = ctk.CTkOptionMenu(r1, values=["320kbps", "128kbps"], variable=self._aud_q, width=90)
        aud_menu.pack(side="left", padx=(6, 0))
        r2 = ctk.CTkFrame(opt_frame, fg_color="transparent")
        r2.grid(row=2, column=0, columnspan=3, sticky="ew", pady=3)
        ctk.CTkCheckBox(r2, text="SRT (subtitles)", variable=self._srt_var).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(r2, text="Meta.txt", variable=self._meta_var).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(r2, text=f"Comments ({cmt_count})", variable=self._cmt_var).pack(side="left")
        dl_btn = ctk.CTkButton(self.info_frame, text="Download", height=38, font=ctk.CTkFont(size=14, weight="bold"), fg_color="#2b7a4b", hover_color="#236b3f", command=self._download)
        dl_btn.grid(row=4, column=0, columnspan=2, pady=(10, 0), sticky="ew")
        self.status_label.grid_remove()

    def _download(self):
        if not self.info:
            return
        outdir = Path.home() / "Downloads"
        opts = {
            "mp4": self._mp4_var.get(),
            "mp3": self._mp3_var.get(),
            "vid_quality": self._vid_q.get(),
            "aud_quality": self._aud_q.get().replace("kbps", ""),
            "srt": self._srt_var.get(),
            "meta": self._meta_var.get(),
            "comments": 50 if self._cmt_var.get() else 0,
        }
        if not any([opts["mp4"], opts["mp3"]]):
            messagebox.showwarning("Nothing selected", "Select at least MP4 or MP3.")
            return
        self._clear_frame(self.results_frame)
        self.results_frame.grid_remove()
        self.info_frame.grid_remove()
        self.progress_frame.grid(row=1, column=0, sticky="ew")
        self._clear_frame(self.progress_frame)
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, height=14, corner_radius=7)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(14, 4))
        self.progress_bar.set(0)
        self.progress_text = ctk.CTkLabel(self.progress_frame, text="Starting...", font=ctk.CTkFont(size=13))
        self.progress_text.grid(row=1, column=0, pady=2)
        self.progress_sub = ctk.CTkLabel(self.progress_frame, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.progress_sub.grid(row=2, column=0, pady=(0, 8))
        self.cancel_btn = ctk.CTkButton(self.progress_frame, text="Cancel", width=80, fg_color="#a33", hover_color="#822", command=self._cancel)
        self.cancel_btn.grid(row=3, column=0, pady=4)
        self.worker = DownloadWorker(self.url_entry.get().strip(), outdir, opts, self._progress_update)
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()
        self.progress_text.configure(text="Cancelled")
        self.cancel_btn.configure(state="disabled")

    def _progress_update(self, d):
        status = d.get("status", "")
        if status == "fetching":
            self.progress_text.configure(text="Fetching video info...")
            self.progress_bar.set(0)
            self.progress_sub.configure(text="")
        elif status == "downloading":
            pct = 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = min(downloaded / total, 0.99)
            speed = d.get("_speed_str", "")
            eta = d.get("_eta_str", "")
            fn = Path(d.get("filename", "")).name
            self.progress_bar.set(pct)
            self.progress_text.configure(text=f"Downloading  {fn}")
            if speed and eta and total > 0:
                self.progress_sub.configure(text=f"{downloaded/1024/1024:.1f} MB / {total/1024/1024:.1f} MB  @  {speed}  .  ETA {eta}")
            elif total > 0:
                self.progress_sub.configure(text=f"{downloaded/1024/1024:.1f} MB / {total/1024/1024:.1f} MB")
        elif status in ("post_process", "Processing"):
            self.progress_text.configure(text="Processing...")
            self.progress_bar.set(0.92)
            self.progress_sub.configure(text="")
        elif status == "converting_srt":
            self.progress_text.configure(text="Converting subtitles...")
            self.progress_bar.set(0.95)
        elif status == "writing_meta":
            self.progress_text.configure(text="Writing metadata...")
            self.progress_bar.set(0.98)
        elif status == "done":
            self.progress_bar.set(1)
            self.progress_text.configure(text="Complete!")
            self.cancel_btn.grid_remove()
            self._show_results(d.get("results", []), d.get("title", ""))
        elif status == "error":
            self.progress_bar.set(0)
            self.progress_text.configure(text=f"Error: {d.get('message', 'Unknown')}")
            self.cancel_btn.configure(text="Retry", fg_color="#2b7a4b", command=self._download)

    def _show_results(self, results, title):
        self._clear_frame(self.results_frame)
        self.results_frame.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self.results_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.results_frame, text="Downloaded", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        for i, (label, path, size) in enumerate(results):
            kb = size / 1024
            size_str = f"{kb/1024:.1f} MB" if kb > 1024 else f"{kb:.0f} KB"
            ctk.CTkLabel(self.results_frame, text=label, font=ctk.CTkFont(size=13, weight="bold")).grid(row=1 + i, column=0, sticky="w", padx=(0, 8))
            ctk.CTkLabel(self.results_frame, text=size_str, text_color="gray", font=ctk.CTkFont(size=12)).grid(row=1 + i, column=1, sticky="w")
            btn_frame = ctk.CTkFrame(self.results_frame, fg_color="transparent")
            btn_frame.grid(row=1 + i, column=2, sticky="e", padx=4)
            ctk.CTkButton(btn_frame, text="Open", width=60, command=lambda p=path: open_file(p)).pack(side="left", padx=2)
            ctk.CTkButton(btn_frame, text="Folder", width=60, fg_color="#444", command=lambda p=path: open_folder(p)).pack(side="left", padx=2)
        btn2 = ctk.CTkButton(self.results_frame, text="+ New Download", height=34, command=self._reset, fg_color="#333", hover_color="#555")
        btn2.grid(row=len(results) + 1, column=0, columnspan=3, pady=(14, 4), sticky="ew")

    def _reset(self):
        self._clear_frame(self.info_frame)
        self._clear_frame(self.progress_frame)
        self._clear_frame(self.results_frame)
        self.info_frame.grid_remove()
        self.progress_frame.grid_remove()
        self.results_frame.grid_remove()
        self.status_label.configure(text="Paste a YouTube URL and click Fetch")
        self.status_label.grid(row=0, column=0, pady=60)
        self.url_entry.delete(0, "end")
        self.info = None
        self.worker = None

    def _clear_frame(self, frame):
        for w in frame.winfo_children():
            w.destroy()

    def _setup_create_tab(self):
        t = self.tab_create
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(t, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text="Create Video", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w")

        input_frame = ctk.CTkFrame(top, fg_color="transparent")
        input_frame.pack(fill="x", pady=(8, 0))
        input_frame.grid_columnconfigure(0, weight=1)

        self.topic_entry = ctk.CTkTextbox(input_frame, height=100, corner_radius=8, border_width=1)
        self.topic_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.topic_entry.insert("1.0", "Enter topic or describe what video you want to create...")

        btn_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="n")
        self.refine_btn = ctk.CTkButton(btn_frame, text="Refine with AI", width=120, height=34, command=self._refine_topic)
        self.refine_btn.pack(pady=(0, 6))
        self.generate_btn = ctk.CTkButton(btn_frame, text="Generate Video", width=120, height=38, fg_color="#2b7a4b", hover_color="#236b3f", font=ctk.CTkFont(weight="bold"), command=self._generate_video)
        self.generate_btn.pack()

        opt_frame = ctk.CTkFrame(top, fg_color="transparent")
        opt_frame.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(opt_frame, text="Orientation:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 8))
        self.orientation_var = ctk.StringVar(value=self.config.orientation)
        ctk.CTkOptionMenu(opt_frame, values=["horizontal", "vertical", "square"],
                          variable=self.orientation_var, width=130).pack(side="left")

        self.create_scroll = ctk.CTkScrollableFrame(t, fg_color="transparent")
        self.create_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(8, 10))
        self.create_scroll.grid_columnconfigure(0, weight=1)

        self.create_status = ctk.CTkLabel(self.create_scroll, text="Enter a topic and click Generate Video", font=ctk.CTkFont(size=13), text_color="gray")
        self.create_status.grid(row=0, column=0, pady=40)

        self.create_progress_frame = ctk.CTkFrame(self.create_scroll, fg_color="transparent")
        self.create_result_frame = ctk.CTkFrame(self.create_scroll, fg_color="transparent")

    def _refine_topic(self):
        text = self.topic_entry.get("1.0", "end-1c").strip()
        if not text or text == "Enter topic or describe what video you want to create...":
            messagebox.showwarning("Empty", "Enter a topic first.")
            return
        key = self.config.gemini_key
        if not key:
            messagebox.showwarning("API Key", "Set your Gemini API key in Settings tab first.")
            return
        self.refine_btn.configure(state="disabled", text="Refining...")
        threading.Thread(target=self._refine_thread, args=(text, key), daemon=True).start()

    def _refine_thread(self, text, key):
        try:
            from brain.director import Director
            d = Director(key)
            orientation = getattr(self, 'orientation_var', None)
            orient = orientation.get() if orientation else "horizontal"
            scenes = d.generate_script(text, orient)
            summary = f"AI refined your idea into {len(scenes)} scenes.\n"
            for i, s in enumerate(scenes[:5]):
                summary += f"\n{i+1}. {s.get('narration_text', '')[:80]}"
            if len(scenes) > 5:
                summary += f"\n...and {len(scenes)-5} more scenes"
            self.after(0, self._show_refined, summary)
        except Exception as e:
            self.after(0, self._refine_error, str(e))

    def _show_refined(self, summary):
        self.refine_btn.configure(state="normal", text="Refine with AI")
        self._clear_frame(self.create_status)
        self.create_status.grid_remove()
        self.create_status = ctk.CTkLabel(self.create_scroll, text=summary, font=ctk.CTkFont(size=13), justify="left", wraplength=600)
        self.create_status.grid(row=0, column=0, pady=20, sticky="w")

    def _refine_error(self, msg):
        self.refine_btn.configure(state="normal", text="Refine with AI")
        messagebox.showerror("Error", f"AI refinement failed:\n{msg}")

    def _generate_video(self):
        text = self.topic_entry.get("1.0", "end-1c").strip()
        if not text or text == "Enter topic or describe what video you want to create...":
            messagebox.showwarning("Empty", "Enter a topic first.")
            return
        key = self.config.gemini_key
        if not key:
            messagebox.showwarning("API Key", "Set your Gemini API key in Settings tab first.")
            return
        self.generate_btn.configure(state="disabled", text="Generating...")
        self.refine_btn.configure(state="disabled")

        self._clear_frame(self.create_progress_frame)
        self._clear_frame(self.create_result_frame)
        self.create_progress_frame.grid(row=1, column=0, sticky="ew", pady=10)
        self.create_progress_frame.grid_columnconfigure(0, weight=1)
        self.create_result_frame.grid_remove()

        self.prog_bar = ctk.CTkProgressBar(self.create_progress_frame, height=14, corner_radius=7)
        self.prog_bar.grid(row=0, column=0, sticky="ew", pady=(10, 4))
        self.prog_bar.set(0)
        self.prog_text = ctk.CTkLabel(self.create_progress_frame, text="Starting...", font=ctk.CTkFont(size=13))
        self.prog_text.grid(row=1, column=0, pady=2)
        self.prog_sub = ctk.CTkLabel(self.create_progress_frame, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.prog_sub.grid(row=2, column=0, pady=(0, 8))
        self.cancel_create_btn = ctk.CTkButton(self.create_progress_frame, text="Cancel", width=80, fg_color="#a33", command=self._cancel_create)
        self.cancel_create_btn.grid(row=3, column=0, pady=4)

        orientation = self.orientation_var.get()
        self.pipeline = VideoPipeline(key, str(Path.home() / "YTTransformer"), self.ffmpeg.path(), orientation)
        self.pipeline.on_progress(self._create_progress)
        threading.Thread(target=self._generate_thread, args=(text,), daemon=True).start()

    def _generate_thread(self, text):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            output = loop.run_until_complete(self.pipeline.run(text))
            loop.close()
            self.after(0, self._create_done, output)
        except Exception as e:
            if not getattr(self.pipeline, '_cancelled', False):
                self.after(0, self._create_error, str(e))

    def _create_progress(self, d):
        stage = d.get("stage", "")
        pct = d.get("percent", 0)
        msg = d.get("message", "")
        stages = {
            "script_generation": "Script Generation",
            "clip_search": "Clip Search",
            "downloading": "Downloading",
            "narration": "Narration",
            "transitions": "Transitions",
            "assembling": "Assembling",
            "rendering": "Rendering",
        }
        stage_name = stages.get(stage, stage)
        self.after(0, lambda: self._update_progress_ui(stage_name, pct, msg))

    def _update_progress_ui(self, stage, pct, msg):
        self.prog_bar.set(pct)
        self.prog_text.configure(text=f"{stage}")
        self.prog_sub.configure(text=msg)

    def _create_done(self, output):
        self.generate_btn.configure(state="normal", text="Generate Video")
        self.refine_btn.configure(state="normal")
        self.cancel_create_btn.grid_remove()
        self.prog_bar.set(1)
        self.prog_text.configure(text="Complete!")
        self.prog_sub.configure(text="")
        self._clear_frame(self.create_result_frame)
        self.create_result_frame.grid(row=2, column=0, sticky="ew", pady=10)
        self.create_result_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.create_result_frame, text="Video Created!", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ctk.CTkLabel(self.create_result_frame, text=str(output), text_color="gray", font=ctk.CTkFont(size=12)).grid(row=1, column=0, columnspan=3, sticky="w")
        btn_frame = ctk.CTkFrame(self.create_result_frame, fg_color="transparent")
        btn_frame.grid(row=2, column=0, columnspan=3, pady=10)
        ctk.CTkButton(btn_frame, text="Open Video", command=lambda: open_file(output)).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="Open Folder", fg_color="#444", command=lambda: open_folder(output)).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="Create Another", fg_color="#333", command=self._reset_create).pack(side="left", padx=4)

    def _create_error(self, msg):
        self.generate_btn.configure(state="normal", text="Generate Video")
        self.refine_btn.configure(state="normal")
        self.cancel_create_btn.grid_remove()
        self.prog_bar.set(0)
        self.prog_text.configure(text=f"Error: {msg[:100]}")
        self.prog_sub.configure(text="")

    def _cancel_create(self):
        if self.pipeline:
            self.pipeline.cancel()
        self.prog_text.configure(text="Cancelled")
        self.cancel_create_btn.configure(state="disabled")
        self.generate_btn.configure(state="normal", text="Generate Video")
        self.refine_btn.configure(state="normal")

    def _reset_create(self):
        self._clear_frame(self.create_progress_frame)
        self._clear_frame(self.create_result_frame)
        self.create_progress_frame.grid_remove()
        self.create_result_frame.grid_remove()
        self.prog_bar = None
        self.topic_entry.delete("1.0", "end")
        self.topic_entry.insert("1.0", "Enter topic or describe what video you want to create...")
        self.create_status = ctk.CTkLabel(self.create_scroll, text="Enter a topic and click Generate Video", font=ctk.CTkFont(size=13), text_color="gray")
        self.create_status.grid(row=0, column=0, pady=40)

    def _setup_settings_tab(self):
        t = self.tab_settings
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(t, text="Settings", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 16))

        key_frame = ctk.CTkFrame(t, fg_color="transparent")
        key_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        key_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(key_frame, text="Gemini API Key:", font=ctk.CTkFont(size=14)).grid(row=0, column=0, sticky="w", padx=(0, 10))
        current_key = self.config.gemini_key
        masked = current_key[:8] + "..." if current_key else ""
        self.key_var = ctk.StringVar(value=current_key)
        self.key_entry = ctk.CTkEntry(key_frame, textvariable=self.key_var, show="*", height=34)
        self.key_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.key_entry.configure(placeholder_text="Enter your Google Gemini API key")
        self.toggle_key_btn = ctk.CTkButton(key_frame, text="Show", width=60, height=34, command=self._toggle_key_visibility)
        self.toggle_key_btn.grid(row=0, column=2, padx=(0, 4))
        self.save_key_btn = ctk.CTkButton(key_frame, text="Save", width=60, height=34, fg_color="#2b7a4b", command=self._save_key)
        self.save_key_btn.grid(row=0, column=3)

        out_frame = ctk.CTkFrame(t, fg_color="transparent")
        out_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        out_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(out_frame, text="Output Directory:", font=ctk.CTkFont(size=14)).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.out_var = ctk.StringVar(value=str(self.config.output_dir))
        ctk.CTkEntry(out_frame, textvariable=self.out_var, height=34).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkButton(out_frame, text="Browse", width=80, height=34, command=self._browse_output).grid(row=0, column=2)

        res_frame = ctk.CTkFrame(t, fg_color="transparent")
        res_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=4)
        ctk.CTkLabel(res_frame, text="Max Resolution:", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
        self.res_var = ctk.StringVar(value=self.config.max_resolution)
        ctk.CTkOptionMenu(res_frame, values=["1080p", "720p", "480p"], variable=self.res_var, width=100).pack(side="left")

        save_all = ctk.CTkButton(t, text="Save All Settings", height=38, font=ctk.CTkFont(weight="bold"), command=self._save_all_settings)
        save_all.grid(row=4, column=0, sticky="w", padx=10, pady=16)

        self.settings_status = ctk.CTkLabel(t, text="", font=ctk.CTkFont(size=12), text_color="green")
        self.settings_status.grid(row=5, column=0, sticky="nw", padx=10)

    def _toggle_key_visibility(self):
        if self.key_entry.cget("show") == "*":
            self.key_entry.configure(show="")
            self.toggle_key_btn.configure(text="Hide")
        else:
            self.key_entry.configure(show="*")
            self.toggle_key_btn.configure(text="Show")

    def _save_key(self):
        key = self.key_var.get().strip()
        if key:
            self.config.gemini_key = key
            self.settings_status.configure(text="API key saved locally.", text_color="green")
        else:
            self.settings_status.configure(text="No key entered.", text_color="red")

    def _browse_output(self):
        path = ctk.filedialog.askdirectory(initialdir=str(self.config.output_dir))
        if path:
            self.out_var.set(path)
            self.config.output_dir = path

    def _save_all_settings(self):
        key = self.key_var.get().strip()
        if key:
            self.config.gemini_key = key
        self.config.output_dir = self.out_var.get()
        self.config.max_resolution = self.res_var.get()
        self.settings_status.configure(text="All settings saved.", text_color="green")


if __name__ == "__main__":
    app = App()
    app.mainloop()
