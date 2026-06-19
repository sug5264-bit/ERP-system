"""한국 ERP 표준 양식 PDF 생성기.

지원 양식:
- 거래명세표 (Transaction Statement / Delivery Slip)
- 인수증 (Acceptance Receipt)
- 세금계산서 (Tax Invoice — 국세청 양식 준용)
- 발주서 (Purchase Order)
- 견적서 (Quotation)
- 거래원장 (Customer Ledger)

모든 양식은:
- A4 세로, NanumGothic(CID 폰트) 한글 렌더링
- 공급자(자사) ↔ 공급받는자(거래처) 박스 양분 레이아웃 (세금계산서 표준)
- 공급가액 / 부가세 / 합계 명확히 표기
- 한글 금액 표기 ("일금 OOO원정")

사용:
    from app.core.docs_pdf import render_transaction_statement
    pdf_bytes = render_transaction_statement(company, customer, shipment, items)
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ──── 폰트 등록 (모듈 import 시 1회) ─────────────────────────────────
_FONT = "HYSMyeongJo-Medium"
try:
    pdfmetrics.registerFont(UnicodeCIDFont(_FONT))
except Exception:  # already registered or font missing
    pass


# ──── 데이터 클래스 (양식별 입력 컨테이너) ─────────────────────────────
@dataclass
class PartyInfo:
    """공급자 또는 공급받는자 정보 한 묶음."""

    business_no: str | None
    company_name: str
    representative: str | None
    address: str | None
    business_type: str | None = None
    business_item: str | None = None
    phone: str | None = None
    fax: str | None = None


@dataclass
class LineItem:
    """양식 본문 한 줄."""

    no: int
    name: str  # 품목명 (규격 포함 가능)
    spec: str | None  # 규격
    qty: Decimal
    unit: str  # 단위 (EA, KG 등)
    unit_price: Decimal  # 공급단가
    supply_amount: Decimal  # 공급가액 = qty * unit_price (부가세 별도)
    tax_amount: Decimal  # 부가세 (10% 기본, 면세는 0)


# ──── 유틸 ───────────────────────────────────────────────────────────
def _fmt_money(v: Decimal | int | float | None) -> str:
    if v is None:
        return ""
    return f"{int(Decimal(str(v))):,}"


def _korean_amount(value: Decimal | int) -> str:
    """정수 금액을 한글 표기로. 예: 1500000 → '일백오십만'.

    세금계산서/거래명세표 '일금 OOO원정' 칸용. 음수/0/소수는 단순 처리.
    """
    if value is None or int(value) == 0:
        return "영"
    n = int(value)
    if n < 0:
        return "음수금액"

    digits = "영일이삼사오육칠팔구"
    units_small = ["", "십", "백", "천"]
    units_big = ["", "만", "억", "조"]
    s = str(n)
    parts: list[str] = []
    # 4자리씩 끊어 처리
    chunks: list[str] = []
    while s:
        chunks.append(s[-4:])
        s = s[:-4]

    for big_idx, chunk in enumerate(chunks):
        piece = ""
        for i, ch in enumerate(chunk[::-1]):
            d = int(ch)
            if d == 0:
                continue
            small = units_small[i]
            # '일십' → '십', '일백' → '백' 생략 (관용)
            if d == 1 and small:
                piece = small + piece
            else:
                piece = digits[d] + small + piece
        if piece:
            piece += units_big[big_idx]
        parts.insert(0, piece)
    return "".join(parts) or "영"


def _para(text: str, size: int = 9, bold: bool = False, align: str = "LEFT") -> Paragraph:
    style = ParagraphStyle(
        "kr",
        fontName=_FONT,
        fontSize=size,
        leading=size * 1.3,
        alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}[align],
    )
    if bold:
        # CID 폰트는 굵게가 안되므로 ▮ 시각적 강조 대신 단순 표시
        text = f"<b>{text}</b>"
    return Paragraph(text, style)


# ──── 공통 헤더 ──────────────────────────────────────────────────────
def _doc_header(title: str, doc_no: str, doc_date: date) -> list:
    """모든 양식 상단의 큰 제목 + 우측 문서번호/일자 박스."""
    title_p = _para(title, size=24, align="CENTER")
    meta = Table(
        [
            [_para("문서번호", size=8, align="CENTER"), _para(doc_no, size=9)],
            [
                _para("발행일자", size=8, align="CENTER"),
                _para(doc_date.strftime("%Y년 %m월 %d일"), size=9),
            ],
        ],
        colWidths=[20 * mm, 50 * mm],
    )
    meta.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return [title_p, Spacer(1, 6 * mm), meta, Spacer(1, 4 * mm)]


# ──── 공급자 / 공급받는자 양분 박스 (세금계산서 표준) ─────────────────
def _parties_block(supplier: PartyInfo, buyer: PartyInfo) -> Table:
    """국세청 세금계산서 양식의 표준 2단 박스.

    행: [라벨, 공급자 값, 라벨, 공급받는자 값]
    """

    def cell(label: str, value: str | None) -> list[Paragraph]:
        return [_para(label, size=8, align="CENTER"), _para(value or "-", size=9)]

    rows = [
        [
            _para("공\n급\n자", size=10, align="CENTER"),
            _para("등록번호", size=8, align="CENTER"),
            _para(supplier.business_no or "-", size=9),
            _para("공\n급\n받\n는\n자", size=10, align="CENTER"),
            _para("등록번호", size=8, align="CENTER"),
            _para(buyer.business_no or "-", size=9),
        ],
        [
            "",
            _para("상호", size=8, align="CENTER"),
            _para(supplier.company_name, size=9),
            "",
            _para("상호", size=8, align="CENTER"),
            _para(buyer.company_name, size=9),
        ],
        [
            "",
            _para("대표자", size=8, align="CENTER"),
            _para(supplier.representative or "-", size=9),
            "",
            _para("대표자", size=8, align="CENTER"),
            _para(buyer.representative or "-", size=9),
        ],
        [
            "",
            _para("주소", size=8, align="CENTER"),
            _para(supplier.address or "-", size=9),
            "",
            _para("주소", size=8, align="CENTER"),
            _para(buyer.address or "-", size=9),
        ],
        [
            "",
            _para("업태", size=8, align="CENTER"),
            _para(supplier.business_type or "-", size=9),
            "",
            _para("업태", size=8, align="CENTER"),
            _para(buyer.business_type or "-", size=9),
        ],
        [
            "",
            _para("종목", size=8, align="CENTER"),
            _para(supplier.business_item or "-", size=9),
            "",
            _para("종목", size=8, align="CENTER"),
            _para(buyer.business_item or "-", size=9),
        ],
    ]
    t = Table(
        rows,
        colWidths=[8 * mm, 18 * mm, 64 * mm, 8 * mm, 18 * mm, 64 * mm],
    )
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("SPAN", (0, 0), (0, -1)),  # 공급자 세로 병합
                ("SPAN", (3, 0), (3, -1)),  # 공급받는자 세로 병합
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2e0")),
                ("BACKGROUND", (3, 0), (3, -1), colors.HexColor("#fef3c7")),
                ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#f8fafc")),
                ("BACKGROUND", (4, 0), (4, -1), colors.HexColor("#f8fafc")),
            ]
        )
    )
    return t


# ──── 본문 라인 테이블 ────────────────────────────────────────────────
def _line_table(items: Sequence[LineItem], show_tax: bool = True) -> Table:
    """품목 라인 테이블. show_tax=False면 부가세 컬럼 숨김 (인수증 등)."""
    if show_tax:
        headers = ["No", "품목", "규격", "수량", "단위", "단가", "공급가액", "세액"]
        col_widths = [
            10 * mm,
            48 * mm,
            22 * mm,
            16 * mm,
            14 * mm,
            22 * mm,
            28 * mm,
            22 * mm,
        ]
    else:
        headers = ["No", "품목", "규격", "수량", "단위", "단가", "금액"]
        col_widths = [
            10 * mm,
            56 * mm,
            26 * mm,
            18 * mm,
            16 * mm,
            26 * mm,
            30 * mm,
        ]

    data = [[_para(h, size=9, align="CENTER") for h in headers]]
    sum_supply = Decimal(0)
    sum_tax = Decimal(0)
    for it in items:
        if show_tax:
            row = [
                _para(str(it.no), size=9, align="CENTER"),
                _para(it.name, size=9),
                _para(it.spec or "-", size=9, align="CENTER"),
                _para(_fmt_money(it.qty), size=9, align="RIGHT"),
                _para(it.unit, size=9, align="CENTER"),
                _para(_fmt_money(it.unit_price), size=9, align="RIGHT"),
                _para(_fmt_money(it.supply_amount), size=9, align="RIGHT"),
                _para(_fmt_money(it.tax_amount), size=9, align="RIGHT"),
            ]
        else:
            row = [
                _para(str(it.no), size=9, align="CENTER"),
                _para(it.name, size=9),
                _para(it.spec or "-", size=9, align="CENTER"),
                _para(_fmt_money(it.qty), size=9, align="RIGHT"),
                _para(it.unit, size=9, align="CENTER"),
                _para(_fmt_money(it.unit_price), size=9, align="RIGHT"),
                _para(_fmt_money(it.supply_amount + it.tax_amount), size=9, align="RIGHT"),
            ]
        data.append(row)
        sum_supply += Decimal(it.supply_amount)
        sum_tax += Decimal(it.tax_amount)

    # 합계 행
    if show_tax:
        total_row = [
            "",
            _para("합  계", size=10, align="CENTER"),
            "",
            "",
            "",
            "",
            _para(_fmt_money(sum_supply), size=10, align="RIGHT"),
            _para(_fmt_money(sum_tax), size=10, align="RIGHT"),
        ]
    else:
        total_row = [
            "",
            _para("합  계", size=10, align="CENTER"),
            "",
            "",
            "",
            "",
            _para(_fmt_money(sum_supply + sum_tax), size=10, align="RIGHT"),
        ]
    data.append(total_row)

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff7ed")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                # 본문 zebra (헤더, 합계 제외)
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -2),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
            ]
        )
    )
    return t


# ──── 합계 / 한글금액 박스 ────────────────────────────────────────────
def _totals_box(
    supply: Decimal, tax: Decimal, total: Decimal | None = None
) -> Table:
    if total is None:
        total = supply + tax
    rows = [
        [
            _para("공급가액", size=9, align="CENTER"),
            _para(_fmt_money(supply), size=10, align="RIGHT"),
            _para("세  액", size=9, align="CENTER"),
            _para(_fmt_money(tax), size=10, align="RIGHT"),
            _para("합  계", size=9, align="CENTER"),
            _para(_fmt_money(total), size=11, align="RIGHT"),
        ],
        [
            _para("일금", size=9, align="CENTER"),
            "",
            _para(f"{_korean_amount(total)}원정", size=10, align="LEFT"),
            "",
            "",
            "",
        ],
    ]
    t = Table(
        rows,
        colWidths=[18 * mm, 30 * mm, 18 * mm, 30 * mm, 18 * mm, 38 * mm],
    )
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("SPAN", (1, 1), (5, 1)),  # 한글금액 행 병합
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f1f5f9")),
                ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#f1f5f9")),
                ("BACKGROUND", (4, 0), (4, 0), colors.HexColor("#fff7ed")),
                ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#f1f5f9")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


# ──── 서명/인수 박스 ─────────────────────────────────────────────────
def _signature_block(
    left_label: str = "공급자",
    right_label: str = "공급받는자",
) -> Table:
    rows = [
        [
            _para(f"{left_label} (인)", size=10, align="CENTER"),
            _para(f"{right_label} (인)", size=10, align="CENTER"),
        ],
        [_para(" ", size=10), _para(" ", size=10)],  # 서명 공간
    ]
    t = Table(rows, colWidths=[76 * mm, 76 * mm], rowHeights=[8 * mm, 24 * mm])
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


# ──── 문서 빌더 헬퍼 ─────────────────────────────────────────────────
def _build(story: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    doc.build(story)
    return buf.getvalue()


# ════════════════════════════════════════════════════════════════════
# 양식별 진입점
# ════════════════════════════════════════════════════════════════════


def render_transaction_statement(
    company: PartyInfo,
    customer: PartyInfo,
    items: Sequence[LineItem],
    *,
    doc_no: str,
    doc_date: date,
    bank_info: str | None = None,
    remarks: str | None = None,
) -> bytes:
    """거래명세표 PDF."""
    supply = sum((Decimal(i.supply_amount) for i in items), Decimal(0))
    tax = sum((Decimal(i.tax_amount) for i in items), Decimal(0))

    story: list = []
    story += _doc_header("거 래 명 세 표", doc_no, doc_date)
    story.append(_parties_block(company, customer))
    story.append(Spacer(1, 4 * mm))
    story.append(_line_table(items, show_tax=True))
    story.append(Spacer(1, 3 * mm))
    story.append(_totals_box(supply, tax))
    if bank_info:
        story.append(Spacer(1, 3 * mm))
        story.append(_para(f"입금계좌: {bank_info}", size=9))
    if remarks:
        story.append(Spacer(1, 2 * mm))
        story.append(_para(f"비고: {remarks}", size=9))
    story.append(Spacer(1, 6 * mm))
    story.append(_signature_block())
    return _build(story)


def render_acceptance_receipt(
    company: PartyInfo,
    customer: PartyInfo,
    items: Sequence[LineItem],
    *,
    doc_no: str,
    doc_date: date,
    delivery_address: str | None = None,
) -> bytes:
    """인수증 PDF — 거래명세표 축약본 + 인수자 서명란 강조."""
    story: list = []
    story += _doc_header("인  수  증", doc_no, doc_date)
    story.append(_parties_block(company, customer))
    story.append(Spacer(1, 4 * mm))
    story.append(_line_table(items, show_tax=False))
    story.append(Spacer(1, 3 * mm))

    if delivery_address:
        story.append(_para(f"인도장소: {delivery_address}", size=10))
        story.append(Spacer(1, 2 * mm))

    story.append(
        _para(
            "위 물품을 정히 인수하였음을 확인합니다.",
            size=11,
            align="CENTER",
        )
    )
    story.append(Spacer(1, 6 * mm))
    story.append(
        _signature_block(left_label="인도자(공급자)", right_label="인수자")
    )
    return _build(story)


def render_tax_invoice(
    company: PartyInfo,
    customer: PartyInfo,
    items: Sequence[LineItem],
    *,
    doc_no: str,
    doc_date: date,
    is_exempt: bool = False,
    bank_info: str | None = None,
) -> bytes:
    """세금계산서 (국세청 양식 준용). is_exempt=True면 면세계산서."""
    supply = sum((Decimal(i.supply_amount) for i in items), Decimal(0))
    tax = sum((Decimal(i.tax_amount) for i in items), Decimal(0))

    story: list = []
    title = "면 세 계 산 서" if is_exempt else "세 금 계 산 서"
    story += _doc_header(title, doc_no, doc_date)
    story.append(_parties_block(company, customer))
    story.append(Spacer(1, 4 * mm))
    story.append(_line_table(items, show_tax=not is_exempt))
    story.append(Spacer(1, 3 * mm))
    story.append(_totals_box(supply, tax))
    if bank_info:
        story.append(Spacer(1, 3 * mm))
        story.append(_para(f"입금계좌: {bank_info}", size=9))
    story.append(Spacer(1, 6 * mm))
    story.append(_signature_block())
    return _build(story)


def render_purchase_order(
    company: PartyInfo,
    supplier: PartyInfo,
    items: Sequence[LineItem],
    *,
    doc_no: str,
    doc_date: date,
    expected_date: date | None = None,
    remarks: str | None = None,
) -> bytes:
    """발주서 PDF. 공급자=거래처(suppli er), 공급받는자=자사 (역순)."""
    supply = sum((Decimal(i.supply_amount) for i in items), Decimal(0))
    tax = sum((Decimal(i.tax_amount) for i in items), Decimal(0))

    story: list = []
    story += _doc_header("발  주  서", doc_no, doc_date)
    # 발주서는 자사(buyer)가 공급받는자, 공급처가 공급자
    story.append(_parties_block(supplier, company))
    story.append(Spacer(1, 4 * mm))

    info_rows = []
    if expected_date:
        info_rows.append(
            [
                _para("납기일자", size=9, align="CENTER"),
                _para(expected_date.strftime("%Y-%m-%d"), size=9),
            ]
        )
    if remarks:
        info_rows.append([_para("비고", size=9, align="CENTER"), _para(remarks, size=9)])
    if info_rows:
        t = Table(info_rows, colWidths=[24 * mm, 156 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), _FONT),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 3 * mm))

    story.append(_line_table(items, show_tax=True))
    story.append(Spacer(1, 3 * mm))
    story.append(_totals_box(supply, tax))
    story.append(Spacer(1, 6 * mm))
    story.append(_signature_block(left_label="발주처(공급받는자)", right_label="수주처(공급자)"))
    return _build(story)


def render_quote(
    company: PartyInfo,
    customer: PartyInfo,
    items: Sequence[LineItem],
    *,
    doc_no: str,
    doc_date: date,
    expires_date: date | None = None,
    notes: str | None = None,
) -> bytes:
    """견적서 PDF."""
    supply = sum((Decimal(i.supply_amount) for i in items), Decimal(0))
    tax = sum((Decimal(i.tax_amount) for i in items), Decimal(0))

    story: list = []
    story += _doc_header("견  적  서", doc_no, doc_date)
    story.append(_parties_block(company, customer))
    story.append(Spacer(1, 4 * mm))

    info_rows = []
    if expires_date:
        info_rows.append(
            [
                _para("유효기간", size=9, align="CENTER"),
                _para(expires_date.strftime("%Y-%m-%d 까지"), size=9),
            ]
        )
    if notes:
        info_rows.append([_para("비고", size=9, align="CENTER"), _para(notes, size=9)])
    if info_rows:
        t = Table(info_rows, colWidths=[24 * mm, 156 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), _FONT),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 3 * mm))

    story.append(_line_table(items, show_tax=True))
    story.append(Spacer(1, 3 * mm))
    story.append(_totals_box(supply, tax))
    story.append(Spacer(1, 6 * mm))
    story.append(
        _para(
            "위와 같이 견적합니다.",
            size=11,
            align="CENTER",
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(_signature_block(left_label="견적자", right_label="수신처"))
    return _build(story)


@dataclass
class LedgerRow:
    """거래원장 한 줄 — 매출/입금/잔액."""

    txn_date: date
    description: str  # 'INV-001 매출' 또는 'PAY 입금'
    debit: Decimal = Decimal(0)  # 매출 발생
    credit: Decimal = Decimal(0)  # 입금
    balance: Decimal = Decimal(0)


def render_customer_ledger(
    company: PartyInfo,
    customer: PartyInfo,
    rows: Sequence[LedgerRow],
    *,
    period_from: date,
    period_to: date,
    opening_balance: Decimal = Decimal(0),
) -> bytes:
    """거래원장 PDF — 거래처 기준 매출/입금/잔액 시계열."""
    story: list = []
    title_p = _para("거 래 원 장", size=24, align="CENTER")
    period_p = _para(
        f"기간: {period_from.strftime('%Y-%m-%d')} ~ {period_to.strftime('%Y-%m-%d')}",
        size=10,
        align="CENTER",
    )
    story += [title_p, Spacer(1, 3 * mm), period_p, Spacer(1, 5 * mm)]

    cust_rows = [
        [_para("거래처", size=9, align="CENTER"), _para(customer.company_name, size=10)],
        [_para("사업자번호", size=9, align="CENTER"), _para(customer.business_no or "-", size=10)],
        [_para("대표자", size=9, align="CENTER"), _para(customer.representative or "-", size=10)],
    ]
    ct = Table(cust_rows, colWidths=[24 * mm, 156 * mm])
    ct.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
            ]
        )
    )
    story.append(ct)
    story.append(Spacer(1, 5 * mm))

    data = [
        [
            _para(h, size=9, align="CENTER")
            for h in ["일자", "적요", "매출(차변)", "입금(대변)", "잔액"]
        ],
        [
            "",
            _para("전기이월", size=9),
            "",
            "",
            _para(_fmt_money(opening_balance), size=9, align="RIGHT"),
        ],
    ]
    total_debit = Decimal(0)
    total_credit = Decimal(0)
    for r in rows:
        total_debit += Decimal(r.debit)
        total_credit += Decimal(r.credit)
        data.append(
            [
                _para(r.txn_date.strftime("%Y-%m-%d"), size=9, align="CENTER"),
                _para(r.description, size=9),
                _para(_fmt_money(r.debit) if r.debit else "-", size=9, align="RIGHT"),
                _para(_fmt_money(r.credit) if r.credit else "-", size=9, align="RIGHT"),
                _para(_fmt_money(r.balance), size=9, align="RIGHT"),
            ]
        )
    data.append(
        [
            "",
            _para("합  계", size=10, align="CENTER"),
            _para(_fmt_money(total_debit), size=10, align="RIGHT"),
            _para(_fmt_money(total_credit), size=10, align="RIGHT"),
            _para(
                _fmt_money(opening_balance + total_debit - total_credit),
                size=10,
                align="RIGHT",
            ),
        ]
    )

    t = Table(
        data,
        colWidths=[24 * mm, 70 * mm, 28 * mm, 28 * mm, 30 * mm],
        repeatRows=1,
    )
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff7ed")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -2),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
            ]
        )
    )
    story.append(t)
    return _build(story)
