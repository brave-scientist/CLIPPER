import re
import subprocess
from pathlib import Path
from typing import List, Tuple

def compute_loudness_per_second(video_path: Path) -> List[Tuple[float, float]]:
    """Uses FFmpeg ebur128 filter to estimate momentary loudness per second."""
    cmd = [
        "ffmpeg", "-nostats", "-i", str(video_path),
        "-filter_complex", "ebur128=peak=none", "-f", "null", "-"
    ]
    try:
        proc = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, timeout=25)
        levels: List[Tuple[float, float]] = []
        for line in proc.stderr.splitlines():
            # Matches: t: 1.2 M: -21.4
            m = re.search(r"t:\s*([\d\.]+)\s+M:\s*(-?[\d\.]+)", line)
            if m:
                levels.append((float(m.group(1)), float(m.group(2))))
        return levels
    except Exception:
        return []

def apply_audio_excitement_bonus(clips: list, levels: list, words: list) -> list:
    """Give up to +10 score bonus if volume and speech speed rise during clip."""
    if not levels:
        return clips
    avg_loudness = sum(lvl for _, lvl in levels) / max(1, len(levels))
    for c in clips:
        clip_levels = [lvl for t, lvl in levels if c.start <= t <= c.end]
        if not clip_levels:
            continue
        clip_avg = sum(clip_levels) / len(clip_levels)
        loudness_rise = clip_avg - avg_loudness  # In LUFS: higher = louder
        
        # Calculate speech rate (words per second)
        clip_words = [w for w in words if c.start <= w.get('start', 0) <= c.end]
        dur = max(1.0, c.end - c.start)
        wps = len(clip_words) / dur
        
        bonus = 0
        if loudness_rise > 2.0:
            bonus += min(6, int(loudness_rise * 1.5))
        if wps > 2.8:
            bonus += 4
        bonus = min(10, max(0, bonus))
        
        if bonus > 0:
            c.scores.hook = min(100, c.scores.hook + bonus)
            c.scores.total = min(100, round(c.scores.hook * 0.5 + c.scores.pacing * 0.3 + c.scores.trend * 0.2))
            c.reason = f"{c.reason} [Excitement bonus +{bonus} pts: speaker volume and speed rise]"
    return clips
