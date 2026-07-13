#!/usr/bin/env python3
"""
Build script: packages the app as standalone executable.
Usage:
  python build.py          # detect platform, build
  python build.py --dmg   # macOS: create DMG after build
  python build.py --clean  # remove build artifacts
"""
import sys
import os
import shutil
import platform
import subprocess
from pathlib import Path

APP_NAME = "YTDownloader"
MAIN_SCRIPT = "main.py"

PLATFORM = platform.system()
ARCH = platform.machine()
IS_ARM = ARCH in ("arm64", "aarch64")

def log(msg):
    print(f"[build] {msg}")

def check_deps():
    try:
        import PyInstaller
    except ImportError:
        log("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    try:
        import customtkinter
    except ImportError:
        log("Installing dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def build():
    check_deps()
    log(f"Building {APP_NAME} for {PLATFORM} ({ARCH})...")

    name = APP_NAME
    icon = None
    separator = "--onedir"

    if PLATFORM == "Darwin":
        icon = "YTDownloader.icns" if Path("YTDownloader.icns").exists() else ("icon.icns" if Path("icon.icns").exists() else None)
        separator = "--onedir"
    elif PLATFORM == "Windows":
        icon = "icon.ico" if Path("icon.ico").exists() else None
        separator = "--onefile"
    else:
        icon = "icon.png" if Path("icon.png").exists() else None
        separator = "--onedir"

    hidden = [
        "--hidden-import", "customtkinter",
        "--hidden-import", "yt_dlp",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "requests",
        "--hidden-import", "charset_normalizer",
    ]
    data = [
        "--add-data", f"requirements.txt{';' if PLATFORM == 'Windows' else ':'}.",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", name,
        "--noconfirm",
        "--clean",
        separator,
    ]
    if PLATFORM == "Darwin":
        cmd += ["--windowed"]
    cmd += hidden + data
    if icon:
        cmd += ["--icon", icon]
    cmd.append(MAIN_SCRIPT)

    log("Running PyInstaller...")
    subprocess.check_call(cmd)
    log("Build complete!")

    dist_dir = Path("dist") / name
    if dist_dir.exists():
        log(f"Output: {dist_dir.resolve()}")
        if PLATFORM == "Darwin":
            app_path = dist_dir.with_suffix(".app")
            if app_path.exists():
                log(f"App bundle: {app_path.resolve()}")

    # Package for platform
    if PLATFORM == "Darwin":
        _package_macos(dist_dir)
    elif PLATFORM == "Windows":
        _package_windows()
    else:
        _package_linux()

def _package_macos(dist_dir):
    """Create a .dmg from the .app bundle."""
    dmg = Path("dist") / f"{APP_NAME}.dmg"
    if dmg.exists():
        dmg.unlink()

    app_path = Path("dist") / f"{APP_NAME}.app"
    if not app_path.exists():
        log("No .app found, skipping DMG")
        return

    # Try create-dmg if available, else use hdiutil
    if shutil.which("create-dmg"):
        log("Creating DMG with create-dmg...")
        subprocess.check_call([
            "create-dmg",
            "--volname", APP_NAME,
            "--window-pos", "200", "120",
            "--window-size", "600", "400",
            "--icon-size", "100",
            f"--app-drop-link", "400", "200",
            str(dmg),
            str(app_path),
        ])
    else:
        log("Using hdiutil to create DMG...")
        tmp_dir = Path("/tmp") / APP_NAME
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True)
        shutil.copytree(app_path, tmp_dir / f"{APP_NAME}.app")
        subprocess.check_call([
            "hdiutil", "create", "-volname", APP_NAME,
            "-srcfolder", str(tmp_dir),
            "-ov", "-format", "UDZO",
            str(dmg),
        ])
        shutil.rmtree(tmp_dir)

    if dmg.exists():
        log(f"DMG: {dmg.resolve()}")

def _package_windows():
    """Create an installer or just show where the exe is."""
    exe = Path("dist") / f"{APP_NAME}.exe"
    if exe.exists():
        log(f"EXE: {exe.resolve()}")
        log("Run the exe directly or wrap with Inno Setup for an installer.")

def _package_linux():
    """Create an AppImage."""
    app_dir = Path("dist") / APP_NAME
    if not app_dir.exists():
        return
    log(f"Linux build in: {app_dir.resolve()}")
    log("To create AppImage, use appimagetool or linuxdeploy.")

def clean():
    folders = ["build", "dist", "__pycache__"]
    files = ["*.spec"]
    for f in folders:
        p = Path(f)
        if p.exists():
            shutil.rmtree(p)
            log(f"Removed {f}")
    for pattern in files:
        for p in Path(".").glob(pattern):
            p.unlink()
            log(f"Removed {p}")

if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean()
    else:
        build()
        if "--dmg" in sys.argv and PLATFORM == "Darwin":
            pass  # already done in build()
