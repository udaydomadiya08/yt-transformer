#!/usr/bin/env python3
"""End-to-end demo without Gemini API calls."""
import sys, os, asyncio, time, json, copy
from pathlib import Path

sys.path.insert(0, "desktop-app")
os.environ["PYTHONIOENCODING"] = "utf-8"

# Monkey-patch: replace Director with DemoDirector
import brain.director as dr_mod
from brain.demo_director import DemoDirector
dr_mod.Director = DemoDirector

from pipeline import VideoPipeline
from engine.searcher import Searcher
from engine.clipper import Clipper
from composer.mixer import AudioMixer
from composer.assembler import ClipAssembly
from composer.renderer import Renderer
from composer.subtitler import estimate_word_timestamps
from utils.cleanup import TempManager
from brain.matcher import Matcher

OUTPUT = Path.home() / "Downloads" / "ytt_demo"
OUTPUT.mkdir(parents=True, exist_ok=True)



DEMO_SCENES = [
    {"scene_number": 1, "purpose": "intro", "search_query": "quantum computer explained animation",
     "narration_text": "Ever wondered what quantum computing actually means?",
     "duration_sec": 3, "clip": {"enabled": True, "treatment": "normal"},
     "original_audio": {"enabled": True, "volume": 0.3}, "narration": {"enabled": True, "volume": 0.9},
     "music_bg": {"enabled": False, "volume": 0.0},
     "subtitles": {"enabled": True, "style": "word_highlight", "color_active": "#00FF00", "color_passive": "#FFFF00", "fontsize": 50},
     "transition_out": "crossfade"},
    {"scene_number": 2, "purpose": "explain", "search_query": "qubits explained visually",
     "narration_text": "Regular computers use bits, zeros and ones.",
     "duration_sec": 3, "clip": {"enabled": True, "treatment": "zoom_in"},
     "original_audio": {"enabled": True, "volume": 0.3}, "narration": {"enabled": True, "volume": 0.9},
     "music_bg": {"enabled": False, "volume": 0.0},
     "subtitles": {"enabled": True, "style": "word_highlight", "color_active": "#00FF00", "color_passive": "#FFFF00", "fontsize": 50},
     "transition_out": "crossfade"},
    {"scene_number": 3, "purpose": "explain", "search_query": "superposition quantum mechanics",
     "narration_text": "But quantum computers use qubits that can be both at once.",
     "duration_sec": 3, "clip": {"enabled": True, "treatment": "zoom_out"},
     "original_audio": {"enabled": True, "volume": 0.3}, "narration": {"enabled": True, "volume": 0.9},
     "music_bg": {"enabled": False, "volume": 0.0},
     "subtitles": {"enabled": True, "style": "word_highlight", "color_active": "#00FF00", "color_passive": "#FFFF00", "fontsize": 50},
     "transition_out": "crossfade"},
    {"scene_number": 4, "purpose": "explain", "search_query": "quantum entanglement explained",
     "narration_text": "This lets them solve certain problems millions of times faster.",
     "duration_sec": 4, "clip": {"enabled": True, "treatment": "normal"},
     "original_audio": {"enabled": True, "volume": 0.3}, "narration": {"enabled": True, "volume": 0.9},
     "music_bg": {"enabled": False, "volume": 0.0},
     "subtitles": {"enabled": True, "style": "word_highlight", "color_active": "#00FF00", "color_passive": "#FFFF00", "fontsize": 50},
     "transition_out": "fade_black"},
    {"scene_number": 5, "purpose": "conclusion", "search_query": "future of quantum computing",
     "narration_text": "And that is quantum computing in a nutshell.",
     "duration_sec": 3, "clip": {"enabled": True, "treatment": "normal"},
     "original_audio": {"enabled": True, "volume": 0.3}, "narration": {"enabled": True, "volume": 0.9},
     "music_bg": {"enabled": False, "volume": 0.0},
     "subtitles": {"enabled": True, "style": "word_highlight", "color_active": "#00FF00", "color_passive": "#FFFF00", "fontsize": 50},
     "transition_out": "fade_black"},
]


def progress_cb(p):
    if isinstance(p, dict):
        stage = p.get("stage", "")
        pct = p.get("percent", 0)
        msg = p.get("message", "")
    else:
        stage = getattr(p, "stage", "")
        pct = getattr(p, "percent", 0)
        msg = getattr(p, "message", "")
    bar = "█" * int(pct * 40) + "░" * (40 - int(pct * 40))
    print(f"\r  [{bar}] {pct*100:5.1f}%  {msg}", end="")
    sys.stdout.flush()


async def run_demo():
    print("=" * 60)
    print("  YTTransformer - Demo Run (No Gemini)")
    print("=" * 60)
    print()

    temp = TempManager()
    searcher = Searcher()
    clipper = Clipper(str(temp.create_temp_dir()))
    mixer = AudioMixer()
    assembler = ClipAssembly(temp, "horizontal")
    renderer = Renderer(temp, str(OUTPUT))
    renderer.progress.on_update(progress_cb)

    print("\n[1/5] Searching for clips...")
    scene_data = []
    for i, scene in enumerate(DEMO_SCENES):
        q = scene["search_query"]
        print(f"  Scene {i+1}: searching '{q}'...")
        candidates = searcher.search_videos(q, max_results=3)
        found = None
        for c in candidates:
            try:
                info = searcher.get_video_info(c.get("webpage_url") or f"https://youtube.com/watch?v={c.get('id')}")
                if info and info.get("duration", 0) > 5:
                    found = info
                    break
            except Exception:
                continue
        if found:
            dur = found.get("duration", 60)
            start = max(2, int(dur * 0.05))
            end = min(start + 4, int(dur * 0.95))
            scene_data.append({
                "scene": scene,
                "clip": {"url": found["webpage_url"], "video_id": found.get("id"), "title": found.get("title", ""),
                         "start": start, "end": end, "duration": end - start,
                         "matched_text": scene["narration_text"], "relevance_score": 0.8}
            })
            print(f"    -> {found.get('title','')[:60]} ({dur}s)")
        else:
            scene_data.append({"scene": scene, "clip": None})
            print(f"    -> no clip found")

    print(f"\n[2/5] Downloading clips...")
    clip_paths = []
    for i, sd in enumerate(scene_data):
        clip_info = sd["clip"]
        if clip_info:
            clip_id = f"demo_s{i:03d}"
            start = clip_info["start"]
            end = clip_info["end"]
            try:
                v_path = clipper.download_video_segment(clip_info["url"], start, end, clip_id)
                a_path = clipper.download_audio_segment(clip_info["url"], start, end, f"{clip_id}_audio")
                clip_paths.append({"video": v_path, "audio": a_path, "narration": None, "music": None})
                print(f"  Scene {i+1}: {Path(v_path).name} ({Path(v_path).stat().st_size/1024:.0f}KB)")
            except Exception as e:
                print(f"  Scene {i+1}: download failed ({e})")
                clip_paths.append({"video": None, "audio": None, "narration": None, "music": None})
        else:
            clip_paths.append({"video": None, "audio": None, "narration": None, "music": None})
            print(f"  Scene {i+1}: skipped (no clip)")

    print(f"\n[3/5] Generating narration...")
    word_segments_list = []
    for i, sd in enumerate(scene_data):
        scene = sd["scene"]
        text = scene["narration_text"]
        narr_path = temp.create_temp_dir() / f"demo_narr_{i:03d}.mp3"
        await mixer.generate_narration(text, narr_path)
        clip_paths[i]["narration"] = narr_path
        dur = mixer.get_narration_duration(text)
        segments = estimate_word_timestamps(text, dur)
        word_segments_list.append(segments)
        print(f"  Scene {i+1}: '{text}' -> {Path(narr_path).name} ({dur:.1f}s)")

    print(f"\n[4/5] Assembling scenes...")
    transitions = []
    for i in range(len(DEMO_SCENES) - 1):
        transitions.append({"transition": DEMO_SCENES[i].get("transition_out", "crossfade")})
    final_clip = assembler.assemble(DEMO_SCENES, clip_paths, transitions, word_segments_list)

    print(f"\n[5/5] Rendering...")
    output = renderer.render_with_cleanup(final_clip, "YTTransformer_demo.mp4")

    print(f"\n{'=' * 60}")
    print(f"  DONE! Output: {output}")
    print(f"  Size: {Path(output).stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  Duration: {final_clip.duration:.1f}s")
    print(f"{'=' * 60}")
    return output


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_demo())
    except KeyboardInterrupt:
        print("\nCancelled.")
    finally:
        loop.close()
