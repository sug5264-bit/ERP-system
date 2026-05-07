"""Shared utilities for exporting tabular data to CSV / Excel / PDF.

All exports support non-ASCII (Korean) text:
  - CSV is UTF-8 with a BOM so Excel auto-detects encoding
  - XLSX always Unicode
  - PDF uses the bundled CID font HYSMyeongJo-Medium so Korean glyphs render
  - Filenames in Content-Disposition use RFC 5987 (filename*=UTF-8'')
"""
import csv
import io
from typing import Iterable
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

ExportFormat = str  # "csv" | "xlsx" | "pdf"


def _content_disposition(filename: str, *, inline: bool = False) -> str:
    """Build a Content-Disposition header that handles non-ASCII filenames.

    `inline=True` lets the browser preview (e.g. PDF in a tab) instead of
    forcing a download. Provides both an ASCII fallback (`filename=`) and
    the UTF-8 RFC 5987 form (`filename*=UTF-8''…`) for old clients.
    """
    disposition = "inline" if inline else "attachment"
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "download"
    encoded = quote(filename, safe="")
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def export_table(
    rows: Iterable[Iterable],
    headers: list[str],
    filename: str,
    fmt: ExportFormat = "csv",
    inline: bool = False,
) -> StreamingResponse:
    fmt = (fmt or "csv").lower()
    if fmt == "csv":
        return _csv(rows, headers, filename)
    if fmt in ("xlsx", "excel"):
        return _xlsx(rows, headers, filename)
    if fmt == "pdf":
        return _pdf(rows, headers, filename, inline=inline)
    raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")


def _csv(rows, headers, filename) -> StreamingResponse:
    # Stream row-by-row so we never hold the whole table in memory.
    def generate():
        # UTF-8 BOM first so Excel auto-detects encoding.
        yield "﻿".encode("utf-8")
        line = io.StringIO()
        writer = csv.writer(line)
        writer.writerow(headers)
        yield line.getvalue().encode("utf-8")
        for row in rows:
            line.seek(0)
            line.truncate()
            writer.writerow(row)
            yield line.getvalue().encode("utf-8")

    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(f"{filename}.csv")},
    )


def _xlsx(rows, headers, filename) -> StreamingResponse:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(list(row))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(f"{filename}.xlsx")},
    )


# ---- PDF with Korean (CJK) font support ------------------------------------

_KOREAN_FONT_REGISTERED = False


def _ensure_korean_font() -> str:
    """Register reportlab's bundled Adobe CID font for Korean.

    Returns the font name to use. If registration fails (very old reportlab),
    falls back to Helvetica which can't render Korean — caller should still
    work, just with glyph squares.
    """
    global _KOREAN_FONT_REGISTERED
    name = "HYSMyeongJo-Medium"
    if _KOREAN_FONT_REGISTERED:
        return name
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        pdfmetrics.registerFont(UnicodeCIDFont(name))
        _KOREAN_FONT_REGISTERED = True
        return name
    except Exception:
        return "Helvetica"


def render_pdf_bytes(rows, headers, title: str) -> bytes:
    """Render a table as PDF and return raw bytes (for email attachments etc.)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font_name = _ensure_korean_font()

    rows_list = [list(r) for r in rows]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=title)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleKR",
        parent=styles["Title"],
        fontName=font_name,
    )
    story = [Paragraph(title, title_style), Spacer(1, 12)]

    data = [headers] + [[str(c) if c is not None else "" for c in r] for r in rows_list]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                # Apply the CJK-capable font to every cell, header included.
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buf.getvalue()


def _pdf(rows, headers, filename, inline: bool = False) -> StreamingResponse:
    pdf_bytes = render_pdf_bytes(rows, headers, filename)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": _content_disposition(
                f"{filename}.pdf", inline=inline
            )
        },
    )
