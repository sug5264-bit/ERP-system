"""공통 Excel/CSV 일괄 import 유틸.

품목·거래처·공급처 등 다양한 엔티티가 같은 패턴(헤더 한글/영문 별칭, xlsx+csv
자동 감지, 빈 행 스킵, 라인별 오류 누적)을 쓰므로 한 곳에 모음.
"""
from __future__ import annotations

import csv as _csv
import io as _io
from typing import Iterator

from fastapi import HTTPException, UploadFile


async def parse_upload(
    file: UploadFile,
    alias: dict[str, str],
) -> Iterator[dict]:
    """xlsx 또는 csv 파일에서 행을 dict로 yield.

    alias: 원본 헤더(소문자 strip) → 표준 키. 매칭 안되면 컬럼 무시.
    """
    raw = await file.read()
    filename = (file.filename or "").lower()

    rows: list[dict] = []
    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            from openpyxl import load_workbook

            wb = load_workbook(_io.BytesIO(raw), data_only=True)
            ws = wb.active
            it = ws.iter_rows(values_only=True)
            try:
                header_row = next(it)
            except StopIteration:
                raise HTTPException(status_code=400, detail="빈 파일입니다.")
            keys = [
                alias.get(str(h or "").strip().lower(), None) for h in header_row
            ]
            for raw_row in it:
                if all(c is None or str(c).strip() == "" for c in raw_row):
                    continue
                rows.append(
                    {k: v for k, v in zip(keys, raw_row) if k is not None}
                )
        else:
            text = raw.decode("utf-8-sig")
            reader = _csv.reader(_io.StringIO(text))
            header_row = next(reader, None)
            if not header_row:
                raise HTTPException(status_code=400, detail="빈 파일입니다.")
            keys = [alias.get(h.strip().lower(), None) for h in header_row]
            for raw_row in reader:
                if not any(c.strip() for c in raw_row):
                    continue
                rows.append(
                    {k: v for k, v in zip(keys, raw_row) if k is not None}
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"파일을 읽을 수 없습니다: {exc}"
        )

    return rows
