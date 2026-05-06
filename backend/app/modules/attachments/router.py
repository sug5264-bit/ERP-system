import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_role
from app.core.config import settings
from app.core.db import get_db
from app.modules.attachments.models import Attachment
from app.modules.attachments.schemas import AttachmentOut
from app.modules.auth.models import User

router = APIRouter(
    prefix="/api/attachments",
    tags=["attachments"],
    dependencies=[Depends(get_current_user)],
)


def _storage_dir() -> Path:
    path = Path(settings.upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


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

    suffix = Path(file.filename or "upload").suffix
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
        filename=file.filename or stored_name,
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


@router.get("/{attachment_id}/download")
def download(attachment_id: int, db: Session = Depends(get_db)):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Not found")
    if not os.path.exists(att.storage_path):
        raise HTTPException(status_code=410, detail="File missing on disk")
    return FileResponse(att.storage_path, filename=att.filename, media_type=att.content_type)


@router.delete(
    "/{attachment_id}",
    dependencies=[Depends(require_role("manager"))],
)
def delete(attachment_id: int, db: Session = Depends(get_db)):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        os.remove(att.storage_path)
    except OSError:
        pass
    db.delete(att)
    db.commit()
    return {"ok": True}
