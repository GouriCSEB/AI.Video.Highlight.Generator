"""
app.py  –  AI Video Highlight Generator  (Flask backend)
Advanced edition with:
  - Speech-to-text (Whisper)
  - Keyword boosting
  - Face + emotion detection
  - PDF report generation
"""

import os, json, uuid, threading, traceback, base64, time
from pathlib import Path
from flask import (Flask, request, jsonify, send_file, render_template, Response)
try:
    from flask_cors import CORS
    _has_cors = True
except ImportError:
    _has_cors = False

import numpy as np
import joblib
import cv2
from datetime import timedelta
from config   import config
from database import db
from auth import (create_user, login_user_by_email, login_session,
                  logout_session, current_user, is_logged_in, login_required)
from user_store import save_highlight, load_history, delete_highlight, get_entry
from storage import storage_available

from video_processing.extract_frames    import extract_features, get_video_info
from video_processing.highlight_generator import (
    select_highlight_segments, generate_highlight_video, build_timeline
)

# ── optional AI features (fail gracefully if not installed) ──
try:
    from ai_features.transcription  import transcribe_video, boost_scores_with_keywords
    HAS_WHISPER = True
except Exception:
    HAS_WHISPER = False

try:
    from ai_features.face_emotion   import (analyze_faces_in_video,
                                             analyze_emotions_in_video,
                                             boost_scores_with_faces,
                                             boost_scores_with_emotions)
    HAS_FACE = True
except Exception:
    HAS_FACE = False

try:
    from ai_features.report_generator import generate_report
    HAS_REPORT = True
except Exception:
    HAS_REPORT = False

# ─────────────────────────── app setup ────────────────────────────────────
BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = config.UPLOAD_DIR
OUTPUT_DIR = config.OUTPUT_DIR
MODEL_DIR  = BASE_DIR / "model"

for d in [UPLOAD_DIR, OUTPUT_DIR]: d.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "webm"}

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"]         = config.MAX_CONTENT_LENGTH
app.config["SECRET_KEY"]                 = config.SECRET_KEY
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SQLALCHEMY_DATABASE_URI"]    = config.SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = config.SQLALCHEMY_ENGINE_OPTIONS

db.init_app(app)
if _has_cors: CORS(app)

# Create all tables on startup (safe — skips existing tables)
with app.app_context():
    db.create_all()

jobs: dict = {}

# ─────────────────────────── model loader ─────────────────────────────────
_clf = _scaler = _metrics_cache = None

def _load_model():
    global _clf, _scaler
    mp, sp = MODEL_DIR / "model.pkl", MODEL_DIR / "scaler.pkl"
    if not mp.exists():
        from model.train_model import train_and_save
        train_and_save(str(MODEL_DIR))
    _clf, _scaler = joblib.load(mp), joblib.load(sp)

def _get_metrics():
    global _metrics_cache
    if _metrics_cache is None:
        p = MODEL_DIR / "metrics.json"
        if p.exists():
            with open(p) as f: _metrics_cache = json.load(f)
    return _metrics_cache or {}

_load_model()

# ─────────────────────────── helpers ──────────────────────────────────────
def allowed_file(fn): return "." in fn and fn.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS
def _predict(feat): return _clf.predict_proba(_scaler.transform(feat))[:,1]

def _thumbnail(video_path, timestamp):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(timestamp * fps))
    ret, frame = cap.read(); cap.release()
    if not ret: return ""
    frame = cv2.resize(frame, (320, 180))
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf).decode()

def _seg_score(timestamps, scores, s, e):
    vals = [sc for t, sc in zip(timestamps, scores) if s <= t <= e]
    return round(float(np.mean(vals)) * 100, 1) if vals else 0.0

def _fmt(s): return f"{int(s)//60}m {int(s)%60}s"

# ─────────────────────────── background worker ────────────────────────────
def _process_job(video_id, video_path, top_fraction, keywords, enable_whisper,
                 enable_face, enable_emotion, enable_report):
    def upd(status, progress): jobs[video_id].update({"status": status, "progress": progress})
    try:
        upd("extracting", 10)
        info = get_video_info(str(video_path))
        jobs[video_id]["video_info"] = info

        features, metadata = extract_features(str(video_path), sample_fps=1.0, max_frames=300)
        upd("scoring", 30)
        if not len(features): raise ValueError("No frames extracted.")

        scores     = _predict(features).tolist()
        timestamps = [m["timestamp"] for m in metadata]

        # ── Face detection + score boost ──────────────────────────────────
        face_data    = []
        emotion_data = []
        if enable_face and HAS_FACE:
            upd("detecting_faces", 38)
            face_data = analyze_faces_in_video(str(video_path), sample_fps=0.5, max_frames=100)
            scores    = boost_scores_with_faces(timestamps, scores, face_data, face_boost=0.15)

            if enable_emotion:
                upd("detecting_emotions", 44)
                emotion_data = analyze_emotions_in_video(str(video_path), sample_fps=0.2, max_frames=50)
                scores       = boost_scores_with_emotions(timestamps, scores, emotion_data)

        # ── Whisper transcription + keyword boost ─────────────────────────
        transcript   = None
        keyword_hits = []
        if enable_whisper:
            if not HAS_WHISPER:
                transcript = {"text": "", "segments": [], "language": "unknown",
                              "error": "openai-whisper not installed. Run: pip install openai-whisper torch"}
            else:
                upd("transcribing", 50)
                transcript = transcribe_video(str(video_path), model_size="base")
                if transcript.get("error"):
                    jobs[video_id]["whisper_error"] = transcript["error"]
                if transcript.get("segments"):
                    scores, keyword_hits = boost_scores_with_keywords(
                        timestamps, scores,
                        transcript["segments"],
                        user_keywords=keywords,
                        boost_amount=0.25
                    )

        upd("selecting_segments", 60)
        segments = select_highlight_segments(
            timestamps, scores,
            top_fraction=top_fraction,
            min_gap_sec=10.0,      # merge frames within 10s of each other
            segment_pad_sec=3.0,   # 3s context before/after
            min_segment_dur=5.0,   # drop clips under 5s
            max_segments=15        # max 15 segments
        )

        # Safety fallback: if still empty, use very loose settings
        if not segments:
            segments = select_highlight_segments(
                timestamps, scores,
                top_fraction=max(top_fraction, 0.5),
                min_gap_sec=5.0,
                segment_pad_sec=2.0,
                min_segment_dur=2.0,
                max_segments=20
            )

        upd("generating", 70)
        hl_path = OUTPUT_DIR / f"{video_id}_highlight.mp4"
        original_dur = info.get("duration", 300)
        max_hl_dur   = min(300.0, original_dur * 0.40)  # max 40% of video or 5 min
        hl_meta = generate_highlight_video(str(video_path), str(hl_path), segments, max_duration=max_hl_dur)

        duration = info.get("duration", timestamps[-1] if timestamps else 0)
        timeline = build_timeline(timestamps, scores, segments, duration)

        seg_scores = [_seg_score(timestamps, scores, s, e) for s, e in segments]
        thumbnails = [_thumbnail(str(video_path), s + (e-s)/2) for s, e in segments]

        # ── PDF Report ────────────────────────────────────────────────────
        report_path = None
        if enable_report and HAS_REPORT:
            upd("generating_report", 90)
            report_path = str(OUTPUT_DIR / f"{video_id}_report.pdf")
            try:
                generate_report(
                    output_path    = report_path,
                    video_filename = jobs[video_id].get("filename", "video"),
                    video_info     = info,
                    highlight_meta = hl_meta,
                    segments       = segments,
                    seg_scores     = seg_scores,
                    timeline       = timeline,
                    transcript     = transcript,
                    face_data      = face_data,
                    emotion_data   = emotion_data,
                    keyword_hits   = keyword_hits,
                    ml_metrics     = _get_metrics(),
                )
            except Exception as re:
                report_path = None
                jobs[video_id]["report_error"] = str(re)

        jobs[video_id].update({
            "status":         "done",      "progress":       100,
            "scores":         scores,      "timestamps":     timestamps,
            "segments":       segments,    "seg_scores":     seg_scores,
            "thumbnails":     thumbnails,  "timeline":       timeline,
            "highlight_meta": hl_meta,     "highlight_path": str(hl_path),
            "transcript":     transcript,  "keyword_hits":   keyword_hits,
            "face_data":      face_data,   "emotion_data":   emotion_data,
            "report_path":    report_path, "finished_at":    time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        # Auto-save to user's personal library if logged in
        uid = jobs[video_id].get("user_id")
        if uid:
            try:
                save_highlight(uid, jobs[video_id], video_id)
            except Exception as se:
                jobs[video_id]["save_error"] = str(se)

    except Exception as exc:
        jobs[video_id].update({"status": "error", "error": str(exc),
                                "traceback": traceback.format_exc()})


# ─────────────────────────── routes ───────────────────────────────────────

# ─────────────────────────── auth routes ─────────────────────────────────

@app.route("/login")
def login_page():
    if is_logged_in():
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/signup")
def signup_page():
    if is_logged_in():
        return redirect(url_for("index"))
    return render_template("signup.html")

@app.route("/api/signup", methods=["POST"])
def api_signup():
    body = request.get_json(silent=True) or {}
    result = create_user(body.get("name",""), body.get("email",""), body.get("password",""))
    return jsonify(result), (200 if result["ok"] else 400)

@app.route("/api/login", methods=["POST"])
def api_login():
    body   = request.get_json(silent=True) or {}
    result = login_user_by_email(body.get("email",""), body.get("password",""))
    if result["ok"]:
        login_session(result["user"])
        next_url = request.args.get("next", "/")
        result["redirect"] = next_url
    return jsonify(result), (200 if result["ok"] else 401)

@app.route("/api/logout", methods=["POST"])
def api_logout():
    logout_session()
    return jsonify({"ok": True, "redirect": "/login"})

@app.route("/api/me")
def api_me():
    user = current_user()
    if not user:
        return jsonify({"logged_in": False}), 401
    return jsonify({"logged_in": True, "user": user})

# ─────────────────────────── main app routes ──────────────────────────────

@app.route("/")
def index(): return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "video" not in request.files: return jsonify({"error": "No file"}), 400
    file = request.files["video"]
    if not file.filename or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file"}), 400
    vid  = str(uuid.uuid4())[:8]
    ext  = file.filename.rsplit(".",1)[1].lower()
    path = UPLOAD_DIR / f"{vid}.{ext}"
    file.save(path)
    info = get_video_info(str(path))
    user  = current_user()
    jobs[vid] = {"status": "uploaded", "progress": 0, "filename": file.filename,
                 "video_path": str(path), "video_info": info,
                 "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "user_id": user["id"] if user else None}
    return jsonify({"video_id": vid, "filename": file.filename, "video_info": info,
                    "is_logged_in": user is not None})


@app.route("/process/<vid>", methods=["POST"])
def process(vid):
    job = jobs.get(vid)
    if not job: return jsonify({"error": "Unknown video_id"}), 404
    if job["status"] not in ("uploaded", "error"):
        return jsonify({"status": job["status"]}), 200

    body = request.get_json(silent=True) or {}
    top_fraction   = float(np.clip(body.get("highlight_fraction", 0.30), 0.05, 0.80))
    keywords       = [k.strip() for k in body.get("keywords", "").split(",") if k.strip()]
    enable_whisper = bool(body.get("enable_whisper", True))
    enable_face    = bool(body.get("enable_face",    True))
    enable_emotion = bool(body.get("enable_emotion", True))
    enable_report  = bool(body.get("enable_report",  True))

    jobs[vid].update({"status": "queued", "progress": 0})
    threading.Thread(
        target=_process_job,
        args=(vid, Path(job["video_path"]), top_fraction, keywords,
              enable_whisper, enable_face, enable_emotion, enable_report),
        daemon=True
    ).start()
    return jsonify({"video_id": vid, "status": "queued"})


@app.route("/status/<vid>")
def status(vid):
    job = jobs.get(vid)
    if not job: return jsonify({"error": "Unknown"}), 404
    resp = {"video_id": vid, "status": job["status"],
            "progress": job.get("progress", 0), "error": job.get("error")}
    if job["status"] == "done":
        resp.update({
            "highlight_meta": job.get("highlight_meta", {}),
            "segments":       job.get("segments",       []),
            "seg_scores":     job.get("seg_scores",     []),
            "thumbnails":     job.get("thumbnails",     []),
            "timeline":       job.get("timeline",       []),
            "video_info":     job.get("video_info",     {}),
            "transcript":     {
                "text":     (job.get("transcript") or {}).get("text", ""),
                "segments": (job.get("transcript") or {}).get("segments", []),
                "language": (job.get("transcript") or {}).get("language", ""),
                "error":    (job.get("transcript") or {}).get("error"),
            },
            "keyword_hits":   job.get("keyword_hits",   []),
            "face_summary":   _face_summary(job.get("face_data",    [])),
            "emotion_summary":_emotion_summary(job.get("emotion_data", [])),
            "has_report":     job.get("report_path") is not None,
        })
    return jsonify(resp)


def _face_summary(face_data):
    if not face_data: return None
    n_face = sum(1 for f in face_data if f.get("has_face"))
    return {"frames_with_face": n_face, "total_sampled": len(face_data),
            "pct": round(n_face / max(len(face_data),1) * 100, 1)}

def _emotion_summary(emotion_data):
    if not emotion_data: return None
    from collections import Counter
    c = Counter(e["dominant_emotion"] for e in emotion_data)
    return dict(c.most_common())


@app.route("/history")
def history():
    out = []
    for vid, job in jobs.items():
        if job["status"] == "done":
            meta = job.get("highlight_meta", {})
            info = job.get("video_info",     {})
            out.append({"video_id": vid, "filename": job.get("filename","?"),
                         "uploaded_at": job.get("uploaded_at",""),
                         "finished_at": job.get("finished_at",""),
                         "original_duration":  info.get("duration", 0),
                         "highlight_duration": meta.get("highlight_duration", 0),
                         "segments_count":     meta.get("segments_count", 0),
                         "has_transcript":     bool(job.get("transcript",{}) and job["transcript"].get("text")),
                         "has_report":         job.get("report_path") is not None})
    return jsonify(sorted(out, key=lambda x: x["finished_at"], reverse=True))


@app.route("/highlight/<vid>")
def highlight(vid):
    job = jobs.get(vid)
    if not job or job["status"] != "done": return jsonify({"error": "Not ready"}), 404
    path = Path(job["highlight_path"])
    if not path.exists(): return jsonify({"error": "Missing"}), 404
    size = path.stat().st_size
    rh   = request.headers.get("Range")
    if rh:
        parts = rh.replace("bytes=","").split("-")
        s = int(parts[0]) if parts[0] else 0
        e = int(parts[1]) if len(parts)>1 and parts[1] else size-1
        e = min(e, size-1); n = e-s+1
        with open(path,"rb") as f: f.seek(s); data = f.read(n)
        return Response(data, 206, mimetype="video/mp4",
                        headers={"Content-Range":f"bytes {s}-{e}/{size}",
                                 "Accept-Ranges":"bytes","Content-Length":str(n),"Cache-Control":"no-cache"})
    with open(path,"rb") as f: data = f.read()
    return Response(data, 200, mimetype="video/mp4",
                    headers={"Accept-Ranges":"bytes","Content-Length":str(size),"Cache-Control":"no-cache"})


@app.route("/download/<vid>")
def download(vid):
    job = jobs.get(vid)
    if not job or job["status"] != "done": return jsonify({"error": "Not ready"}), 404
    return send_file(job["highlight_path"], mimetype="video/mp4",
                     as_attachment=True, download_name=f"highlight_{vid}.mp4")


@app.route("/report/<vid>")
def report(vid):
    job = jobs.get(vid)
    if not job or not job.get("report_path"): return jsonify({"error": "No report"}), 404
    p = Path(job["report_path"])
    if not p.exists(): return jsonify({"error": "File missing"}), 404
    return send_file(str(p), mimetype="application/pdf",
                     as_attachment=True, download_name=f"report_{vid}.pdf")


# ─────────────────────────── user library routes ──────────────────────────

@app.route("/library")
def library_page():
    if not is_logged_in():
        return redirect(url_for("login_page") + "?next=/library")
    return render_template("library.html")

@app.route("/api/library")
def api_library():
    user = current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401
    entries = load_history(user["id"])
    # Strip heavy thumbnail from list view (send only first as cover)
    slim = []
    for e in entries:
        s = {k: v for k, v in e.items() if k != "cover_thumbnail"}
        s["has_cover"] = bool(e.get("cover_thumbnail"))
        slim.append(s)
    return jsonify({"entries": slim, "count": len(slim)})

@app.route("/api/library/<vid>/cover")
def library_cover(vid):
    user = current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401
    entry = get_entry(user["id"], vid)
    if not entry or not entry.get("cover_thumbnail"):
        return jsonify({"error": "No cover"}), 404
    img_data = base64.b64decode(entry["cover_thumbnail"])
    return Response(img_data, mimetype="image/jpeg")

@app.route("/api/library/<vid>/save", methods=["POST"])
def api_save_highlight(vid):
    """Manually save/re-save a highlight to the user library."""
    user = current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401
    job = jobs.get(vid)
    if not job or job["status"] != "done":
        return jsonify({"error": "Video not ready"}), 404
    try:
        entry = save_highlight(user["id"], job, vid)
        return jsonify({"ok": True, "entry": {k: v for k, v in entry.items()
                                               if k != "cover_thumbnail"}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/library/<vid>/delete", methods=["POST"])
def api_delete_highlight(vid):
    user = current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401
    ok = delete_highlight(user["id"], vid)
    return jsonify({"ok": ok})

@app.route("/library/download/<vid>")
def library_download(vid):
    user = current_user()
    if not user:
        return redirect(url_for("login_page"))
    entry = get_entry(user["id"], vid)
    if not entry:
        return jsonify({"error": "Not found"}), 404
    p = Path(entry["highlight_path"])
    if not p.exists():
        return jsonify({"error": "File missing"}), 404
    return send_file(str(p), mimetype="video/mp4",
                     as_attachment=True,
                     download_name=f"highlight_{entry['filename']}")

@app.route("/library/stream/<vid>")
def library_stream(vid):
    user = current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401
    entry = get_entry(user["id"], vid)
    if not entry:
        return jsonify({"error": "Not found"}), 404
    path = Path(entry["highlight_path"])
    if not path.exists():
        return jsonify({"error": "File missing"}), 404
    size = path.stat().st_size
    rh   = request.headers.get("Range")
    if rh:
        parts = rh.replace("bytes=","").split("-")
        s = int(parts[0]) if parts[0] else 0
        e = int(parts[1]) if len(parts)>1 and parts[1] else size-1
        e = min(e, size-1); n = e-s+1
        with open(path,"rb") as f: f.seek(s); data = f.read(n)
        return Response(data, 206, mimetype="video/mp4",
                        headers={"Content-Range":f"bytes {s}-{e}/{size}",
                                 "Accept-Ranges":"bytes","Content-Length":str(n)})
    with open(path,"rb") as f: data = f.read()
    return Response(data, 200, mimetype="video/mp4",
                    headers={"Accept-Ranges":"bytes","Content-Length":str(size)})

@app.route("/library/report/<vid>")
def library_report(vid):
    user = current_user()
    if not user:
        return redirect(url_for("login_page"))
    entry = get_entry(user["id"], vid)
    if not entry or not entry.get("report_path"):
        return jsonify({"error": "No report"}), 404
    p = Path(entry["report_path"])
    if not p.exists():
        return jsonify({"error": "File missing"}), 404
    return send_file(str(p), mimetype="application/pdf",
                     as_attachment=True,
                     download_name=f"report_{entry['filename']}.pdf")


@app.route("/metrics")
def metrics(): return jsonify(_get_metrics())


@app.route("/capabilities")
def capabilities():
    return jsonify({"whisper": HAS_WHISPER, "face": HAS_FACE, "report": HAS_REPORT})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
