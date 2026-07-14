import asyncio
import edge_tts
from pathlib import Path

class AudioMixer:
    def __init__(self):
        self._tts_voice = "en-US-GuyNeural"

    async def generate_narration(self, text, output_path, voice=None):
        voice = voice or self._tts_voice
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        return Path(output_path)

    def get_narration_duration(self, text):
        words = len(text.split())
        return max(2.0, words * 0.3)

    def get_volume_config(self, scene_config):
        vol = scene_config.get("volume_ratios", {})
        if not vol:
            return {
                "original": scene_config.get("original_audio", {}).get("volume", 0.5),
                "narration": scene_config.get("narration", {}).get("volume", 0.9),
                "music": scene_config.get("music_bg", {}).get("volume", 0.0),
            }
        return vol

    def determine_final_audio_mode(self, scene_config):
        orig = scene_config.get("original_audio", {})
        narration = scene_config.get("narration", {})
        music = scene_config.get("music_bg", {})

        has_orig = orig.get("enabled", False) and orig.get("volume", 0) > 0
        has_narr = narration.get("enabled", False) and narration.get("volume", 0) > 0
        has_music = music.get("enabled", False) and music.get("volume", 0) > 0

        if has_narr and has_orig:
            return "narration_over_original"
        elif has_narr and not has_orig:
            return "narration_only"
        elif has_orig and not has_narr:
            return "original_only"
        elif has_narr and has_orig and has_music:
            return "narration_over_original_with_music"
        elif has_narr and has_music:
            return "narration_with_music"
        elif has_orig and has_music:
            return "original_with_music"
        else:
            return "narration_only"
