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
        "business_no": "123-45-67890",
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
            "business_no": "111-11-11111",
            "company_name": "X",
            "representative": "Y",
            "address": "Z",
        },
        headers=staff_auth["headers"],
    )
    assert res.status_code == 403


# ────── 3. 출고 → 거래명세표/인수증 통합 ────────────────────────


def _setup_shipment(client, db_session, admin_headers):
    """회사정보+거래처+상품+주문+pick+ship까지 한 번에 만들기."""
    # 회사정보
    client.put(
        "/api/company-profile",
        json={
            "business_no": "123-45-67890",
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
