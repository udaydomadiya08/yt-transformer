import time
import subprocess
import sys
from pathlib import Path


APP_NAME = "YTTransformer"

def _appdata_dir():
    import platform
    home = Path.home()
    sys_name = platform.system()
    if sys_name == "Darwin":
        return home / "Library" / "Application Support" / APP_NAME
    elif sys_name == "Windows":
        return Path(__import__('os').environ.get("APPDATA", home / "AppData" / "Roaming")) / APP_NAME
    else:
        return home / ".config" / APP_NAME


CACHE_FILE = _appdata_dir() / "browser_cache"
TS_FILE = _appdata_dir() / "browser_cache_ts"
CACHE_TTL = 86400  # 24 hours


def _detect_browser_cache():
    if CACHE_FILE.exists() and TS_FILE.exists():
        try:
            last = float(TS_FILE.read_text().strip())
            if time.time() - last < CACHE_TTL:
                val = CACHE_FILE.read_text().strip()
                return val if val != "none" else None
        except (ValueError, OSError):
            pass
    return None


def _write_cache(browser):
    _appdata_dir().mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(browser if browser else "none")
    TS_FILE.write_text(str(time.time()))


def detect_browser(force_redetect=False):
    if not force_redetect:
        cached = _detect_browser_cache()
        if cached is not None:
            return cached

    browsers = ["chrome", "firefox", "edge", "brave", "opera", "chromium", "vivaldi", "safari"]
    for b in browsers:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "yt_dlp", "--cookies-from-browser", b, "--dump-json",
                 "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode == 0 and r.stdout.strip():
                _write_cache(b)
                return b
        except Exception:
            continue

    _write_cache(None)
    return None
