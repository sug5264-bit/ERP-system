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

    contents = await file.read()
    if len(contents) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="File too large")

    with open(target, "wb") as f:
        f.write(contents)

    attachment = Attachment(
        related_type=related_type,
        related_id=related_id,
        filename=safe_basename or stored_name,
        content_type=file.content_type or "application/octet-stream",
        size=len(contents),
        storage_path=str(target),
        uploaded_by=current_user.id,
    )
    db.add(attachment)
    db.commit()
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
