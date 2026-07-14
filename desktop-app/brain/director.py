import json

from google import genai

SCENE_TEMPLATE = """{
  "scene_number": 1,
  "purpose": "intro/explain/emphasize/transition/conclusion",
  "search_query": "search terms for finding matching clip",
  "narration_text": "AI narration text for this 3-4 second scene",
  "duration_sec": 4,
  "clip": {
    "enabled": true,
    "treatment": "normal|zoom_in|zoom_out|pan|crop_vertical|bw"
  },
  "original_audio": {
    "enabled": true,
    "volume": 0.5
  },
  "narration": {
    "enabled": true,
    "volume": 0.9
  },
  "music_bg": {
    "enabled": false,
    "volume": 0.0
  },
  "subtitles": {
    "enabled": true,
    "style": "word_highlight",
    "color_active": "#00FF00",
    "color_passive": "#FFFF00",
    "fontsize": 50
  },
  "transition_out": "cut|crossfade|fade_black|slide_left|slide_right|zoom_in",
  "visual_fallback_if_no_clip": "search_other_video"
}"""

DURATION_LIMITS = {
    "vertical": {"max_sec": 58, "scene_range": "8-15 scenes", "total_range": "25-58 seconds"},
    "horizontal": {"max_sec": 120, "scene_range": "8-25 scenes", "total_range": "30-120 seconds"},
    "square": {"max_sec": 88, "scene_range": "8-20 scenes", "total_range": "25-88 seconds"},
}

def build_director_prompt(orientation="horizontal"):
    limits = DURATION_LIMITS.get(orientation, DURATION_LIMITS["horizontal"])
    return f"""You are a video director AI. Given a user's topic or description, create a complete video script.

Each scene is 3-4 seconds. The scenes will be assembled from existing YouTube video clips (exact timestamp matches) synchronized to narration text.

Format: {"VERTICAL (9:16)" if orientation == "vertical" else "SQUARE (1:1)" if orientation == "square" else "HORIZONTAL (16:9)"}

Rules:
- Every scene MUST have a unique video clip - never reuse same video segment
- Narration text must be concise (2-7 seconds when spoken)
- Search queries must be specific enough to find matching YouTube content
- Vary treatments across scenes to keep visual interest
- Audio volumes are 0.0 to 1.0 (narration is usually 0.7-1.0, original audio 0.0-0.5, music 0.1-0.3)
- If original audio is muted (volume 0), narration should compensate
- NEVER leave a scene without some audio source
- TOTAL VIDEO DURATION MUST NOT EXCEED {limits['max_sec']} SECONDS

Return ONLY valid JSON array of scenes, nothing else.
Each scene object follows this exact schema:
{SCENE_TEMPLATE}

Generate {limits['scene_range']} depending on the topic complexity. Make the total video {limits['total_range']}."""

RELEVANCE_PROMPT = """You are a clip relevance judge. Given a narration text and a candidate YouTube clip, determine if the clip content exactly matches the narration topic.

Narration: "%s"
Clip title: "%s"
Clip matched text from transcript: "%s"

Answer with ONLY valid JSON:
{"relevant": true/false, "confidence": 0.0-1.0, "reason": "brief justification"}"""

REFINE_PROMPT_TMPL = """You are a video director refining the script. Given the user's raw idea, produce a polished, engaging script with proper narrative flow.

User idea: "%%s"

Generate a complete video plan. Each scene is 3-4 seconds. Return ONLY valid JSON array of scenes. Use this schema per scene:
%s

Make it compelling, well-paced, and optimized for short-form video (TikTok/Shorts/Reels style).""" % SCENE_TEMPLATE

TRANSITION_PROMPT = """You are a video editor. Given the sequence of scenes below, suggest the best transition between each consecutive pair.

Scene sequence:
%s

For each gap between scene N and scene N+1, pick one transition:
cut, crossfade, fade_black, slide_left, slide_right, zoom_in

Return ONLY valid JSON array: [{"from_scene": 1, "to_scene": 2, "transition": "crossfade"}, ...]"""


class Director:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self._model = "gemini-2.0-flash"

    def generate_script(self, user_input, orientation="horizontal"):
        base = build_director_prompt(orientation)
        limits = DURATION_LIMITS.get(orientation, DURATION_LIMITS["horizontal"])
        if len(user_input) <= 50:
            prompt = f"""{base}

User idea: "{user_input}"

Refine this into a complete video plan. Total must be under {limits['max_sec']} seconds. Return ONLY valid JSON."""
        else:
            prompt = f"""{base}

User's topic/description: {user_input}

Generate the full video plan now. Total must be under {limits['max_sec']} seconds."""
        try:
            response = self.client.models.generate_content(
                model=self._model,
                contents=prompt,
            )
            scenes = self._parse_json(response.text)
            return scenes
        except Exception as e:
            raise RuntimeError(f"Gemini script generation failed: {e}")

    def check_relevance(self, narration_text, candidate):
        clip_title = candidate.get("title", "")
        matched_text = candidate.get("matched_text", "")
        prompt = RELEVANCE_PROMPT % (narration_text, clip_title, matched_text)
        try:
            response = self.client.models.generate_content(
                model=self._model,
                contents=prompt,
            )
            result = self._parse_json(response.text)
            if isinstance(result, dict):
                return result.get("relevant", False), result.get("confidence", 0)
            return False, 0
        except Exception:
            return False, 0

    def batch_check_relevance(self, checks):
        prompt_parts = []
        for i, (narration, candidate) in enumerate(checks):
            prompt_parts.append(f"""[Scene {i+1}]
Narration: "{narration}"
Clip title: "{candidate.get('title', '')}"
Matched transcript: "{candidate.get('matched_text', '')}"
""")
        full_prompt = f"""You are a clip relevance judge. For each scene below, determine if the clip content matches the narration topic.

{chr(10).join(prompt_parts)}

Return ONLY a valid JSON array of objects:
[{{"scene": 1, "relevant": true, "confidence": 0.9}}, ...]"""
        try:
            response = self.client.models.generate_content(
                model=self._model,
                contents=full_prompt,
            )
            results = self._parse_json(response.text)
            if isinstance(results, list):
                return [(r.get("relevant", False), r.get("confidence", 0)) for r in results]
            return [(False, 0)] * len(checks)
        except Exception:
            return [(False, 0)] * len(checks)

    def suggest_transitions(self, scenes):
        sequence = "\n".join(
            f"Scene {s.get('scene_number', i+1)}: {s.get('narration_text', '')[:80]}"
            for i, s in enumerate(scenes)
        )
        prompt = TRANSITION_PROMPT % sequence
        try:
            response = self.client.models.generate_content(
                model=self._model,
                contents=prompt,
            )
            return self._parse_json(response.text)
        except Exception:
            return [{"transition": "crossfade"} for _ in range(len(scenes)-1)]

    def _parse_json(self, text):
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        return json.loads(cleaned)
