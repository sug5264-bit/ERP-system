"""Shared utilities for exporting tabular data to CSV / Excel / PDF."""
import csv
import io
from typing import Iterable

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

ExportFormat = str  # "csv" | "xlsx" | "pdf"


def export_table(
    rows: Iterable[Iterable],
    headers: list[str],
    filename: str,
    fmt: ExportFormat = "csv",
) -> StreamingResponse:
    fmt = (fmt or "csv").lower()
    if fmt == "csv":
        return _csv(rows, headers, filename)
    if fmt in ("xlsx", "excel"):
        return _xlsx(rows, headers, filename)
    if fmt == "pdf":
        return _pdf(rows, headers, filename)
    raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")


def _csv(rows, headers, filename) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    data = "﻿" + buf.getvalue()  # BOM so Excel opens UTF-8 correctly
    return StreamingResponse(
        iter([data]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
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
        headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
    )


def _pdf(rows, headers, filename) -> StreamingResponse:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    rows_list = [list(r) for r in rows]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=filename)
    styles = getSampleStyleSheet()
    story = [Paragraph(filename, styles["Title"]), Spacer(1, 12)]

    data = [headers] + [[str(c) if c is not None else "" for c in r] for r in rows_list]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )
