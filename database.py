from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    avatar = db.Column(db.String(10), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "avatar": self.avatar,
            "is_active": self.is_active
        }

class Highlight(db.Model):
    __tablename__ = "highlights"
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(36), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    
    original_duration = db.Column(db.Float, default=0.0)
    highlight_duration = db.Column(db.Float, default=0.0)
    segments_count = db.Column(db.Integer, default=0)
    
    has_transcript = db.Column(db.Boolean, default=False)
    transcript_excerpt = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(20), nullable=True)
    keyword_hits_count = db.Column(db.Integer, default=0)
    face_pct = db.Column(db.Float, nullable=True)
    
    has_report = db.Column(db.Boolean, default=False)
    highlight_path = db.Column(db.String(255), nullable=True)
    highlight_s3_key = db.Column(db.String(255), nullable=True)
    highlight_s3_url = db.Column(db.String(512), nullable=True)
    
    report_path = db.Column(db.String(255), nullable=True)
    report_s3_key = db.Column(db.String(255), nullable=True)
    report_s3_url = db.Column(db.String(512), nullable=True)
    
    cover_thumbnail = db.Column(db.Text, nullable=True)  # Base64 encoded
    
    finished_at = db.Column(db.DateTime, nullable=True)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "video_id": self.video_id,
            "user_id": self.user_id,
            "original_duration": self.original_duration,
            "highlight_duration": self.highlight_duration,
            "segments_count": self.segments_count,
            "has_transcript": self.has_transcript,
            "transcript_excerpt": self.transcript_excerpt,
            "language": self.language,
            "keyword_hits_count": self.keyword_hits_count,
            "face_pct": self.face_pct,
            "has_report": self.has_report,
            "highlight_path": self.highlight_path,
            "highlight_s3_url": self.highlight_s3_url,
            "report_path": self.report_path,
            "report_s3_url": self.report_s3_url,
            "cover_thumbnail": self.cover_thumbnail,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "saved_at": self.saved_at.isoformat()
        }

class Video(db.Model):
    __tablename__ = "videos"
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(255), nullable=False)
    duration = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), default="uploaded")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
