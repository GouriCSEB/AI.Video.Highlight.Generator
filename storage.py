import os
import shutil
from pathlib import Path

def storage_available():
    """Check if storage (S3 or local) is available."""
    return True

def save_highlight(local_path, video_id):
    """
    Simulate S3 save by just verifying the local path.
    In a real app, this would upload to S3 and return the URL.
    """
    return {
        "path": local_path,
        "s3_key": None,
        "s3_url": None
    }

def save_report(local_path, video_id):
    """Simulate S3 save for reports."""
    return {
        "path": local_path,
        "s3_key": None,
        "s3_url": None
    }

def delete_file(s3_key):
    """Simulate S3 delete."""
    pass

def delete_local(path):
    """Delete local file if it exists."""
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass
