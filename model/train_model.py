"""
train_model.py
==============
Trains a Random Forest classifier to detect "important" video frames.

Feature vector per frame (12 features):
  1. brightness        – mean pixel intensity
  2. contrast          – std dev of pixel intensity
  3. edge_density      – fraction of edge pixels (Canny)
  4. motion_score      – mean absolute diff vs previous frame
  5. color_variance    – variance of HSV hue channel
  6. saturation_mean   – mean HSV saturation
  7. sharpness         – Laplacian variance (focus measure)
  8. face_like_regions – simple skin-tone blob ratio
  9. text_like_density – high-frequency horizontal pattern
 10. scene_change      – histogram correlation drop vs prev frame
 11. temporal_position – normalised position in video (0–1)
 12. activity_score    – combined motion + edge composite

Labels are generated heuristically from the features themselves so the
model works even without ground-truth annotations.  In production you
would replace the synthetic labels with real human annotations.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (accuracy_score, precision_score,
                             recall_score, f1_score, confusion_matrix,
                             classification_report)
from sklearn.preprocessing import StandardScaler
import joblib
import json
import os

# ─────────────────────────── synthetic dataset ────────────────────────────

def generate_synthetic_dataset(n_samples: int = 2000, seed: int = 42):
    """
    Generate a realistic synthetic dataset that mimics real video-frame
    feature distributions so we can ship a pre-trained model.
    """
    rng = np.random.default_rng(seed)

    brightness        = rng.normal(120, 40, n_samples).clip(0, 255)
    contrast          = rng.normal(50,  20, n_samples).clip(0, 128)
    edge_density      = rng.beta(2, 5,      n_samples)
    motion_score      = rng.exponential(15, n_samples).clip(0, 100)
    color_variance    = rng.normal(30,  15, n_samples).clip(0, 100)
    saturation_mean   = rng.normal(80,  30, n_samples).clip(0, 255)
    sharpness         = rng.exponential(200, n_samples).clip(0, 2000)
    face_like_regions = rng.beta(1, 8,       n_samples)
    text_like_density = rng.beta(2, 6,       n_samples)
    scene_change      = rng.beta(1, 10,      n_samples)
    temporal_position = rng.uniform(0, 1,    n_samples)
    activity_score    = (motion_score / 100 * 0.5 +
                         edge_density       * 0.5)

    X = np.column_stack([
        brightness, contrast, edge_density, motion_score,
        color_variance, saturation_mean, sharpness,
        face_like_regions, text_like_density, scene_change,
        temporal_position, activity_score
    ])

    # Heuristic importance score → binary label
    importance = (
        0.20 * (brightness      / 255) +
        0.15 * (contrast        / 128) +
        0.20 * edge_density              +
        0.15 * (motion_score    / 100)   +
        0.10 * (sharpness       / 2000)  +
        0.10 * face_like_regions         +
        0.10 * scene_change
    )
    # Add noise so it's not trivially separable
    importance += rng.normal(0, 0.05, n_samples)
    y = (importance > 0.35).astype(int)

    feature_names = [
        "brightness", "contrast", "edge_density", "motion_score",
        "color_variance", "saturation_mean", "sharpness",
        "face_like_regions", "text_like_density", "scene_change",
        "temporal_position", "activity_score"
    ]
    return pd.DataFrame(X, columns=feature_names), y, feature_names


# ─────────────────────────── training pipeline ────────────────────────────

def train_and_save(model_dir: str = "model"):
    os.makedirs(model_dir, exist_ok=True)

    print("📊  Generating synthetic training data …")
    X, y, feature_names = generate_synthetic_dataset(n_samples=3000)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    print("🌲  Training Random Forest …")
    clf = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )
    clf.fit(X_train_s, y_train)

    # ── evaluation ──
    y_pred = clf.predict(X_test_s)
    y_prob = clf.predict_proba(X_test_s)[:, 1]

    metrics = {
        "accuracy":  round(accuracy_score(y_test, y_pred),  4),
        "precision": round(precision_score(y_test, y_pred), 4),
        "recall":    round(recall_score(y_test, y_pred),    4),
        "f1_score":  round(f1_score(y_test, y_pred),        4),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "feature_names": feature_names,
        "feature_importances": dict(zip(
            feature_names,
            [round(v, 4) for v in clf.feature_importances_]
        ))
    }

    print("\n📈  Evaluation Metrics")
    print(f"    Accuracy : {metrics['accuracy']:.4f}")
    print(f"    Precision: {metrics['precision']:.4f}")
    print(f"    Recall   : {metrics['recall']:.4f}")
    print(f"    F1 Score : {metrics['f1_score']:.4f}")
    print("\n" + classification_report(y_test, y_pred,
                                       target_names=["Not Important",
                                                     "Important"]))

    # ── save artefacts ──
    joblib.dump(clf,    os.path.join(model_dir, "model.pkl"))
    joblib.dump(scaler, os.path.join(model_dir, "scaler.pkl"))
    with open(os.path.join(model_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\n✅  Model saved to {model_dir}/model.pkl")
    print(f"✅  Scaler saved to {model_dir}/scaler.pkl")
    print(f"✅  Metrics saved to {model_dir}/metrics.json")
    return clf, scaler, metrics


if __name__ == "__main__":
    train_and_save()
