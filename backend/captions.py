from pathlib import Path
from typing import List, Dict, Any

# Style definitions dictionary - easily extendable with new subtitle styles
CAPTION_STYLES: Dict[str, Dict[str, Any]] = {
    "bold_pop": {
        "name": "Bold Pop",
        "description": "2-3 words, huge bold uppercase, active word in yellow with a pop-in scale effect",
        "font_name": "Montserrat ExtraBold",
        "fallback_font": "Arial, DejaVu Sans, sans-serif",
        "font_size": 76,
        "primary_color": "&H00FFFFFF",   # White (&HAABBGGRR)
        "active_color": "&H0000FFFF",    # Vibrant Yellow (&HAABBGGRR)
        "outline_color": "&H00000000",   # Black
        "back_color": "&H80000000",
        "bold": -1,                      # -1 is True in ASS
        "outline": 8,
        "shadow": 3,
        "alignment": 2,                  # Bottom-Center
        "margin_v": 520,                 # Lower-middle of vertical frame
        "words_per_group": 3,
        "uppercase": True,
        "animation": "pop",
    },
    "karaoke": {
        "name": "Karaoke",
        "description": "Full line shown with active spoken word highlighted in vibrant blue",
        "font_name": "Montserrat ExtraBold",
        "fallback_font": "Arial, DejaVu Sans, sans-serif",
        "font_size": 60,
        "primary_color": "&H00FFFFFF",   # White
        "active_color": "&H00F59E0B",    # Vibrant Blue (BGR: 0B 9E F5 -> Sky/Blue)
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
        "bold": -1,
        "outline": 6,
        "shadow": 2,
        "alignment": 2,
        "margin_v": 460,
        "words_per_group": 6,
        "uppercase": False,
        "animation": "karaoke",
    },
    "clean": {
        "name": "Clean",
        "description": "Small, elegant white subtitles at bottom of frame with no animation",
        "font_name": "Montserrat ExtraBold",
        "fallback_font": "Arial, DejaVu Sans, sans-serif",
        "font_size": 42,
        "primary_color": "&H00FFFFFF",
        "active_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
        "bold": 0,
        "outline": 3,
        "shadow": 1,
        "alignment": 2,
        "margin_v": 140,                 # Bottom of frame
        "words_per_group": 8,
        "uppercase": False,
        "animation": "none",
    },
}


def format_ass_timestamp(seconds: float) -> str:
    """Format float seconds to ASS timestamp format: H:MM:SS.cs"""
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def build_ass_header(style_config: Dict[str, Any], res_x: int, res_y: int) -> str:
    """Generate ASS file script header and V4+ Styles section."""
    # Scale vertical margin proportionally for different aspect ratios
    margin_v = int(style_config["margin_v"] * (res_y / 1920.0))
    font_size = int(style_config["font_size"] * (res_y / 1920.0))

    header = f"""[Script Info]
Title: ClipSnap Dynamic Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {res_x}
PlayResY: {res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style_config['font_name']},{font_size},{style_config['primary_color']},{style_config['primary_color']},{style_config['outline_color']},{style_config['back_color']},{style_config['bold']},0,0,0,100,100,0,0,1,{style_config['outline']},{style_config['shadow']},{style_config['alignment']},30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header


def generate_ass_subtitles(
    all_words: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    style_name: str,
    output_ass_path: Path,
    res_x: int = 1080,
    res_y: int = 1920,
) -> bool:
    """
    Filter transcript words inside clip range [clip_start, clip_end],
    shift timestamps so clip starts at 0, and generate an ASS file.
    Returns True if subtitles were written, False if no words were found.
    """
    style_key = style_name.lower().strip()
    if style_key not in CAPTION_STYLES:
        style_key = "bold_pop"

    style = CAPTION_STYLES[style_key]
    clip_duration = max(0.5, clip_end - clip_start)

    # 1. Filter and shift words so clip starts at 0
    shifted_words: List[Dict[str, Any]] = []
    for w in all_words:
        w_start = float(w.get("start", 0.0))
        w_end = float(w.get("end", 0.0))

        # Check overlap with clip window
        if w_end > clip_start and w_start < clip_end:
            shifted_start = max(0.0, w_start - clip_start)
            shifted_end = min(clip_duration, w_end - clip_start)
            word_text = str(w.get("word", "")).strip()

            if style["uppercase"]:
                word_text = word_text.upper()

            if word_text and shifted_end > shifted_start:
                shifted_words.append({
                    "word": word_text,
                    "start": shifted_start,
                    "end": shifted_end
                })

    if not shifted_words:
        return False

    # 2. Group words into lines/phrases based on style
    group_size = style["words_per_group"]
    groups: List[List[Dict[str, Any]]] = []
    for i in range(0, len(shifted_words), group_size):
        groups.append(shifted_words[i:i + group_size])

    dialogue_events: List[str] = []

    # 3. Build dialogue events for each group
    for group in groups:
        group_start = group[0]["start"]
        group_end = group[-1]["end"]

        if style["animation"] == "pop":
            # "bold_pop": 2-3 words at a time. Each word in the group pops with scale & yellow
            for idx, active_word in enumerate(group):
                w_start_str = format_ass_timestamp(active_word["start"])
                w_end_str = format_ass_timestamp(active_word["end"])

                parts = []
                for j, w in enumerate(group):
                    if j == idx:
                        # Pop animation: scale up to 114% then settle to 100%, color yellow
                        pop_tag = r"{\c" + style["active_color"] + r"\t(0,70,\fscx114\fscy114)\t(70,140,\fscx100\fscy100)}"
                        parts.append(f"{pop_tag}{w['word']}{{\\c{style['primary_color']}}}")
                    else:
                        parts.append(w["word"])

                line_text = " ".join(parts)
                dialogue_events.append(
                    f"Dialogue: 0,{w_start_str},{w_end_str},Default,,0,0,0,,{line_text}"
                )

        elif style["animation"] == "karaoke":
            # "karaoke": Full line shown, active word highlighted in vibrant blue
            for idx, active_word in enumerate(group):
                w_start_str = format_ass_timestamp(active_word["start"])
                w_end_str = format_ass_timestamp(active_word["end"])

                parts = []
                for j, w in enumerate(group):
                    if j == idx:
                        # Blue highlight on active word
                        parts.append(f"{{\\c{style['active_color']}}}{w['word']}{{\\c{style['primary_color']}}}")
                    else:
                        parts.append(w["word"])

                line_text = " ".join(parts)
                dialogue_events.append(
                    f"Dialogue: 0,{w_start_str},{w_end_str},Default,,0,0,0,,{line_text}"
                )

        else:
            # "clean": static line with no animation
            g_start_str = format_ass_timestamp(group_start)
            g_end_str = format_ass_timestamp(group_end)
            line_text = " ".join(w["word"] for w in group)
            dialogue_events.append(
                f"Dialogue: 0,{g_start_str},{g_end_str},Default,,0,0,0,,{line_text}"
            )

    header = build_ass_header(style, res_x, res_y)
    full_content = header + "\n".join(dialogue_events) + "\n"

    output_ass_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    return True
