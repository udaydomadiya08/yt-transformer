#!/usr/bin/env python3
"""
Build script: packages the app as standalone executables.
Usage:
  python build.py           # build GUI + CLI, package as zip/tar.gz
  python build.py --cli-only  # build CLI only
  python build.py --clean     # remove build artifacts
"""
import sys, shutil, platform, subprocess, zipfile, tarfile
from pathlib import Path

APP_NAME = "YTTransformer"
GUI_SCRIPT = "main.py"
CLI_SCRIPT = "cli.py"
PLATFORM = platform.system()
ARCH = platform.machine()

def log(msg): print(f"[build] {msg}")

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

def _hidden_imports():
    pkgs = ["customtkinter", "yt_dlp", "PIL", "PIL._tkinter_finder", "requests",
            "charset_normalizer", "moviepy", "moviepy.editor", "moviepy.audio.fx.all",
            "edge_tts", "google", "google.genai"]
    modules = ["engine", "engine.searcher", "engine.clipper",
               "brain", "brain.director", "brain.matcher",
               "composer", "composer.mixer", "composer.assembler", "composer.renderer", "composer.subtitler",
               "utils", "utils.config", "utils.cleanup", "utils.cookies", "pipeline"]
    result = []
    for p in pkgs:
        result += ["--hidden-import", p]
    for m in modules:
        result += ["--hidden-import", m]
    return result

def _data_dirs():
    result = []
    sep = ";" if PLATFORM == "Windows" else ":"
    result += ["--add-data", f"requirements.txt{sep}."]
    for pkg in ["engine", "brain", "composer", "utils"]:
        pkg_path = Path(pkg)
        if pkg_path.is_dir():
            result += ["--add-data", f"{pkg}{sep}{pkg}"]
    return result

def _pyinstaller(script, name, windowed=False):
    check_deps()
    upx = shutil.which("upx")
    cmd = [sys.executable, "-m", "PyInstaller", "--name", name,
           "--noconfirm", "--clean", "--onedir"]
    if PLATFORM == "Darwin" and windowed:
        cmd += ["--windowed"]
    if upx:
        cmd += ["--upx-dir", str(Path(upx).parent)]
    cmd += _hidden_imports() + _data_dirs()
    icon = None
    if PLATFORM == "Darwin":
        icon = "icon.icns" if Path("icon.icns").exists() else None
    elif PLATFORM == "Windows":
        icon = "icon.ico" if Path("icon.ico").exists() else None
    else:
        icon = "icon.png" if Path("icon.png").exists() else None
    if icon and windowed:
        cmd += ["--icon", icon]
    cmd.append(script)
    log(f"PyInstaller: {name}")
    subprocess.check_call(cmd)

def _package_dir(src_dir, archive_name):
    """Zip (Windows) or tar.gz (others) a directory into dist/."""
    dist = Path("dist")
    dist.mkdir(parents=True, exist_ok=True)
    if not src_dir.exists():
        log(f"  SKIP: {src_dir} not found")
        return None
    if PLATFORM == "Windows":
        archive = dist / f"{archive_name}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for f in src_dir.rglob("*"):
                if f.is_file():
                    z.write(f, arcname=f.relative_to(src_dir.parent))
    else:
        archive = dist / f"{archive_name}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(src_dir, arcname=src_dir.name)
    log(f"  Package: {archive} ({archive.stat().st_size / 1024 / 1024:.0f} MB)")
    return archive

def _clean_dist():
    dist = Path("dist")
    if not dist.exists():
        return
    keep = (".zip", ".dmg", ".AppImage", ".exe")
    for p in dist.iterdir():
        if p.suffix in keep or p.name.endswith(".tar.gz"):
            continue
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()

def build():
    log(f"Building {APP_NAME} for {PLATFORM} ({ARCH})...")

    # Build GUI
    _pyinstaller(GUI_SCRIPT, APP_NAME, windowed=True)
    gui_dir = Path("dist") / APP_NAME
    suffix = {"Darwin": "macOS", "Windows": "Windows"}.get(PLATFORM, "Linux")
    if PLATFORM == "Darwin":
        gui_dir = Path("dist") / f"{APP_NAME}.app"
    _package_dir(gui_dir, f"{APP_NAME}-{suffix}")

    # Build CLI
    _pyinstaller(CLI_SCRIPT, f"{APP_NAME}-cli")
    cli_dir = Path("dist") / f"{APP_NAME}-cli"
    cli_suffix = {"Darwin": "macOS", "Windows": "Windows"}.get(PLATFORM, "Linux")
    _package_dir(cli_dir, f"{APP_NAME}-cli-{cli_suffix}")

    _clean_dist()
    log("Build complete!")

def build_cli_only():
    _pyinstaller(CLI_SCRIPT, f"{APP_NAME}-cli")
    cli_dir = Path("dist") / f"{APP_NAME}-cli"
    suffix = {"Darwin": "macOS", "Windows": "Windows"}.get(PLATFORM, "Linux")
    _package_dir(cli_dir, f"{APP_NAME}-cli-{suffix}")
    _clean_dist()
    log("CLI build complete!")

def clean():
    for f in ["build", "dist", "__pycache__"]:
        p = Path(f)
        if p.exists(): shutil.rmtree(p); log(f"Removed {f}")
    for p in Path(".").glob("*.spec"): p.unlink(); log(f"Removed {p}")

if __name__ == "__main__":
    if "--clean" in sys.argv: clean()
    elif "--cli-only" in sys.argv: build_cli_only()
    else: build()
