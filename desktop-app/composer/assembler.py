import subprocess
from pathlib import Path
from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeAudioClip,
    concatenate_videoclips, CompositeVideoClip,
)
from moviepy.audio.fx.all import volumex
from composer.subtitler import estimate_word_timestamps, overlay_subtitles

ORIENTATIONS = {
    "horizontal": (1920, 1080),
    "vertical": (1080, 1920),
    "square": (1080, 1080),
}

def resample_clip(input_path, output_path, target_w, target_h, duration):
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},setsar=1",
        "-t", str(duration + 0.5),
        "-r", "30",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        return Path(output_path)
    except Exception as e:
        raise RuntimeError(f"FFmpeg resample failed: {e}")

class ClipAssembly:
    def __init__(self, temp_manager, orientation="horizontal"):
        self.temp = temp_manager
        self.orientation = orientation
        self.target_w, self.target_h = ORIENTATIONS.get(orientation, (1920, 1080))

    def _resample_if_needed(self, clip_path, target_dur):
        clip = VideoFileClip(str(clip_path))
        needs_resample = (clip.w != self.target_w or clip.h != self.target_h)
        clip.close()
        if not needs_resample:
            return clip_path
        out = self.temp.create_temp_dir() / f"resampled_{clip_path.stem}.mp4"
        resample_clip(clip_path, out, self.target_w, self.target_h, target_dur)
        return out

    def build_scene_clip(self, video_path, audio_path, narration_path, scene_config, music_path=None, word_segments=None):
        target_dur = scene_config.get("duration_sec", 4)

        src = self._resample_if_needed(video_path, target_dur)
        clip = VideoFileClip(str(src)).set_duration(target_dur)

        vol = scene_config.get("volume_ratios", {})
        orig_vol = scene_config.get("original_audio", {}).get("volume", 0.5) or vol.get("original", 0.5)
        narr_vol = scene_config.get("narration", {}).get("volume", 0.9) or vol.get("narration", 0.9)
        music_vol = scene_config.get("music_bg", {}).get("volume", 0.2) or vol.get("music", 0.2)
        orig_enabled = scene_config.get("original_audio", {}).get("enabled", True)
        narr_enabled = scene_config.get("narration", {}).get("enabled", True)
        music_enabled = scene_config.get("music_bg", {}).get("enabled", False)

        audio_sources = []
        if orig_enabled and orig_vol > 0 and audio_path and Path(audio_path).exists():
            orig_audio = AudioFileClip(str(audio_path)).fx(volumex, orig_vol)
            audio_sources.append(orig_audio)
        if narr_enabled and narr_vol > 0 and narration_path and Path(narration_path).exists():
            narr_audio = AudioFileClip(str(narration_path)).fx(volumex, narr_vol)
            audio_sources.append(narr_audio)
        if music_enabled and music_vol > 0 and music_path and Path(music_path).exists():
            music_audio = AudioFileClip(str(music_path)).fx(volumex, music_vol)
            audio_sources.append(music_audio)

        if audio_sources:
            mixed = CompositeAudioClip(audio_sources)
            if mixed.duration > target_dur:
                mixed = mixed.subclip(0, target_dur)
            clip = clip.set_audio(mixed)
        else:
            clip = clip.set_audio(None)

        treatment = scene_config.get("clip", {}).get("treatment", "normal")
        if treatment == "zoom_in":
            clip = clip.resize(lambda t: 1 + 0.05 * t / target_dur)
        elif treatment == "zoom_out":
            clip = clip.resize(lambda t: 1.05 - 0.05 * t / target_dur)

        sub_config = scene_config.get("subtitles", {})
        if sub_config.get("enabled", False) and word_segments:
            clip = overlay_subtitles(clip, word_segments, (self.target_w, self.target_h), sub_config)

        return clip

    def assemble(self, scenes, clip_paths, transitions, word_segments_list=None):
        video_clips = []
        for i, scene in enumerate(scenes):
            paths = clip_paths[i]
            segs = None
            if word_segments_list and i < len(word_segments_list):
                segs = word_segments_list[i]
            clip = self.build_scene_clip(
                video_path=paths.get("video"),
                audio_path=paths.get("audio"),
                narration_path=paths.get("narration"),
                scene_config=scene,
                music_path=paths.get("music"),
                word_segments=segs,
            )
            video_clips.append(clip)

        if not video_clips:
            raise RuntimeError("No clips to assemble")

        final = video_clips[0]
        for i in range(1, len(video_clips)):
            trans = "crossfade"
            if transitions and i - 1 < len(transitions):
                t_obj = transitions[i - 1]
                if isinstance(t_obj, dict):
                    trans = t_obj.get("transition", "crossfade")
                elif isinstance(t_obj, str):
                    trans = t_obj
            if trans == "crossfade":
                final = concatenate_videoclips([final, video_clips[i]], method="compose", padding=-0.25)
            else:
                final = concatenate_videoclips([final, video_clips[i]])
        return final
