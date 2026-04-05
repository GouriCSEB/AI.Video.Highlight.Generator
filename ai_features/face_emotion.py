"""
ai_features/face_emotion.py
============================
Face detection using OpenCV Haar cascades (no extra installs needed).
Emotion detection using DeepFace (optional – gracefully skipped if not installed).

Install emotion detection (optional):
    pip install deepface tf-keras

Face detection works out-of-the-box with OpenCV.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import base64


# ─────────────────────────── face detector ───────────────────────────────

def _get_face_cascade():
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    return cv2.CascadeClassifier(cascade_path)


def detect_faces_in_frame(frame_bgr: np.ndarray) -> List[Dict]:
    """
    Detect faces in a single BGR frame.
    Returns list of {x, y, w, h, confidence} dicts.
    """
    cascade = _get_face_cascade()
    gray    = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    faces   = cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30),
        flags=cv2.CASCADE_SCALE_IMAGE
    )
    result = []
    if len(faces):
        for (x, y, w, h) in faces:
            result.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
    return result


# ─────────────────────────── per-video face analysis ─────────────────────

def analyze_faces_in_video(
        video_path: str,
        sample_fps: float = 0.5,
        max_frames: int   = 120
) -> List[Dict]:
    """
    Sample frames from the video and detect faces in each.

    Returns list of {timestamp, face_count, has_face, faces[]} dicts.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step         = max(1, int(video_fps / sample_fps))
    frame_indices = list(range(0, total_frames, step))[:max_frames]

    results = []
    for fidx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
        ret, frame = cap.read()
        if not ret:
            continue
        small  = cv2.resize(frame, (320, 180))
        faces  = detect_faces_in_frame(small)
        timestamp = round(fidx / video_fps, 2)
        results.append({
            "timestamp":  timestamp,
            "face_count": len(faces),
            "has_face":   len(faces) > 0,
            "faces":      faces
        })

    cap.release()
    return results


# ─────────────────────────── emotion detection ───────────────────────────

def detect_emotions_in_frame(frame_bgr: np.ndarray) -> List[Dict]:
    """
    Detect emotions using DeepFace (optional).
    Returns list of {dominant_emotion, scores{}, region{}} per face.
    Falls back to empty list if DeepFace is not installed.
    """
    try:
        from deepface import DeepFace
        results = DeepFace.analyze(
            frame_bgr,
            actions=["emotion"],
            enforce_detection=False,
            silent=True
        )
        if isinstance(results, dict):
            results = [results]
        return [
            {
                "dominant_emotion": r.get("dominant_emotion", "unknown"),
                "scores": r.get("emotion", {}),
                "region": r.get("region", {})
            }
            for r in results
        ]
    except ImportError:
        return []
    except Exception:
        return []


def analyze_emotions_in_video(
        video_path: str,
        sample_fps: float = 0.2,
        max_frames: int   = 60
) -> List[Dict]:
    """
    Sample frames and run emotion detection on frames that contain faces.
    Returns list of {timestamp, dominant_emotion, scores} dicts.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step         = max(1, int(video_fps / sample_fps))
    frame_indices = list(range(0, total_frames, step))[:max_frames]

    results = []
    for fidx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
        ret, frame = cap.read()
        if not ret:
            continue
        small     = cv2.resize(frame, (320, 240))
        emotions  = detect_emotions_in_frame(small)
        timestamp = round(fidx / video_fps, 2)
        if emotions:
            results.append({
                "timestamp":        timestamp,
                "dominant_emotion": emotions[0]["dominant_emotion"],
                "scores":           emotions[0]["scores"]
            })

    cap.release()
    return results


# ─────────────────────────── score boosting ──────────────────────────────

def boost_scores_with_faces(
        timestamps:    List[float],
        scores:        List[float],
        face_data:     List[Dict],
        face_boost:    float = 0.15
) -> List[float]:
    """
    Boost scores for frames that contain faces
    (presenter is visible → likely important).
    """
    face_times = {d["timestamp"] for d in face_data if d["has_face"]}
    ts_array   = np.array(timestamps)
    boosted    = list(scores)

    for i, t in enumerate(timestamps):
        # Match within ±1 second of any face-detected timestamp
        if any(abs(t - ft) <= 1.0 for ft in face_times):
            boosted[i] = min(1.0, boosted[i] + face_boost)

    return boosted


EMOTION_BOOST_MAP = {
    "happy":     0.20,
    "surprise":  0.15,
    "neutral":   0.00,
    "sad":      -0.05,
    "angry":     0.05,
    "fear":      0.05,
    "disgust":  -0.05,
}

def boost_scores_with_emotions(
        timestamps:    List[float],
        scores:        List[float],
        emotion_data:  List[Dict]
) -> List[float]:
    """
    Adjust scores based on detected emotions.
    Positive/surprise emotions boost; negative emotions slightly reduce.
    """
    if not emotion_data:
        return scores

    boosted = list(scores)
    for edat in emotion_data:
        t      = edat["timestamp"]
        em     = edat["dominant_emotion"].lower()
        delta  = EMOTION_BOOST_MAP.get(em, 0.0)
        if delta == 0.0:
            continue
        for i, ts in enumerate(timestamps):
            if abs(ts - t) <= 1.5:
                boosted[i] = float(np.clip(boosted[i] + delta, 0, 1))

    return boosted


# ─────────────────────────── annotated thumbnail ─────────────────────────

def draw_face_boxes(frame_bgr: np.ndarray, faces: List[Dict]) -> np.ndarray:
    """Draw green bounding boxes around detected faces."""
    out = frame_bgr.copy()
    for f in faces:
        x, y, w, h = f["x"], f["y"], f["w"], f["h"]
        cv2.rectangle(out, (x, y), (x+w, y+h), (0, 200, 100), 2)
    return out
