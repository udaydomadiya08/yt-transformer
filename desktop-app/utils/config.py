import json
import os
import platform
from pathlib import Path

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

class Config:
    def __init__(self):
        self.path = appdata_dir() / "config.json"
        self._data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:
                pass
        return {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    @property
    def gemini_key(self):
        return self.get("gemini_key", "")

    @gemini_key.setter
    def gemini_key(self, val):
        self.set("gemini_key", val)

    @property
    def output_dir(self):
        return Path(self.get("output_dir", str(Path.home() / "YTTransformer")))

    @output_dir.setter
    def output_dir(self, val):
        self.set("output_dir", str(val))

    @property
    def max_resolution(self):
        return self.get("max_resolution", "1080p")

    @max_resolution.setter
    def max_resolution(self, val):
        self.set("max_resolution", val)

    @property
    def orientation(self):
        return self.get("orientation", "horizontal")

    @orientation.setter
    def orientation(self, val):
        self.set("orientation", val)
