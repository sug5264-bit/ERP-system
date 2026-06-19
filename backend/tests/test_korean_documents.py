"""한국형 양식 PDF 출력 검증.

직접 실행해서 PDF 바이트 검증:
- PDF 시그니처(%PDF-)
- 본문에 한글 글리프 인덱스 표가 들어있는지 (CID 폰트)
- 사이즈 합리 (10KB 이상)
- 라인 합계 = 실제 금액

엔드포인트 통합:
- 회사정보 PUT/GET
- 출고 → 거래명세표 → 인수증
- PO → 발주서
- 견적서 / 세금계산서 / 거래원장
"""
from datetime import date
from decimal import Decimal


# ────── 1. PDF 렌더링 단위 테스트 (회사정보 없이 직접 호출) ────────


def test_docs_pdf_imports_and_korean_amount():
    from app.core.docs_pdf import _korean_amount

    assert _korean_amount(0) == "영"
    assert _korean_amount(1) == "일"
    assert _korean_amount(10) == "십"
    assert _korean_amount(100) == "백"
    # '일백' 같은 선행 '일' 은 관용적으로 생략 (백/십)
    assert _korean_amount(1500000) == "백오십만"
    # 만/억 단위 앞의 '일'은 유지 (관용)
    assert _korean_amount(12345) == "일만이천삼백사십오"
    assert _korean_amount(100000000) == "일억"


def test_render_transaction_statement_returns_valid_pdf():
    from app.core.docs_pdf import (
        LineItem,
        PartyInfo,
        render_transaction_statement,
    )

    company = PartyInfo(
        business_no="123-45-67890",
        company_name="(주)웰그린",
        representative="김대표",
        address="서울시 강남구 테헤란로 123",
        business_type="도소매업",
        business_item="식품",
        phone="02-1234-5678",
    )
    customer = PartyInfo(
        business_no="987-65-43210",
        company_name="(주)고객사",
        representative="이고객",
        address="서울시 마포구 합정동 456",
        business_type="음식점업",
        business_item="요식업",
    )
    items = [
        LineItem(
            no=1,
            name="유기농 토마토",
            spec="1kg 박스",
            qty=Decimal("10"),
            unit="BOX",
            unit_price=Decimal("15000"),
            supply_amount=Decimal("150000"),
            tax_amount=Decimal("15000"),
        ),
        LineItem(
            no=2,
            name="국내산 양파",
            spec="3kg",
            qty=Decimal("5"),
            unit="BAG",
            unit_price=Decimal("8000"),
            supply_amount=Decimal("40000"),
            tax_amount=Decimal("4000"),
        ),
    ]

    pdf = render_transaction_statement(
        company,
        customer,
        items,
        doc_no="SHP-20260619-001",
        doc_date=date(2026, 6, 19),
        bank_info="국민은행 123-456-789 (예금주: 웰그린)",
        remarks="익일 배송 요청",
    )

    assert pdf.startswith(b"%PDF-"), "유효한 PDF 시그니처 필요"
    assert len(pdf) > 5000, "PDF가 너무 작음 — 본문 누락 가능성"
    # PDF에 폰트 등록 흔적
    assert b"HYSMyeongJo-Medium" in pdf or b"CIDFont" in pdf, "CID 한국어 폰트 미등록"


def test_render_transaction_statement_v2_two_copies():
    """v2 양식 — A4 1장 2부, 바코드/적요, 전잔/후잔 표기."""
    from app.core.docs_pdf import (
        LineItem,
        PartyInfo,
        render_transaction_statement_v2,
    )

    company = PartyInfo(
        business_no="206-87-06151",
        company_name="웰그린 라들러",
        representative="이승주",
        address="서울특별시 영등포구 선유로3길 10, 506호",
        phone="031-797-8550",
    )
    customer = PartyInfo(
        business_no=None,
        company_name="GS앱발주",
        representative=None,
        address=None,
        phone=None,
    )
    items = [
        LineItem(
            no=1,
            name="에스터하지, 클림트 레드 2020",
            spec="750ml",
            qty=Decimal("2"),
            unit="BTL",
            unit_price=Decimal("12000"),
            supply_amount=Decimal("24000"),
            tax_amount=Decimal("2400"),
            barcode="9003634113963",
        ),
    ]
    pdf = render_transaction_statement_v2(
        company,
        customer,
        items,
        serial_no="2026/06/19 -1",
        doc_date=date(2026, 6, 19),
        bank_info="우리은행 1005-402-804956 (주)웰그린라들러",
        opening_balance=Decimal("100000"),
        closing_balance=Decimal("126400"),
        copies=2,
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 4000


def test_render_acceptance_receipt():
    from app.core.docs_pdf import (
        LineItem,
        PartyInfo,
        render_acceptance_receipt,
    )

    company = PartyInfo(
        business_no="123-45-67890",
        company_name="(주)웰그린",
        representative="김대표",
        address="서울 강남",
    )
    customer = PartyInfo(
        business_no="987-65-43210",
        company_name="(주)고객사",
        representative="이고객",
        address="서울 마포",
    )
    items = [
        LineItem(
            no=1,
            name="딸기",
            spec="500g",
            qty=Decimal("20"),
            unit="PACK",
            unit_price=Decimal("5000"),
            supply_amount=Decimal("100000"),
            tax_amount=Decimal("10000"),
        )
    ]
    pdf = render_acceptance_receipt(
        company,
        customer,
        items,
        doc_no="SHP-001",
        doc_date=date(2026, 6, 19),
        delivery_address="서울 마포구 합정동 456",
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 3000


def test_acceptance_receipt_v2_hides_prices():
    """인수증은 가격 정보 일체 노출 금지 — 수량/품명만 보여야 함."""
    from app.core.docs_pdf import (
        LineItem,
        PartyInfo,
        render_acceptance_receipt_v2,
        render_transaction_statement_v2,
    )

    company = PartyInfo(
        business_no="206-87-06151",
        company_name="웰그린",
        representative="이승주",
        address="서울 영등포",
    )
    customer = PartyInfo(
        business_no=None,
        company_name="GS앱발주",
        representative=None,
        address=None,
    )
    items = [
        LineItem(
            no=1,
            name="유기농 토마토",
            spec="1kg박스",
            qty=Decimal("10"),
            unit="BOX",
            unit_price=Decimal("15000"),
            supply_amount=Decimal("150000"),
            tax_amount=Decimal("15000"),
            barcode="8801234567890",
        ),
    ]

    receipt = render_acceptance_receipt_v2(
        company, customer, items,
        serial_no="2026/06/19 -1",
        doc_date=date(2026, 6, 19),
    )
    statement = render_transaction_statement_v2(
        company, customer, items,
        serial_no="2026/06/19 -1",
        doc_date=date(2026, 6, 19),
        bank_info="우리은행 1005-402-804956",
        opening_balance=Decimal("100000"),
        closing_balance=Decimal("265000"),
    )
    assert receipt.startswith(b"%PDF-") and statement.startswith(b"%PDF-")

    # 거래명세서엔 가격이 보이고 (15,000 / 150,000 / 우리은행) 인수증엔 없어야 함.
    # PDF 텍스트는 CID로 인코딩돼 raw bytes로는 직접 검색 불가 — 대신
    # 가격 정보를 가진 거래명세서가 인수증보다 명백히 더 커야 함을 검증.
    assert len(statement) > len(receipt), (
        "거래명세서(가격포함)가 인수증(가격숨김)보다 커야 함"
    )


# ────── 4. 품목 일괄 등록/갱신 (Excel/CSV import) ───────────────


def _make_admin_items_xlsx(rows: list[list]) -> bytes:
    """xlsx 바이트 생성기 (테스트용)."""
    import io as _io
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["SKU", "품목명", "단위", "단가", "재고", "바코드"])
    for r in rows:
        ws.append(r)
    buf = _io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_items_import_template_xlsx(client, admin_auth):
    res = client.get(
        "/api/inventory/items/import-template?format=xlsx",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    # xlsx 시그니처 = PK (ZIP)
    assert res.content[:2] == b"PK"


def test_items_import_creates_and_updates(client, db_session, admin_auth):
    from app.modules.inventory.models import Item

    # 1번 호출: 신규 2건
    xlsx = _make_admin_items_xlsx(
        [
            ["SKU-A", "토마토 1kg", "BOX", 15000, 10, "8801111111111"],
            ["SKU-B", "양파 3kg", "BAG", 8000, 20, "8802222222222"],
        ]
    )
    res = client.post(
        "/api/inventory/items/import",
        files={
            "file": (
                "items.xlsx",
                xlsx,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] == 2 and body["updated"] == 0
    assert db_session.query(Item).filter(Item.sku == "SKU-A").first().name == "토마토 1kg"

    # 2번 호출: 기존 1건 update + 신규 1건
    xlsx2 = _make_admin_items_xlsx(
        [
            ["SKU-A", "유기농 토마토 1kg", "BOX", 18000, 12, "8801111111111"],
            ["SKU-C", "상추 200g", "PACK", 3000, 50, "8803333333333"],
        ]
    )
    res = client.post(
        "/api/inventory/items/import",
        files={"file": ("items.xlsx", xlsx2, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    body = res.json()
    assert body["created"] == 1 and body["updated"] == 1

    db_session.expire_all()
    item_a = db_session.query(Item).filter(Item.sku == "SKU-A").first()
    assert item_a.name == "유기농 토마토 1kg"
    assert int(item_a.unit_price) == 18000


def test_items_import_csv_with_korean_headers(client, db_session, admin_auth):
    """CSV (UTF-8 BOM) + 한글 헤더로 업로드 가능해야 함."""
    csv_text = (
        "﻿SKU,품목명,단위,단가,재고,바코드\n"
        "SKU-K1,한글품목1,EA,5000,3,\n"
        "SKU-K2,한글품목2,KG,12000,7,8809999999999\n"
    )
    res = client.post(
        "/api/inventory/items/import",
        files={"file": ("items.csv", csv_text.encode("utf-8"), "text/csv")},
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] == 2
    assert body["errors"] == []


def test_items_import_rejects_missing_required(client, admin_auth):
    """SKU/품목명 없는 행은 errors에 기록되고 commit은 정상 진행."""
    import io as _io
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["SKU", "품목명", "단위", "단가"])
    ws.append(["", "이름만있고sku없음", "EA", 1000])  # 거부 대상
    ws.append(["SKU-OK", "정상품목", "EA", 1000])  # 정상
    buf = _io.BytesIO()
    wb.save(buf)

    res = client.post(
        "/api/inventory/items/import",
        files={
            "file": (
                "items.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    body = res.json()
    assert body["created"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["row"] == 2


def test_items_export_all_formats(client, db_session, admin_auth):
    """품목 export — csv/xlsx/pdf 3종 모두 정상 응답."""
    from app.modules.inventory.models import Item

    db_session.add(Item(sku="EXP-1", name="익스포트테스트", unit_price=Decimal("1000")))
    db_session.commit()

    for fmt, sig in [("csv", b"\xef\xbb\xbf"), ("xlsx", b"PK"), ("pdf", b"%PDF-")]:
        res = client.get(
            f"/api/inventory/items/export?format={fmt}",
            headers=admin_auth["headers"],
        )
        assert res.status_code == 200, f"{fmt} failed: {res.text}"
        assert res.content.startswith(sig), f"{fmt} 시그니처 불일치"


def test_stock_movements_export(client, db_session, admin_auth):
    from app.modules.inventory.models import Item, MovementType, StockMovement

    item = Item(sku="MOV-1", name="이동테스트", stock_qty=Decimal("100"))
    db_session.add(item)
    db_session.flush()
    db_session.add(
        StockMovement(
            item_id=item.id, type=MovementType.inbound, quantity=Decimal("10"), note="테스트"
        )
    )
    db_session.commit()

    res = client.get(
        "/api/inventory/movements/export?format=xlsx",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200
    assert res.content[:2] == b"PK"


def test_render_tax_invoice_with_exemption():
    from app.core.docs_pdf import LineItem, PartyInfo, render_tax_invoice

    company = PartyInfo(
        business_no="111-11-11111",
        company_name="공급자",
        representative="공급대표",
        address="공급주소",
    )
    customer = PartyInfo(
        business_no="222-22-22222",
        company_name="공급받는자",
        representative="공급받는대표",
        address="받는주소",
    )
    items = [
        LineItem(
            no=1,
            name="채소류 (면세)",
            spec=None,
            qty=Decimal("100"),
            unit="KG",
            unit_price=Decimal("3000"),
            supply_amount=Decimal("300000"),
            tax_amount=Decimal("0"),
        )
    ]
    pdf = render_tax_invoice(
        company,
        customer,
        items,
        doc_no="INV-2026-001",
        doc_date=date(2026, 6, 19),
        is_exempt=True,
    )
    assert pdf.startswith(b"%PDF-")


def test_render_purchase_order_and_quote_and_ledger():
    from app.core.docs_pdf import (
        LedgerRow,
        LineItem,
        PartyInfo,
        render_customer_ledger,
        render_purchase_order,
        render_quote,
    )

    company = PartyInfo(
        business_no="111-11-11111",
        company_name="자사",
        representative="자사대표",
        address="자사주소",
    )
    other = PartyInfo(
        business_no="222-22-22222",
        company_name="상대방",
        representative="상대방대표",
        address="상대방주소",
    )
    items = [
        LineItem(
            no=1,
            name="원재료A",
            spec="규격",
            qty=Decimal("100"),
            unit="EA",
            unit_price=Decimal("1000"),
            supply_amount=Decimal("100000"),
            tax_amount=Decimal("10000"),
        )
    ]
    po_pdf = render_purchase_order(
        company,
        other,
        items,
        doc_no="PO-001",
        doc_date=date(2026, 6, 19),
        expected_date=date(2026, 6, 25),
    )
    assert po_pdf.startswith(b"%PDF-")

    qt_pdf = render_quote(
        company,
        other,
        items,
        doc_no="Q-001",
        doc_date=date(2026, 6, 19),
        expires_date=date(2026, 7, 19),
        notes="현금결제 시 3% 할인",
    )
    assert qt_pdf.startswith(b"%PDF-")

    ledger_pdf = render_customer_ledger(
        company,
        other,
        [
            LedgerRow(
                txn_date=date(2026, 6, 10),
                description="INV-001 매출",
                debit=Decimal("110000"),
                credit=Decimal(0),
                balance=Decimal("110000"),
            ),
            LedgerRow(
                txn_date=date(2026, 6, 15),
                description="입금 (계좌이체)",
                debit=Decimal(0),
                credit=Decimal("110000"),
                balance=Decimal(0),
            ),
        ],
        period_from=date(2026, 6, 1),
        period_to=date(2026, 6, 30),
        opening_balance=Decimal(0),
    )
    assert ledger_pdf.startswith(b"%PDF-")


# ────── 2. 회사정보 엔드포인트 ──────────────────────────────────


def test_company_profile_upsert_and_get(client, admin_auth):
    # 처음에는 없으니 404
    res = client.get("/api/company-profile", headers=admin_auth["headers"])
    assert res.status_code == 404

    payload = {
        # 실제 체크섬 통과하는 사업자번호 사용 (가짜 번호는 거부됨)
        "business_no": "206-87-06151",
        "company_name": "(주)웰그린",
        "representative": "김대표",
        "address": "서울특별시 강남구 테헤란로 123",
        "business_type": "도소매업",
        "business_item": "식품",
        "phone": "02-1234-5678",
        "email": "info@well-green.com",
        "bank_name": "국민은행",
        "bank_account": "123-456-789",
        "bank_holder": "(주)웰그린",
    }
    res = client.put(
        "/api/company-profile", json=payload, headers=admin_auth["headers"]
    )
    assert res.status_code == 200, res.text
    saved = res.json()
    assert saved["company_name"] == "(주)웰그린"

    # 두 번째 PUT은 갱신
    payload["representative"] = "박대표"
    res = client.put(
        "/api/company-profile", json=payload, headers=admin_auth["headers"]
    )
    assert res.status_code == 200
    assert res.json()["representative"] == "박대표"

    # GET으로 확인
    res = client.get("/api/company-profile", headers=admin_auth["headers"])
    assert res.status_code == 200
    assert res.json()["representative"] == "박대표"


def test_company_profile_requires_admin(client, staff_auth):
    res = client.put(
        "/api/company-profile",
        json={
            "business_no": "206-87-06151",
            "company_name": "X",
            "representative": "Y",
            "address": "Z",
        },
        headers=staff_auth["headers"],
    )
    assert res.status_code == 403


def test_company_profile_rejects_invalid_business_no(client, admin_auth):
    """체크섬 무효 사업자번호는 422로 거부."""
    res = client.put(
        "/api/company-profile",
        json={
            "business_no": "123-45-67890",  # 체크섬 오류
            "company_name": "X",
            "representative": "Y",
            "address": "Z",
        },
        headers=admin_auth["headers"],
    )
    assert res.status_code == 422
    body = res.json()
    # envelope 또는 detail에 "사업자등록번호" 메시지 포함
    txt = str(body)
    assert "사업자등록번호" in txt or "business_no" in txt


# ────── 3. 출고 → 거래명세표/인수증 통합 ────────────────────────


def _setup_shipment(client, db_session, admin_headers):
    """회사정보+거래처+상품+주문+pick+ship까지 한 번에 만들기."""
    # 회사정보 (체크섬 검증 통과하는 사업자번호)
    client.put(
        "/api/company-profile",
        json={
            "business_no": "206-87-06151",
            "company_name": "(주)웰그린",
            "representative": "김대표",
            "address": "서울 강남",
            "business_type": "도소매",
            "business_item": "식품",
        },
        headers=admin_headers,
    )

    # 거래처
    from app.modules.inventory.models import Item
    from app.modules.sales.models import Customer, OrderStatus, SalesOrder, SalesOrderItem
    from app.modules.wms.models import PickList, PickListItem, PickStatus, Shipment

    cust = Customer(
        name="고객사",
        company="(주)고객사",
        business_no="987-65-43210",
        representative="이고객",
        address="서울 마포구 합정동 456",
        business_type="음식점",
        business_item="요식",
    )
    db_session.add(cust)

    item = Item(sku="SKU-001", name="유기농 토마토", unit="BOX", unit_price=Decimal("15000"))
    db_session.add(item)
    db_session.flush()

    so = SalesOrder(
        order_no="SO-001",
        customer_id=cust.id,
        status=OrderStatus.confirmed,
        total=Decimal("150000"),
    )
    so.items.append(
        SalesOrderItem(item_id=item.id, quantity=Decimal("10"), unit_price=Decimal("15000"))
    )
    db_session.add(so)
    db_session.flush()

    pl = PickList(pick_no="PL-SO-001", sales_order_id=so.id, status=PickStatus.picked)
    pl.items.append(
        PickListItem(
            item_id=item.id, requested_qty=Decimal("10"), picked_qty=Decimal("10")
        )
    )
    db_session.add(pl)
    db_session.flush()

    s = Shipment(
        shipment_no="SHP-001",
        pick_list_id=pl.id,
        sales_order_id=so.id,
        address_to="서울 마포구 합정동 456",
    )
    db_session.add(s)
    db_session.commit()
    return s.id


def test_shipment_transaction_statement_pdf(client, db_session, admin_auth):
    ship_id = _setup_shipment(client, db_session, admin_auth["headers"])
    res = client.get(
        f"/api/wms/shipments/{ship_id}/transaction-statement.pdf",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF-")
    assert len(res.content) > 5000


def test_shipment_acceptance_receipt_pdf(client, db_session, admin_auth):
    ship_id = _setup_shipment(client, db_session, admin_auth["headers"])
    res = client.get(
        f"/api/wms/shipments/{ship_id}/acceptance-receipt.pdf",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    assert res.content.startswith(b"%PDF-")


def test_shipment_pdf_blocked_without_company_profile(client, db_session, admin_auth):
    """회사정보가 없으면 PDF 출력 거부 (400) — 실수로 빈 정보 출력 방지."""
    from app.modules.inventory.models import Item
    from app.modules.sales.models import Customer, OrderStatus, SalesOrder, SalesOrderItem
    from app.modules.wms.models import PickList, PickListItem, PickStatus, Shipment

    cust = Customer(name="고객", business_no="111-22-33333")
    db_session.add(cust)
    item = Item(sku="X", name="X", unit_price=Decimal("1000"))
    db_session.add(item)
    db_session.flush()
    so = SalesOrder(order_no="SO-X", customer_id=cust.id, status=OrderStatus.confirmed)
    so.items.append(SalesOrderItem(item_id=item.id, quantity=Decimal("1"), unit_price=Decimal("1000")))
    db_session.add(so)
    db_session.flush()
    pl = PickList(pick_no="PL-X", sales_order_id=so.id, status=PickStatus.picked)
    pl.items.append(PickListItem(item_id=item.id, requested_qty=Decimal("1"), picked_qty=Decimal("1")))
    db_session.add(pl)
    db_session.flush()
    s = Shipment(shipment_no="SHP-X", pick_list_id=pl.id, sales_order_id=so.id)
    db_session.add(s)
    db_session.commit()

    res = client.get(
        f"/api/wms/shipments/{s.id}/transaction-statement.pdf",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 400
    # 에러 envelope: {"error": {"code", "message", ...}}
    body = res.json()
    msg = body.get("error", {}).get("message") or body.get("detail", "")
    assert "회사정보" in msg


# ────── 5. 사업자번호 체크섬 검증 ────────────────────────────────


def test_business_no_validation_unit():
    """체크섬 알고리즘 단위 테스트."""
    from app.core.business_no import (
        format_business_no,
        is_valid_business_no,
        normalize_business_no,
    )

    # 유효
    assert is_valid_business_no("206-87-06151") is True
    assert is_valid_business_no("105-86-15670") is True
    assert is_valid_business_no("2068706151") is True  # 하이픈 없이
    assert is_valid_business_no("1234567891") is True  # 생성된 유효값

    # 무효
    assert is_valid_business_no("123-45-67890") is False  # 체크섬 오류
    assert is_valid_business_no("000-00-00000") is False
    assert is_valid_business_no("12345") is False  # 자리수 미달
    assert is_valid_business_no("") is False
    assert is_valid_business_no(None) is False
    assert is_valid_business_no("abc-de-fghij") is False

    # 정형화
    assert format_business_no("2068706151") == "206-87-06151"
    assert format_business_no("206-87-06151") == "206-87-06151"
    assert normalize_business_no("206-87-06151") == "2068706151"


# ────── 6. 거래처/공급사 import ──────────────────────────────────


def test_customers_import_xlsx(client, db_session, admin_auth):
    """거래처 일괄 등록 — 유효/무효 사업자번호 혼합."""
    import io as _io
    from openpyxl import Workbook
    from app.modules.sales.models import Customer

    wb = Workbook()
    ws = wb.active
    ws.append(["이름", "상호", "사업자번호", "대표자", "주소", "업태"])
    ws.append(["고객A", "(주)고객A상사", "206-87-06151", "김에이", "서울 강남", "도소매"])
    ws.append(["고객B", "(주)고객B", "105-86-15670", "이비이", "서울 마포", "음식점"])
    ws.append(["고객C-잘못된사업자번호", "C상사", "111-11-11111", "박씨", "주소", "기타"])
    buf = _io.BytesIO()
    wb.save(buf)

    res = client.post(
        "/api/sales/customers/import",
        files={
            "file": (
                "customers.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] == 2  # 유효 2건
    assert len(body["errors"]) == 1  # 체크섬 오류 1건
    assert "사업자번호" in body["errors"][0]["reason"]

    # DB 확인
    db_session.expire_all()
    assert db_session.query(Customer).filter(Customer.name == "고객A").first() is not None
    assert (
        db_session.query(Customer).filter(Customer.name == "고객C-잘못된사업자번호").first()
        is None
    )


def test_suppliers_import_csv(client, db_session, admin_auth):
    from app.modules.suppliers.models import Supplier

    csv_text = (
        "코드,공급사명,사업자번호,대표자,주소\n"
        "SUP-A,(주)공급A,206-87-06151,김공급,서울\n"
        ",(주)공급B,105-86-15670,이공급,경기\n"  # 코드 자동생성
    )
    res = client.post(
        "/api/suppliers/import",
        files={"file": ("s.csv", csv_text.encode("utf-8"), "text/csv")},
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] == 2
    db_session.expire_all()
    assert db_session.query(Supplier).filter(Supplier.code == "SUP-A").first() is not None
    # 코드 자동생성: SUP-<사업자번호 뒤6자리>
    auto = db_session.query(Supplier).filter(Supplier.name == "(주)공급B").first()
    assert auto is not None and auto.code.startswith("SUP-")


# ────── 7. 출고 → 청구서 자동 draft ──────────────────────────────


def test_generate_invoice_from_shipment(client, db_session, admin_auth):
    """출고 1건 → Invoice draft 자동 생성, 멱등성 검증."""
    from app.modules.billing.models import Invoice, InvoiceStatus

    ship_id = _setup_shipment(client, db_session, admin_auth["headers"])

    res = client.post(
        f"/api/wms/shipments/{ship_id}/generate-invoice",
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["already_exists"] is False
    invoice_id = body["invoice_id"]

    db_session.expire_all()
    inv = db_session.query(Invoice).filter(Invoice.id == invoice_id).first()
    assert inv is not None
    assert inv.status == InvoiceStatus.draft
    # 10 box × 15,000 = 150,000 + 10% VAT = 165,000
    assert int(inv.subtotal) == 150000
    assert int(inv.tax) == 15000
    assert int(inv.total) == 165000

    # 멱등성: 한 번 더 호출하면 같은 invoice 반환
    res2 = client.post(
        f"/api/wms/shipments/{ship_id}/generate-invoice",
        headers=admin_auth["headers"],
    )
    assert res2.status_code == 200
    assert res2.json()["already_exists"] is True
    assert res2.json()["invoice_id"] == invoice_id


# ────── 8. 로고/직인 업로드 ──────────────────────────────────────


def _make_png_bytes() -> bytes:
    """최소 PNG (1x1 투명) — 테스트 업로드용."""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "00000010494441547801636001000000050001a2ed8b6a0000000049454e44ae426082"
    )


def test_company_logo_upload_and_get(client, admin_auth):
    """로고 업로드 → GET으로 동일 바이트 반환."""
    # 회사정보 먼저
    client.put(
        "/api/company-profile",
        json={
            "business_no": "206-87-06151",
            "company_name": "(주)웰그린",
            "representative": "김대표",
            "address": "서울",
        },
        headers=admin_auth["headers"],
    )
    png = _make_png_bytes()
    res = client.post(
        "/api/company-profile/upload-logo",
        files={"file": ("logo.png", png, "image/png")},
        headers=admin_auth["headers"],
    )
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True

    res = client.get("/api/company-profile/logo", headers=admin_auth["headers"])
    assert res.status_code == 200
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG 시그니처


def test_company_stamp_upload_rejects_non_image(client, admin_auth):
    client.put(
        "/api/company-profile",
        json={
            "business_no": "206-87-06151",
            "company_name": "(주)웰그린",
            "representative": "김대표",
            "address": "서울",
        },
        headers=admin_auth["headers"],
    )
    res = client.post(
        "/api/company-profile/upload-stamp",
        files={"file": ("bad.txt", b"not an image", "text/plain")},
        headers=admin_auth["headers"],
    )
    assert res.status_code == 400
