"""
user_store.py — Persistent highlight library using PostgreSQL + S3
Replaces the old JSON-file based system.
"""

import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from database import db, Highlight, Video
from storage import save_highlight as s3_save_highlight, save_report as s3_save_report


def save_highlight(user_id: str, job: dict, video_id: str) -> dict:
    """
    Save processed highlight to DB (and S3 if configured).
    Returns entry dict.
    """
    hl_src = Path(job.get("highlight_path", ""))
    if not hl_src.exists():
        raise FileNotFoundError("Highlight file not found.")

    # Upload to S3 (or keep local)
    hl_storage  = s3_save_highlight(str(hl_src), video_id)
    pdf_storage = {"path": None, "s3_key": None, "s3_url": None}
    pdf_src = job.get("report_path")
    if pdf_src and Path(pdf_src).exists():
        pdf_storage = s3_save_report(pdf_src, video_id)

    info  = job.get("video_info",     {})
    meta  = job.get("highlight_meta", {})
    tx    = job.get("transcript")     or {}
    thumbs = job.get("thumbnails",    [])
    cover  = thumbs[0] if thumbs else None

    def _face_pct(fd):
        if not fd: return None
        n = sum(1 for f in fd if f.get("has_face"))
        return round(n / max(len(fd), 1) * 100, 1)

    # Upsert: remove old highlight for same video_id first
    existing = Highlight.query.filter_by(video_id=video_id, user_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.flush()

    hl = Highlight(
        video_id            = video_id,
        user_id             = user_id,
        original_duration   = info.get("duration", 0),
        highlight_duration  = meta.get("highlight_duration", 0),
        segments_count      = len(job.get("segments", [])),
        has_transcript      = bool(tx.get("text")),
        transcript_excerpt  = (tx.get("text") or "")[:200],
        language            = tx.get("language", ""),
        keyword_hits_count  = len(job.get("keyword_hits", [])),
        face_pct            = _face_pct(job.get("face_data", [])),
        has_report          = bool(pdf_src and Path(pdf_src).exists()),
        highlight_path      = str(hl_src),
        highlight_s3_key    = hl_storage.get("s3_key"),
        highlight_s3_url    = hl_storage.get("s3_url"),
        report_path         = pdf_storage.get("path"),
        report_s3_key       = pdf_storage.get("s3_key"),
        report_s3_url       = pdf_storage.get("s3_url"),
        cover_thumbnail     = cover,
        finished_at         = datetime.utcnow(),
    )
    db.session.add(hl)
    db.session.commit()
    return hl.to_dict()


def load_history(user_id: str) -> list:
    """Return all highlights for a user, newest first."""
    highlights = (Highlight.query
                  .filter_by(user_id=user_id)
                  .order_by(Highlight.saved_at.desc())
                  .all())
    return [h.to_dict() for h in highlights]


def get_entry(user_id: str, video_id: str) -> Optional[Highlight]:
    """Return raw Highlight ORM object (or None)."""
    return Highlight.query.filter_by(video_id=video_id, user_id=user_id).first()


def delete_highlight(user_id: str, video_id: str) -> bool:
    """Delete highlight from DB and clean up files."""
    from storage import delete_file, delete_local
    hl = get_entry(user_id, video_id)
    if not hl:
        return False
    # Clean S3
    if hl.highlight_s3_key: delete_file(hl.highlight_s3_key)
    if hl.report_s3_key:    delete_file(hl.report_s3_key)
    # Clean local
    if hl.highlight_path:   delete_local(hl.highlight_path)
    if hl.report_path:      delete_local(hl.report_path)
    db.session.delete(hl)
    db.session.commit()
    return True
