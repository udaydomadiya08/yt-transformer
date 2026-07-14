class Matcher:
    def __init__(self, director):
        self.director = director
        self._used_clips = set()

    def select_best_clip(self, candidates, narration_text):
        if not candidates:
            return None
        checks = [(narration_text, c) for c in candidates]
        results = self.director.batch_check_relevance(checks)
        scored = []
        for i, (relevant, confidence) in enumerate(results):
            if relevant and confidence > 0.3:
                candidate = candidates[i]
                clip_key = candidate.get("_clip_key", "")
                if clip_key not in self._used_clips:
                    scored.append((confidence, candidate))
        if not scored:
            return None
        scored.sort(key=lambda x: -x[0])
        best = scored[0][1]
        self._used_clips.add(best.get("_clip_key", ""))
        return best

    def mark_clip_used(self, clip):
        key = clip.get("_clip_key", "")
        if key:
            self._used_clips.add(key)

    def is_clip_used(self, clip):
        return clip.get("_clip_key", "") in self._used_clips

    def reset(self):
        self._used_clips.clear()
