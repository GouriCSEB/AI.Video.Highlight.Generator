"""
highlight_generator.py
======================
Produces browser-playable H.264/AAC MP4 highlight videos WITH audio
by using ffmpeg via subprocess (much more reliable than OpenCV's mp4v codec).

Requirements: ffmpeg must be installed on the system.
  Windows: https://www.gyan.dev/ffmpeg/builds/  (add to PATH)
  Mac:     brew install ffmpeg
  Linux:   sudo apt install ffmpeg
"""

import subprocess
import shutil
import os
import tempfile
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple


# ─────────────────────────── segment selection ────────────────────────────

def select_highlight_segments(
        timestamps:      List[float],
        scores:          List[float],
        top_fraction:    float = 0.30,
        min_gap_sec:     float = 10.0,   # frames within 10s of each other merge together
        segment_pad_sec: float = 3.0,    # 3s of context added before/after each segment
        min_segment_dur: float = 5.0,    # drop segments shorter than 5 seconds
        max_segments:    int   = 15      # keep only top 15 segments
) -> List[Tuple[float, float]]:
    """
    Select the most important continuous segments from scored frames.

    Key parameters
    --------------
    min_gap_sec    : frames closer than this are merged into one segment (15s default)
    segment_pad_sec: seconds of context added before/after each segment
    min_segment_dur: discard segments shorter than this (removes 2-second fragments)
    max_segments   : keep only the top N segments by average score
    """
    if not timestamps:
        return []

    arr = np.array(scores)

    # Use a higher threshold so only genuinely high-scoring frames are selected
    threshold = np.percentile(arr, max(50, (1 - top_fraction) * 100))
    important_times = [t for t, s in zip(timestamps, scores) if s >= threshold]

    if not important_times:
        return []

    important_times.sort()

    # Merge nearby frames into segments
    segments: List[Tuple[float, float]] = []
    seg_start = important_times[0]
    seg_end   = important_times[0]

    for t in important_times[1:]:
        if t - seg_end <= min_gap_sec:
            seg_end = t
        else:
            segments.append((seg_start, seg_end))
            seg_start = t
            seg_end   = t
    segments.append((seg_start, seg_end))

    # Pad each segment
    padded = []
    for s, e in segments:
        padded.append((max(0.0, s - segment_pad_sec), e + segment_pad_sec))

    # Merge overlapping padded segments
    merged: List[List[float]] = []
    for s, e in sorted(padded):
        if merged and s <= merged[-1][1]:
            merged[-1] = [merged[-1][0], max(merged[-1][1], e)]
        else:
            merged.append([s, e])

    # Drop segments that are too short (removes tiny fragments)
    # If ALL segments are short, keep them anyway rather than returning empty
    long_segs = [seg for seg in merged if (seg[1] - seg[0]) >= min_segment_dur]
    merged = long_segs if long_segs else merged  # fallback: keep all if none pass

    # Rank by average score and keep only top max_segments
    def avg_score(seg):
        s, e = seg
        vals = [sc for t, sc in zip(timestamps, scores) if s <= t <= e]
        return float(np.mean(vals)) if vals else 0.0

    ranked = sorted(merged, key=avg_score, reverse=True)[:max_segments]
    # Return in chronological order
    return [(float(s), float(e)) for s, e in sorted(ranked)]


# ─────────────────────────── ffmpeg helpers ───────────────────────────────

def _ffmpeg_path() -> str:
    # 0. Allow explicit override via environment variable
    env_path = os.environ.get("FFMPEG_PATH", "")
    if env_path and os.path.isfile(env_path):
        return env_path

    # 1. Check system PATH
    path = shutil.which("ffmpeg")
    if path:
        return path

    # 2. Search common Windows install locations automatically
    import glob
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ]
    candidates += glob.glob(r"C:\ffmpeg\*\bin\ffmpeg.exe")
    home = os.path.expanduser("~")
    candidates += glob.glob(os.path.join(home, "**", "ffmpeg.exe"), recursive=True)

    for c in candidates:
        if os.path.isfile(c):
            return c

    raise RuntimeError(
        "ffmpeg not found. Set the FFMPEG_PATH environment variable to the "
        "full path of ffmpeg.exe and restart the app.\n"
        "Example:  set FFMPEG_PATH=C:\\ffmpeg\\ffmpeg-8.0.1-essentials_build\\bin\\ffmpeg.exe"
    )


def _cut_segment(ffmpeg: str, source: str, start: float, end: float, out_path: str) -> bool:
    duration = end - start
    if duration <= 0:
        return False

    cmd = [
        ffmpeg, "-y",
        "-ss", str(start),
        "-i", str(source),
        "-t",  str(duration),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "128k",
        "-preset", "ultrafast",
        "-movflags", "+faststart",
        "-avoid_negative_ts", "make_zero",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result.returncode == 0


def _concat_segments(ffmpeg: str, segment_files: List[str], output_path: str) -> bool:
    list_path = output_path + ".txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for seg in segment_files:
            safe = seg.replace("\\", "/")
            f.write(f"file '{safe}'\n")

    cmd = [
        ffmpeg, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "128k",
        "-preset", "ultrafast",
        "-movflags", "+faststart",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    try:
        os.remove(list_path)
    except Exception:
        pass
    return result.returncode == 0


# ─────────────────────────── main generator ───────────────────────────────

def generate_highlight_video(
        source_path:   str,
        output_path:   str,
        segments:      List[Tuple[float, float]],
        max_duration:  float = 120.0,
        target_height: int   = 480
) -> Dict:
    ff = _ffmpeg_path()

    # Clamp to max_duration
    clamped: List[Tuple[float, float]] = []
    total = 0.0
    for s, e in segments:
        if total >= max_duration:
            break
        available = max_duration - total
        end = min(e, s + available)
        if end > s:
            clamped.append((s, end))
            total += end - s

    if not clamped:
        # Give a detailed error to help diagnose
        seg_info = ", ".join(f"({s:.1f}s-{e:.1f}s dur={e-s:.1f}s)" for s, e in segments[:5])
        raise ValueError(
            f"No valid segments to process. "
            f"max_duration={max_duration}s, "
            f"segments received: {seg_info if segments else 'NONE'}"
        )

    tmp_dir = tempfile.mkdtemp(prefix="hilight_")
    segment_files: List[str] = []

    try:
        for i, (start, end) in enumerate(clamped):
            seg_path = os.path.join(tmp_dir, f"seg_{i:04d}.mp4")
            success = _cut_segment(ff, source_path, start, end, seg_path)
            if success and os.path.exists(seg_path) and os.path.getsize(seg_path) > 0:
                segment_files.append(seg_path)

        if not segment_files:
            raise RuntimeError("ffmpeg failed to cut any segments.")

        if len(segment_files) == 1:
            import shutil as _sh
            _sh.move(segment_files[0], output_path)
        else:
            success = _concat_segments(ff, segment_files, output_path)
            if not success:
                raise RuntimeError("ffmpeg concat step failed.")

    finally:
        import shutil as _sh
        _sh.rmtree(tmp_dir, ignore_errors=True)

    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    highlight_duration = sum(e - s for s, e in clamped)

    return {
        "output_path":        str(output_path),
        "highlight_duration": round(highlight_duration, 2),
        "segments_count":     len(clamped),
        "total_frames":       int(highlight_duration * 25),
        "resolution":         f"auto×{target_height}",
        "file_size_mb":       round(file_size / 1024 / 1024, 2)
    }


# ─────────────────────────── timeline builder ─────────────────────────────

def build_timeline(timestamps, scores, segments, video_duration):
    timeline = []
    for t, s in zip(timestamps, scores):
        seg_id = None
        for i, (start, end) in enumerate(segments):
            if start <= t <= end:
                seg_id = i
                break
        timeline.append({
            "time":         round(t, 2),
            "score":        round(float(s), 4),
            "is_highlight": seg_id is not None,
            "segment_id":   seg_id
        })
    return timeline
