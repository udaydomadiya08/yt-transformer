import json


DEMO_SCENES = [
    {
        "scene_number": 1,
        "purpose": "intro",
        "search_query": "quantum computer explained animation",
        "narration_text": "Ever wondered what quantum computing actually means?",
        "duration_sec": 3,
        "clip": {"enabled": True, "treatment": "normal"},
        "original_audio": {"enabled": True, "volume": 0.3},
        "narration": {"enabled": True, "volume": 0.9},
        "music_bg": {"enabled": False, "volume": 0.0},
        "subtitles": {"enabled": True, "style": "word_highlight", "color_active": "#00FF00", "color_passive": "#FFFF00", "fontsize": 50},
        "transition_out": "crossfade",
    },
    {
        "scene_number": 2,
        "purpose": "explain",
        "search_query": "qubits explained visually",
        "narration_text": "Regular computers use bits, zeros and ones.",
        "duration_sec": 3,
        "clip": {"enabled": True, "treatment": "zoom_in"},
        "original_audio": {"enabled": True, "volume": 0.3},
        "narration": {"enabled": True, "volume": 0.9},
        "music_bg": {"enabled": False, "volume": 0.0},
        "subtitles": {"enabled": True, "style": "word_highlight", "color_active": "#00FF00", "color_passive": "#FFFF00", "fontsize": 50},
        "transition_out": "crossfade",
    },
    {
        "scene_number": 3,
        "purpose": "explain",
        "search_query": "superposition quantum mechanics",
        "narration_text": "But quantum computers use qubits that can be both at once.",
        "duration_sec": 3,
        "clip": {"enabled": True, "treatment": "zoom_out"},
        "original_audio": {"enabled": True, "volume": 0.3},
        "narration": {"enabled": True, "volume": 0.9},
        "music_bg": {"enabled": False, "volume": 0.0},
        "subtitles": {"enabled": True, "style": "word_highlight", "color_active": "#00FF00", "color_passive": "#FFFF00", "fontsize": 50},
        "transition_out": "crossfade",
    },
    {
        "scene_number": 4,
        "purpose": "explain",
        "search_query": "quantum entanglement explained",
        "narration_text": "This lets them solve certain problems millions of times faster.",
        "duration_sec": 4,
        "clip": {"enabled": True, "treatment": "normal"},
        "original_audio": {"enabled": True, "volume": 0.3},
        "narration": {"enabled": True, "volume": 0.9},
        "music_bg": {"enabled": False, "volume": 0.0},
        "subtitles": {"enabled": True, "style": "word_highlight", "color_active": "#00FF00", "color_passive": "#FFFF00", "fontsize": 50},
        "transition_out": "fade_black",
    },
    {
        "scene_number": 5,
        "purpose": "conclusion",
        "search_query": "future of quantum computing",
        "narration_text": "And that is quantum computing in a nutshell.",
        "duration_sec": 3,
        "clip": {"enabled": True, "treatment": "normal"},
        "original_audio": {"enabled": True, "volume": 0.3},
        "narration": {"enabled": True, "volume": 0.9},
        "music_bg": {"enabled": False, "volume": 0.0},
        "subtitles": {"enabled": True, "style": "word_highlight", "color_active": "#00FF00", "color_passive": "#FFFF00", "fontsize": 50},
        "transition_out": "fade_black",
    },
]


class DemoDirector:
    """Drop-in replacement for Director that uses hardcoded scenes (no API calls)."""

    def __init__(self, api_key=None):
        pass

    def generate_script(self, user_input, orientation="horizontal"):
        import copy
        scenes = copy.deepcopy(DEMO_SCENES)
        for s in scenes:
            s.setdefault("search_query", s.get("search_query", ""))
        return scenes

    def suggest_transitions(self, scenes):
        result = []
        for i in range(len(scenes) - 1):
            result.append({
                "from_scene": scenes[i].get("scene_number", i + 1),
                "to_scene": scenes[i + 1].get("scene_number", i + 2),
                "transition": scenes[i].get("transition_out", "crossfade"),
            })
        return result

    def check_relevance(self, narration_text, candidate):
        return True, 0.8

    def batch_check_relevance(self, checks):
        return [(True, 0.8)] * len(checks)
