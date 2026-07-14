from pathlib import Path

class RenderProgress:
    def __init__(self):
        self.stage = ""
        self.percent = 0
        self.message = ""
        self._callbacks = []

    def on_update(self, cb):
        self._callbacks.append(cb)

    def set(self, stage, percent, message=""):
        self.stage = stage
        self.percent = percent
        self.message = message
        for cb in self._callbacks:
            cb(self)

class Renderer:
    def __init__(self, temp_manager, output_dir):
        self.temp = temp_manager
        self.output_dir = Path(output_dir)
        self.progress = RenderProgress()

    def render(self, final_clip, filename="final_video.mp4"):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / filename

        self.progress.set("rendering", 0, "Starting render...")

        try:
            final_clip.write_videofile(
                str(output_path),
                codec="libx264",
                audio_codec="aac",
                preset="medium",
                fps=30,
                threads=2,
                bitrate="5000k",
                verbose=False,
            )
        except Exception as e:
            self.progress.set("error", 0, f"Render failed: {e}")
            raise

        self.progress.set("done", 1.0, f"Done: {output_path}")
        return output_path

    def render_with_cleanup(self, final_clip, filename="final_video.mp4"):
        try:
            return self.render(final_clip, filename)
        finally:
            final_clip.close()
            self.temp.cleanup_all()

    def cleanup_temp(self):
        self.temp.cleanup_all()
