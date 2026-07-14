import shutil
import tempfile
from pathlib import Path

class TempManager:
    def __init__(self):
        self._dirs = []

    def create_temp_dir(self, prefix="yttransform_"):
        d = Path(tempfile.mkdtemp(prefix=prefix))
        self._dirs.append(d)
        return d

    def cleanup_all(self):
        for d in self._dirs:
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
        self._dirs.clear()

    def cleanup_dir(self, d):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        if d in self._dirs:
            self._dirs.remove(d)

    def __del__(self):
        self.cleanup_all()
