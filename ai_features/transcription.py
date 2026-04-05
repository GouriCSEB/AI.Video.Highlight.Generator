"""
ai_features/transcription.py
=============================
Speech-to-text using OpenAI Whisper (runs fully locally, no API key needed).
Also provides keyword-based score boosting.

Install:  pip install openai-whisper
          pip install torch  (CPU version is fine)
"""

import os
import json
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np


# ─────────────────────────── audio extraction ────────────────────────────

def extract_audio(video_path: str, output_dir: str) -> str:
    """Extract audio track from video to a WAV file using ffmpeg."""
    ffmpeg = shutil.which("ffmpeg") or _find_ffmpeg()
    audio_path = os.path.join(output_dir, "audio.wav")
    cmd = [
        ffmpeg, "-y", "-i", str(video_path),
        "-vn",                    # no video
        "-acodec", "pcm_s16le",   # raw PCM – best for Whisper
        "-ar", "16000",           # 16kHz sample rate
        "-ac", "1",               # mono
        str(audio_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not os.path.exists(audio_path):
        raise RuntimeError(f"Audio extraction failed: {result.stderr[-300:]}")
    return audio_path


def _find_ffmpeg() -> str:
    import glob
    candidates = glob.glob(r"C:\ffmpeg\*\bin\ffmpeg.exe")
    candidates += glob.glob(os.path.join(os.path.expanduser("~"), "**", "ffmpeg.exe"), recursive=True)
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise RuntimeError("ffmpeg not found. Add it to PATH.")


# ─────────────────────────── whisper transcription ───────────────────────

def transcribe_video(video_path: str, model_size: str = "base") -> Dict:
    """
    Transcribe video audio using OpenAI Whisper (local, offline).

    Parameters
    ----------
    video_path : path to the source video
    model_size : "tiny" | "base" | "small" | "medium"
                 tiny  = fastest,  lowest accuracy  (~75MB)
                 base  = good balance               (~145MB)
                 small = better accuracy            (~465MB)

    Returns
    -------
    {
      "text":     full transcript string,
      "segments": [{"start", "end", "text"}, ...]  – word-level timestamps
      "language": detected language code
    }
    """
    try:
        import whisper
    except ImportError:
        return {
            "text": "",
            "segments": [],
            "language": "unknown",
            "error": "openai-whisper not installed. Run: pip install openai-whisper"
        }

    tmp_dir = tempfile.mkdtemp(prefix="whisper_")
    try:
        audio_path = extract_audio(str(video_path), tmp_dir)
        model      = whisper.load_model(model_size)
        result     = model.transcribe(
            audio_path,
            word_timestamps=False,
            verbose=False
        )
        segments = [
            {
                "start": round(seg["start"], 2),
                "end":   round(seg["end"],   2),
                "text":  seg["text"].strip()
            }
            for seg in result.get("segments", [])
        ]
        return {
            "text":     result.get("text", "").strip(),
            "segments": segments,
            "language": result.get("language", "unknown"),
            "error":    None
        }
    except Exception as e:
        return {"text": "", "segments": [], "language": "unknown", "error": str(e)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ─────────────────────────── keyword score boost ─────────────────────────

# Default important keywords for lecture / webinar content
DEFAULT_KEYWORDS = [
    "important", "key point", "remember", "note that", "critical",
    "main idea", "conclusion", "summary", "definition", "formula",
    "theorem", "example", "result", "finding", "in summary",
    "to summarise", "let me show", "pay attention", "don't forget",
    "highlight", "significant", "essential", "fundamental"
]


def boost_scores_with_keywords(
        timestamps:    List[float],
        scores:        List[float],
        transcript_segs: List[Dict],
        user_keywords: List[str] = None,
        boost_amount:  float = 0.25
) -> Tuple[List[float], List[Dict]]:
    """
    Boost importance scores for frames that coincide with
    keyword-containing transcript segments.

    Parameters
    ----------
    timestamps       : per-frame timestamps (seconds)
    scores           : per-frame ML importance scores [0..1]
    transcript_segs  : Whisper segment dicts {start, end, text}
    user_keywords    : extra keywords from the user
    boost_amount     : how much to add to the score (0–1)

    Returns
    -------
    boosted_scores : updated score list
    keyword_hits   : [{time, keyword, text}, ...] for UI display
    """
    all_keywords = list(DEFAULT_KEYWORDS)
    if user_keywords:
        all_keywords += [k.lower().strip() for k in user_keywords if k.strip()]

    boosted   = list(scores)
    hits      = []
    ts_array  = np.array(timestamps)

    for seg in transcript_segs:
        seg_text  = seg["text"].lower()
        matched_kw = next((kw for kw in all_keywords if kw in seg_text), None)
        if matched_kw is None:
            continue

        # Find all frames within this transcript segment
        mask = (ts_array >= seg["start"]) & (ts_array <= seg["end"])
        indices = np.where(mask)[0]
        for idx in indices:
            boosted[idx] = min(1.0, boosted[idx] + boost_amount)

        hits.append({
            "time":    round(seg["start"], 2),
            "keyword": matched_kw,
            "text":    seg["text"].strip()
        })

    return boosted, hits


# ─────────────────────────── transcript formatter ─────────────────────────

def format_transcript_for_report(transcript: Dict, max_chars: int = 3000) -> str:
    """Return a clean, readable transcript string truncated to max_chars."""
    if not transcript.get("text"):
        return "No transcript available."
    text = transcript["text"]
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text


def get_transcript_by_segment(
        transcript_segs: List[Dict],
        seg_start: float,
        seg_end:   float
) -> str:
    """Return joined transcript text that overlaps with a highlight segment."""
    lines = [
        s["text"] for s in transcript_segs
        if s["start"] < seg_end and s["end"] > seg_start
    ]
    return " ".join(lines).strip() or "—"
