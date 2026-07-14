import asyncio
import uuid
import json
from pathlib import Path

from engine.searcher import Searcher
from engine.clipper import Clipper
from brain.director import Director
from brain.matcher import Matcher
from composer.mixer import AudioMixer
from composer.assembler import ClipAssembly
from composer.renderer import Renderer
from composer.subtitler import estimate_word_timestamps
from utils.cleanup import TempManager


class VideoPipeline:
    def __init__(self, gemini_key, output_dir, ffmpeg_path="ffmpeg", orientation="horizontal"):
        self.temp = TempManager()
        self.director = Director(gemini_key)
        self.matcher = Matcher(self.director)
        self.searcher = Searcher(ffmpeg_path)
        self.clipper = Clipper(ffmpeg_path, output_dir=str(self.temp.create_temp_dir()))
        self.mixer = AudioMixer()
        self.assembler = ClipAssembly(self.temp, orientation)
        self.renderer = Renderer(self.temp, output_dir)
        self._progress_cb = None
        self._cancelled = False

    def on_progress(self, cb):
        self._progress_cb = cb
        self.renderer.progress.on_update(cb)

    def _progress(self, stage, pct, msg=""):
        if self._progress_cb and not self._cancelled:
            self._progress_cb({"stage": stage, "percent": pct, "message": msg})

    def cancel(self):
        self._cancelled = True

    async def run(self, user_input):
        self._cancelled = False
        video_id = str(uuid.uuid4())[:8]

        orientation = getattr(self.assembler, 'orientation', 'horizontal')
        is_vertical = orientation == "vertical"
        self._progress("script_generation", 0.05, f"Generating script with AI ({orientation})...")
        scenes = self.director.generate_script(user_input, orientation)
        if not scenes:
            raise RuntimeError("Failed to generate script")
        scenes = self._normalize_scenes(scenes)

        self._progress("script_generation", 0.1, f"Script ready: {len(scenes)} scenes")

        self._progress("clip_search", 0.15, "Searching for matching clips...")
        scene_data = []
        for i, scene in enumerate(scenes):
            if self._cancelled:
                raise RuntimeError("Cancelled")
            pct = 0.15 + (i / len(scenes)) * 0.35
            self._progress("clip_search", pct, f"Finding clips for scene {i+1}/{len(scenes)}")

            candidates = self.searcher.find_clips_for_scene(scene)
            best_clip = self.matcher.select_best_clip(candidates, scene.get("narration_text", ""))

            if not best_clip:
                scene["clip"]["enabled"] = True
                alt_search = scene.get("search_query", "")
                alt_candidates = self.searcher.search_videos(alt_search + " broll footage", max_results=3)
                best_clip = self._find_any_usable_clip(alt_candidates, scene)

            scene_data.append({
                "scene": scene,
                "clip": best_clip,
            })

        self._progress("downloading", 0.5, "Downloading clips...")
        clip_paths = []
        for i, sd in enumerate(scene_data):
            if self._cancelled:
                raise RuntimeError("Cancelled")
            scene = sd["scene"]
            clip_info = sd["clip"]
            pct = 0.5 + (i / len(scene_data)) * 0.15
            self._progress("downloading", pct, f"Downloading clip {i+1}/{len(scene_data)}")

            if clip_info:
                clip_id = f"{video_id}_s{i:03d}"
                start = clip_info["start"]
                end = clip_info["end"]
                dur = end - start
                scene["duration_sec"] = min(scene.get("duration_sec", 4), dur)

                v_path = self.clipper.download_video_segment(clip_info["url"], start, end, clip_id)
                a_path = None
                if scene.get("original_audio", {}).get("enabled", True):
                    a_path = self.clipper.download_audio_segment(clip_info["url"], start, end, f"{clip_id}_audio")
                clip_paths.append({"video": v_path, "audio": a_path, "narration": None, "music": None})
            else:
                clip_paths.append({"video": None, "audio": None, "narration": None, "music": None})

        self._progress("narration", 0.68, "Generating AI narration...")
        word_segments_list = []
        for i, sd in enumerate(scene_data):
            if self._cancelled:
                raise RuntimeError("Cancelled")
            scene = sd["scene"]
            text = scene.get("narration_text", "")
            narr_enabled = scene.get("narration", {}).get("enabled", True)
            sub_enabled = scene.get("subtitles", {}).get("enabled", False)

            if text and narr_enabled:
                narr_path = self.temp.create_temp_dir() / f"{video_id}_narr_{i:03d}.mp3"
                await self.mixer.generate_narration(text, narr_path)
                clip_paths[i]["narration"] = narr_path

            if sub_enabled and text:
                narr_dur = self.mixer.get_narration_duration(text)
                segments = estimate_word_timestamps(text, narr_dur)
                word_segments_list.append(segments)
            else:
                word_segments_list.append(None)

        self._progress("transitions", 0.75, "Planning transitions...")
        transitions = self.director.suggest_transitions(scenes)

        self._progress("assembling", 0.8, "Assembling video...")
        final = self.assembler.assemble(scenes, clip_paths, transitions, word_segments_list)

        self._progress("rendering", 0.85, "Rendering final video...")
        output = self.renderer.render_with_cleanup(final, f"YTTransformer_{video_id}.mp4")

        self._progress("done", 1.0, f"Video saved: {output}")
        self.matcher.reset()
        return output

    def _normalize_scenes(self, scenes):
        if isinstance(scenes, dict) and "scenes" in scenes:
            scenes = scenes["scenes"]
        for i, s in enumerate(scenes):
            if isinstance(s, dict):
                s.setdefault("scene_number", i + 1)
                s.setdefault("duration_sec", 4)
                s.setdefault("clip", {"enabled": True, "treatment": "normal"})
                s.setdefault("original_audio", {"enabled": True, "volume": 0.5})
                s.setdefault("narration", {"enabled": True, "volume": 0.9})
                s.setdefault("music_bg", {"enabled": False, "volume": 0.0})
                s.setdefault("transition_out", "crossfade")
                s.setdefault("search_query", s.get("search_query", ""))
                s.setdefault("narration_text", s.get("narration_text", ""))
        return scenes

    def _find_any_usable_clip(self, candidates, scene):
        for vid in candidates[:3]:
            try:
                info = self.searcher.get_video_info(vid.get("webpage_url") or f"https://youtube.com/watch?v={vid.get('id')}")
                if info and info.get("duration", 0) > 10:
                    return {
                        "url": info["webpage_url"],
                        "video_id": info.get("id"),
                        "title": info.get("title", ""),
                        "start": 5,
                        "end": 9,
                        "duration": 4,
                        "matched_text": scene.get("narration_text", "")[:50],
                        "relevance_score": 0.1,
                    }
            except Exception:
                continue
        return None
