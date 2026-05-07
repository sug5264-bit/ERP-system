import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_current_internal_user, require_role
from app.core.config import settings
from app.core.db import get_db
from app.modules.attachments.models import Attachment
from app.modules.attachments.schemas import AttachmentOut
from app.modules.auth.models import User

router = APIRouter(
    prefix="/api/attachments",
    tags=["attachments"],
    dependencies=[Depends(get_current_internal_user)],
)


def _storage_dir() -> Path:
    path = Path(settings.upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


# Whitelist of safe extensions. Reject everything else even if MIME claims OK.
ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".csv", ".xlsx", ".xls", ".doc", ".docx", ".ppt", ".pptx",
    ".txt", ".md", ".json", ".zip",
}


# Image MIME → magic-byte signatures. We only sniff the easy cases; if the
# extension is in our whitelist but magic doesn't match, reject as a defence
# against polyglot files (e.g. an .exe renamed to .png).
MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    ".pdf": [b"%PDF-"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"],  # RIFF....WEBP
    ".zip": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    ".xlsx": [b"PK\x03\x04"],
    ".docx": [b"PK\x03\x04"],
    ".pptx": [b"PK\x03\x04"],
}


def _magic_ok(suffix: str, head: bytes) -> bool:
    sigs = MAGIC_SIGNATURES.get(suffix)
    if not sigs:
        return True  # types without a sig (txt, csv, json, etc.)
    return any(head.startswith(s) for s in sigs)


@router.post("", response_model=AttachmentOut)
async def upload(
    file: UploadFile = File(...),
    related_type: str | None = Form(None),
    related_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if file.size and file.size > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="File too large")

    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: "
            + ", ".join(sorted(ALLOWED_EXTENSIONS)),
        )
    # Strip everything but the extension from the original filename — never trust path components.
    safe_basename = Path(file.filename or "upload").name
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    target = _storage_dir() / stored_name

    # Stream-write to disk in chunks so we don't hold the whole file in RAM.
    # Enforce the size cap as we go.
    written = 0
    chunk_size = 64 * 1024
    first_chunk = b""
    try:
        with open(target, "wb") as out:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                if not first_chunk:
                    first_chunk = chunk[:16]
                written += len(chunk)
                if written > settings.upload_max_bytes:
                    raise HTTPException(status_code=413, detail="File too large")
                out.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except Exception:
        target.unlink(missing_ok=True)
        raise

    if not _magic_ok(suffix, first_chunk):
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=415,
            detail=f"File contents don't match {suffix} signature",
        )

    attachment = Attachment(
        related_type=related_type,
        related_id=related_id,
        filename=safe_basename or stored_name,
        content_type=file.content_type or "application/octet-stream",
        size=written,
        storage_path=str(target),
        uploaded_by=current_user.id,
    )
    db.add(attachment)
    try:
        db.commit()
    except Exception:
        db.rollback()
        # Clean up the orphan file so we don't leak disk space.
        target.unlink(missing_ok=True)
        raise
    db.refresh(attachment)
    return attachment


@router.get("", response_model=list[AttachmentOut])
def list_attachments(
    related_type: str | None = None,
    related_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Attachment)
    if related_type:
        q = q.filter(Attachment.related_type == related_type)
    if related_id is not None:
        q = q.filter(Attachment.related_id == related_id)
    return q.order_by(Attachment.created_at.desc()).all()


def _resolve_safe_path(stored: str) -> Path:
    """Refuse to serve any path that escapes the configured upload_dir."""
    upload_root = Path(settings.upload_dir).resolve()
    target = Path(stored).resolve()
    try:
        target.relative_to(upload_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Path outside upload root")
    return target


@router.get("/{attachment_id}/download")
def download(attachment_id: int, db: Session = Depends(get_db)):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Not found")
    safe = _resolve_safe_path(att.storage_path)
    if not safe.exists():
        raise HTTPException(status_code=410, detail="File missing on disk")
    return FileResponse(str(safe), filename=att.filename, media_type=att.content_type)


@router.delete(
    "/{attachment_id}",
    dependencies=[Depends(require_role("manager"))],
)
def delete(attachment_id: int, db: Session = Depends(get_db)):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        safe = _resolve_safe_path(att.storage_path)
        os.remove(safe)
    except OSError:
        pass
    db.delete(att)
    db.commit()
    return {"ok": True}
