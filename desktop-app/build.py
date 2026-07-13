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
        separator = "--onedir"
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
    # Clean up PyInstaller internals
    _clean_dist_except(["*.dmg", "*.zip", "*.tar.gz", "*.AppImage", "*.exe"])

def _clean_dist_except(patterns):
    """Remove loose files in dist/ not matching any pattern (keep only archives)."""
    dist = Path("dist")
    if not dist.exists():
        return
    import fnmatch
    garbage = {"base_library.zip", "warnings.txt", "PyInstaller"}
    for p in dist.iterdir():
        if p.name in garbage:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
        elif p.is_dir() and p.name != APP_NAME:
            shutil.rmtree(p)
        elif p.is_file() and not any(fnmatch.fnmatch(p.name, pat) for pat in patterns):
            p.unlink()

def _package_windows():
    """Create a .zip portable archive."""
    import zipfile
    exe = Path("dist") / f"{APP_NAME}.exe"
    if exe.exists():
        log(f"EXE: {exe.resolve()}")
        archive = Path("dist") / f"{APP_NAME}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(exe, arcname=exe.name)
        log(f"Created: {archive}")
    else:
        # onedir mode: zip the whole directory
        app_dir = Path("dist") / APP_NAME
        if app_dir.exists():
            archive = Path("dist") / f"{APP_NAME}.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                for f in app_dir.rglob("*"):
                    z.write(f, arcname=f.relative_to(app_dir.parent))
            log(f"Created: {archive}")
    _clean_dist_except(["*.dmg", "*.zip", "*.tar.gz", "*.AppImage", "*.exe"])

def _package_linux():
    """Create a .tar.gz portable archive."""
    app_dir = Path("dist") / APP_NAME
    if not app_dir.exists():
        return
    log(f"Packaging Linux build from: {app_dir.resolve()}")
    import tarfile, struct, zlib
    archive = Path("dist") / f"{APP_NAME}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(app_dir, arcname=APP_NAME)
    log(f"Created: {archive}")

    # Best-effort AppImage via linuxdeploy
    deploy = shutil.which("linuxdeploy") or (Path("/tmp/linuxdeploy") if Path("/tmp/linuxdeploy").exists() else None)
    if not deploy:
        return
    log("linuxdeploy found, creating AppImage...")
    appdir = Path(f"/tmp/{APP_NAME}.AppDir")
    if appdir.exists():
        shutil.rmtree(appdir)
    (appdir / "usr/bin").mkdir(parents=True)
    for item in app_dir.iterdir():
        if item.is_dir():
            shutil.copytree(item, appdir / "usr/bin" / item.name)
        else:
            shutil.copy2(item, appdir / "usr/bin" / item.name)
    # Desktop entry with Icon
    (appdir / "usr/share/applications").mkdir(parents=True)
    desktop = appdir / "usr/share/applications" / f"{APP_NAME}.desktop"
    desktop.write_text(f"[Desktop Entry]\nName={APP_NAME}\nExec={APP_NAME}\nType=Application\nIcon={APP_NAME}\nCategories=Utility;\n")
    (appdir / f"{APP_NAME}.desktop").symlink_to(f"usr/share/applications/{APP_NAME}.desktop")
    # Minimal 1x1 PNG icon so linuxdeploy doesn't fail
    icon_dir = appdir / "usr/share/icons/hicolor/256x256/apps"
    icon_dir.mkdir(parents=True)
    # 1x1 red PNG (valid minimal PNG)
    raw = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0) + struct.pack('>I', 0) + b'IDAT' + struct.pack('>I', zlib.crc32(b'IDAT' + zlib.compress(b'\x00\xff\x00\x00\xff')) & 0xffffffff) + b'IEND' + struct.pack('>I', zlib.crc32(b'IEND') & 0xffffffff)
    (icon_dir / f"{APP_NAME}.png").write_bytes(raw)
    # AppRun
    apprun = appdir / "AppRun"
    apprun.write_text("#!/bin/bash\nSELF=\"$(readlink -f \"$0\")\"\nHERE=\"${SELF%/*}\"\nexec \"$HERE/usr/bin/main\" \"$@\"\n")
    apprun.chmod(0o755)
    # Run linuxdeploy (best-effort)
    try:
        subprocess.check_call([str(deploy), "--appdir", str(appdir), "--output", "appimage"], timeout=180)
        import glob
        for f in glob.glob(f"/tmp/{APP_NAME}*.AppImage"):
            shutil.copy(f, Path("dist") / f"{APP_NAME}.AppImage")
            log(f"AppImage: dist/{APP_NAME}.AppImage")
            break
    except Exception as e:
        log(f"AppImage skipped: {e}")
    _clean_dist_except(["*.dmg", "*.zip", "*.tar.gz", "*.AppImage", "*.exe"])

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
