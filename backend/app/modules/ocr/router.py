"""Receipt OCR endpoint.

Uses pytesseract if the tesseract binary is available. Otherwise returns 503
with a hint. Parses simple "<name>...<price>" lines into draft items.
"""
import io
import re

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_current_internal_user, require_module_role
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.inventory.models import Item

router = APIRouter(
    prefix="/api/ocr",
    tags=["ocr"],
    dependencies=[Depends(get_current_internal_user)],
)

LINE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<qty>\d+(?:\.\d+)?)?\s*[xX*@]?\s*(?P<price>[\d,]+(?:\.\d+)?)\s*(?:원)?$"
)


def _extract_text(image_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"OCR dependency missing: {exc}. Install Pillow + pytesseract + tesseract.",
        )

    try:
        image = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(image, lang="kor+eng")
    except pytesseract.pytesseract.TesseractNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="tesseract binary not installed on the server",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"OCR failed: {exc}")


def _parse_lines(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 4:
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        name = m.group("name").strip()
        qty = float(m.group("qty")) if m.group("qty") else 1.0
        price = float(m.group("price").replace(",", ""))
        if price < 100:  # filter junk
            continue
        out.append({"name": name, "quantity": qty, "unit_price": price})
    return out


OCR_MAX_BYTES = 10 * 1024 * 1024
OCR_ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp", "image/tiff"}


@router.post("/receipt")
async def parse_receipt(
    file: UploadFile = File(...),
    create_items: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if file.content_type not in OCR_ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Image type '{file.content_type}' not supported",
        )
    raw = await file.read()
    if len(raw) > OCR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 10 MB)")
    text = _extract_text(raw)
    lines = _parse_lines(text)

    created: list[dict] = []
    if create_items and lines:
        # Optional: auto-register as inventory items (manager+ only)
        from app.core.auth import effective_role

        if effective_role(user, "inventory") not in ("admin", "manager"):
            raise HTTPException(
                status_code=403,
                detail="Need 'manager' on inventory to auto-create items",
            )

        for ln in lines:
            sku = "OCR-" + str(abs(hash(ln["name"])) % 10**8)
            if db.query(Item).filter(Item.sku == sku).first():
                continue
            item = Item(
                sku=sku,
                name=ln["name"][:200],
                unit="EA",
                unit_price=ln["unit_price"],
                stock_qty=ln["quantity"],
            )
            db.add(item)
            created.append({"sku": sku, "name": item.name})
        db.commit()

    return {"text": text, "lines": lines, "created": created}
