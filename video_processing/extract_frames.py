"""
extract_frames.py
=================
Extracts frames from a video file and computes per-frame feature vectors
that the ML model uses to score importance.

Feature vector (12 values per frame):
  brightness, contrast, edge_density, motion_score,
  color_variance, saturation_mean, sharpness,
  face_like_regions, text_like_density, scene_change,
  temporal_position, activity_score
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Dict


# ─────────────────────────── helpers ──────────────────────────────────────

def _brightness_contrast(gray: np.ndarray) -> Tuple[float, float]:
    return float(gray.mean()), float(gray.std())


def _edge_density(gray: np.ndarray) -> float:
    edges = cv2.Canny(gray, 50, 150)
    return float(edges.mean() / 255.0)


def _motion_score(gray: np.ndarray, prev_gray: np.ndarray | None) -> float:
    if prev_gray is None:
        return 0.0
    diff = cv2.absdiff(gray, prev_gray)
    return float(diff.mean())


def _color_variance_saturation(bgr: np.ndarray) -> Tuple[float, float]:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hue_var = float(np.var(hsv[:, :, 0]))
    sat_mean = float(hsv[:, :, 1].mean())
    return hue_var, sat_mean


def _sharpness(gray: np.ndarray) -> float:
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(lap.var())


def _face_like_regions(bgr: np.ndarray) -> float:
    """
    Approximate face-likelihood via skin-tone segmentation in YCrCb.
    Returns fraction of pixels that resemble skin tone.
    """
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycrcb,
                       np.array([0,   133, 77],  dtype=np.uint8),
                       np.array([255, 173, 127], dtype=np.uint8))
    return float(mask.mean() / 255.0)


def _text_like_density(gray: np.ndarray) -> float:
    """
    Estimate text presence via adaptive threshold blob density.
    """
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=15, C=8
    )
    return float(thresh.mean() / 255.0)


def _scene_change(gray: np.ndarray, prev_gray: np.ndarray | None) -> float:
    if prev_gray is None:
        return 0.0
    hist_curr = cv2.calcHist([gray], [0], None, [64], [0, 256]).flatten()
    hist_prev = cv2.calcHist([prev_gray], [0], None, [64], [0, 256]).flatten()
    hist_curr /= (hist_curr.sum() + 1e-8)
    hist_prev /= (hist_prev.sum() + 1e-8)
    corr = float(cv2.compareHist(
        hist_curr.astype(np.float32),
        hist_prev.astype(np.float32),
        cv2.HISTCMP_CORREL
    ))
    return float(1.0 - corr)   # high value → scene change


# ─────────────────────────── main extractor ───────────────────────────────

def extract_features(
        video_path: str,
        sample_fps: float = 1.0,
        max_frames: int = 300,
        resize_to: Tuple[int, int] = (320, 180)
) -> Tuple[np.ndarray, List[Dict]]:
    """
    Parameters
    ----------
    video_path  : path to input video
    sample_fps  : frames to analyse per second of video
    max_frames  : hard cap to keep processing fast
    resize_to   : (width, height) to resize frames before analysis

    Returns
    -------
    features : ndarray of shape (N, 12)
    metadata : list of dicts with timestamp, frame_idx, thumbnail_b64
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    duration_sec = total_frames / video_fps

    # Determine which frame indices to sample
    step = max(1, int(video_fps / sample_fps))
    frame_indices = list(range(0, total_frames, step))
    if len(frame_indices) > max_frames:
        step2 = len(frame_indices) // max_frames
        frame_indices = frame_indices[::step2]

    feature_rows: List[List[float]] = []
    metadata:     List[Dict]        = []
    prev_gray = None
    total = len(frame_indices)

    for rank, fidx in enumerate(frame_indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
        ret, frame = cap.read()
        if not ret:
            continue

        frame_small = cv2.resize(frame, resize_to)
        gray        = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)

        brightness, contrast    = _brightness_contrast(gray)
        edge_den                = _edge_density(gray)
        motion                  = _motion_score(gray, prev_gray)
        color_var, sat_mean     = _color_variance_saturation(frame_small)
        sharpness               = _sharpness(gray)
        face_like               = _face_like_regions(frame_small)
        text_like               = _text_like_density(gray)
        scene_chg               = _scene_change(gray, prev_gray)
        temporal_pos            = fidx / max(total_frames - 1, 1)
        activity                = (min(motion, 100) / 100 * 0.5 +
                                   edge_den * 0.5)

        feature_rows.append([
            brightness, contrast, edge_den, motion,
            color_var, sat_mean, sharpness,
            face_like, text_like, scene_chg,
            temporal_pos, activity
        ])

        timestamp = fidx / video_fps
        metadata.append({
            "frame_idx": fidx,
            "timestamp": round(timestamp, 2),
            "rank":      rank,
            "total":     total
        })

        prev_gray = gray

    cap.release()

    features = np.array(feature_rows, dtype=np.float32)
    return features, metadata


def get_video_info(video_path: str) -> Dict:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {}
    info = {
        "fps":      cap.get(cv2.CAP_PROP_FPS),
        "width":    int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height":   int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "frames":   int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        "duration": int(cap.get(cv2.CAP_PROP_FRAME_COUNT) /
                        max(cap.get(cv2.CAP_PROP_FPS), 1))
    }
    cap.release()
    return info
