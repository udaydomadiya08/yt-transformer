import os
from moviepy.editor import TextClip, CompositeVideoClip

FONT = "Arial-Bold"
KERNING_BUFFER = 40
SAFE_WIDTH_RATIO = 0.85
MAX_LINES = 2
FONTSIZE_LARGE = 85
FONTSIZE_SMALL = 45
COLOR_PASSIVE = "yellow"
COLOR_ACTIVE = "#00FF00"
STROKE_COLOR = "black"
STROKE_WIDTH = 3
STROKE_WIDTH_ACTIVE = 4
V_POS_RATIO = 0.75
LINE_SPACING = 15


def estimate_word_timestamps(text, total_duration):
    words = text.strip().split()
    if not words:
        return []
    total_chars = sum(len(w) for w in words)
    if total_chars == 0:
        chunk = total_duration / len(words)
        return [{"word": w, "start": i * chunk, "end": (i + 1) * chunk} for i, w in enumerate(words)]
    char_per_sec = total_chars / total_duration
    current = 0.0
    segments = []
    for w in words:
        word_dur = max(0.15, len(w) / char_per_sec)
        segments.append({"word": w, "start": current, "end": current + word_dur})
        current += word_dur
    if segments and current > 0:
        scale = total_duration / current
        for s in segments:
            s["start"] *= scale
            s["end"] *= scale
    return segments


def create_word_by_word_subtitles(word_segments, video_size, style=None):
    style = style or {}
    color_passive = style.get("color_passive", COLOR_PASSIVE)
    color_active = style.get("color_active", COLOR_ACTIVE)
    width, height = video_size
    is_vertical = width < height
    safe_width = int(width * SAFE_WIDTH_RATIO)
    if not is_vertical:
        safe_width = min(safe_width, 918)
    fontsize = FONTSIZE_LARGE if width > 1000 else FONTSIZE_SMALL
    fontsize_active = fontsize + 10
    font_path = style.get("font", FONT)
    v_pos_base = height * V_POS_RATIO
    kerning = KERNING_BUFFER

    word_data = []
    for seg in word_segments:
        clean = seg["word"]
        try:
            m = TextClip(clean, font=font_path, fontsize=fontsize, method="label")
            w, h = m.size
            m.close()
            ma = TextClip(clean, font=font_path, fontsize=fontsize_active, method="label")
            wa, ha = ma.size
            ma.close()
        except Exception:
            w, h = len(clean) * 14, fontsize
            wa, ha = len(clean) * 16, fontsize_active
        word_data.append({"seg": seg, "w": w, "h": h, "wa": wa, "ha": ha, "clean": clean})

    phrases = []
    idx = 0
    total = len(word_data)
    while idx < total:
        phrase_lines = []
        for _ in range(MAX_LINES):
            line_words = []
            line_w = 0
            while idx < total:
                wi = word_data[idx]
                if not line_words:
                    line_words.append(wi)
                    line_w = wi["w"]
                    idx += 1
                elif line_w + kerning + wi["w"] < safe_width:
                    line_words.append(wi)
                    line_w += kerning + wi["w"]
                    idx += 1
                else:
                    break
            if line_words:
                phrase_lines.append(line_words)
            if idx >= total:
                break
        if phrase_lines:
            p_start = phrase_lines[0][0]["seg"]["start"]
            p_end = phrase_lines[-1][-1]["seg"]["end"]
            phrases.append({"lines": phrase_lines, "start": p_start, "end": p_end})

    final_clips = []
    for phrase in phrases:
        p_start, p_end = phrase["start"], phrase["end"]
        y_offset = 0
        for line in phrase["lines"]:
            line_actual_w = sum(wd["w"] for wd in line) + (len(line) - 1) * kerning
            current_x = (width - line_actual_w) / 2
            for wd in line:
                seg = wd["seg"]
                clean = wd["clean"]
                w_start, w_end = seg["start"], seg["end"]
                x_pos = current_x
                y_pos = v_pos_base + y_offset
                pre_dur = w_start - p_start
                if pre_dur > 0.01:
                    pre = (TextClip(clean, font=font_path, fontsize=fontsize, color=color_passive,
                                    stroke_color=STROKE_COLOR, stroke_width=STROKE_WIDTH, method="label")
                           .set_start(p_start).set_duration(pre_dur).set_position((x_pos, y_pos)))
                    final_clips.append(pre)
                post_dur = p_end - w_end
                if post_dur > 0.01:
                    post = (TextClip(clean, font=font_path, fontsize=fontsize, color=color_passive,
                                     stroke_color=STROKE_COLOR, stroke_width=STROKE_WIDTH, method="label")
                            .set_start(w_end).set_duration(post_dur).set_position((x_pos, y_pos)))
                    final_clips.append(post)
                ax = x_pos + (wd["w"] - wd["wa"]) / 2
                ay = y_pos + (wd["h"] - wd["ha"]) / 2
                active = (TextClip(clean, font=font_path, fontsize=fontsize_active, color=color_active,
                                   stroke_color=STROKE_COLOR, stroke_width=STROKE_WIDTH_ACTIVE, method="label")
                          .set_start(w_start).set_duration(w_end - w_start).set_position((ax, ay)))
                final_clips.append(active)
                current_x += wd["w"] + kerning
            y_offset += wd["h"] + LINE_SPACING

    return final_clips


def overlay_subtitles(scene_clip, word_segments, video_size, style=None):
    if not word_segments:
        return scene_clip
    sub_clips = create_word_by_word_subtitles(word_segments, video_size, style)
    return CompositeVideoClip([scene_clip] + sub_clips, size=video_size)
