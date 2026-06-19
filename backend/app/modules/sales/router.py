from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session, selectinload

from app.core.auth import (
    get_current_internal_user,
    get_current_user,
    require_module_role,
    require_role,
)
from app.core.db import get_db
from app.core.exports import export_table
from app.core.pagination import Page, PageParams, paginate
from app.core.rls import can_access, scope_to_owner
from app.modules.auth.models import User
from app.modules.sales import service
from app.modules.sales.models import Customer, SalesOrder
from app.modules.sales.schemas import (
    CustomerCreate,
    CustomerOut,
    SalesOrderCreate,
    SalesOrderOut,
)
from app.modules.tenants.router import get_current_tenant_id

router = APIRouter(
    prefix="/api/sales",
    tags=["sales"],
    dependencies=[Depends(get_current_internal_user)],
)


def _scoped_filter(user: User, tenant_id: int | None):
    """Apply both owner-RLS and tenant scoping to a query."""
    def apply(q, m):
        q = scope_to_owner(q, m, user, "sales")
        if tenant_id is not None:
            q = q.filter(m.tenant_id == tenant_id)
        return q
    return apply


@router.get("/customers", response_model=Page[CustomerOut])
def list_customers(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    q = _scoped_filter(user, tenant_id)(db.query(Customer), Customer).order_by(Customer.name)
    return paginate(q, params)


@router.post(
    "/customers",
    response_model=CustomerOut,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    return service.create_customer(db, payload, owner_id=user.id, tenant_id=tenant_id)


# ---- Customers import / export ---------------------------------------------


@router.get("/customers/export")
def export_customers(
    format: str = Query("csv"),
    inline: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """거래처 리스트 다운로드 — csv/xlsx/pdf."""
    q = scope_to_owner(db.query(Customer), Customer, user, "sales")
    rows_data = q.order_by(Customer.name).all()
    headers = [
        "이름", "상호", "사업자번호", "대표자", "주소", "업태", "종목",
        "전화", "팩스", "이메일", "담당자", "은행", "계좌"
    ]
    rows = [
        [
            c.name, c.company or "", c.business_no or "", c.representative or "",
            c.address or "", c.business_type or "", c.business_item or "",
            c.phone or "", c.fax or "", c.email or "", c.contact_person or "",
            c.bank_name or "", c.bank_account or "",
        ]
        for c in rows_data
    ]
    return export_table(rows, headers, "customers", format, inline=inline)


@router.get("/customers/import-template")
def customers_import_template(format: str = Query("xlsx")):
    """거래처 일괄등록 양식 다운로드."""
    headers = [
        "이름", "상호", "사업자번호", "대표자", "주소", "업태", "종목",
        "전화", "팩스", "이메일", "담당자", "은행", "계좌"
    ]
    sample = [[
        "예시고객사", "(주)예시상사", "123-45-67890", "홍길동",
        "서울 강남구 예시로 1", "도소매", "식품",
        "02-1234-5678", "02-1234-5679", "ex@example.com", "김담당",
        "국민은행", "123-456-789",
    ]]
    return export_table(sample, headers, "customers_import_template", format)


@router.post(
    "/customers/import",
    dependencies=[Depends(require_role("admin"))],
)
async def import_customers(
    file: UploadFile = File(...),
    upsert: bool = Query(True, description="True면 사업자번호 또는 이름 중복 시 update"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    """거래처 일괄 등록/갱신 (xlsx + csv).

    필수: 이름 (또는 사업자번호)
    매칭 우선순위: business_no > name
    헤더 별칭: 한글/영문 모두 인식.
    """
    from app.core.business_no import is_valid_business_no, format_business_no
    from app.core.imports import parse_upload

    alias = {
        "name": "name", "이름": "name", "고객명": "name", "거래처명": "name",
        "company": "company", "상호": "company", "회사": "company",
        "business_no": "business_no", "사업자번호": "business_no",
        "사업자등록번호": "business_no", "biz_no": "business_no",
        "representative": "representative", "대표자": "representative", "대표": "representative",
        "address": "address", "주소": "address", "사업장주소": "address",
        "business_type": "business_type", "업태": "business_type",
        "business_item": "business_item", "종목": "business_item",
        "phone": "phone", "전화": "phone", "전화번호": "phone", "tel": "phone",
        "fax": "fax", "팩스": "fax",
        "email": "email", "이메일": "email", "메일": "email",
        "contact_person": "contact_person", "담당자": "contact_person",
        "bank_name": "bank_name", "은행": "bank_name", "은행명": "bank_name",
        "bank_account": "bank_account", "계좌": "bank_account", "계좌번호": "bank_account",
    }
    rows = await parse_upload(file, alias)

    created = updated = skipped = 0
    errors: list[dict] = []

    for idx, r in enumerate(rows, start=2):
        name = str(r.get("name") or "").strip()
        company = str(r.get("company") or "").strip() or None
        biz_no = str(r.get("business_no") or "").strip() or None

        if not name and not company and not biz_no:
            errors.append({"row": idx, "reason": "이름·상호·사업자번호 모두 비어있음"})
            continue
        if not name:
            name = company or biz_no  # fallback

        # 사업자번호 입력했으면 체크섬 검증
        if biz_no and not is_valid_business_no(biz_no):
            errors.append({"row": idx, "reason": f"사업자번호 체크섬 오류: {biz_no}"})
            continue
        if biz_no:
            biz_no = format_business_no(biz_no)

        # 매칭: 사업자번호 우선, 없으면 이름
        existing = None
        if biz_no:
            existing = (
                db.query(Customer).filter(Customer.business_no == biz_no).first()
            )
        if not existing:
            existing = db.query(Customer).filter(Customer.name == name).first()

        fields = {
            "name": name,
            "company": company,
            "business_no": biz_no,
            "representative": str(r.get("representative") or "").strip() or None,
            "address": str(r.get("address") or "").strip() or None,
            "business_type": str(r.get("business_type") or "").strip() or None,
            "business_item": str(r.get("business_item") or "").strip() or None,
            "phone": str(r.get("phone") or "").strip() or None,
            "fax": str(r.get("fax") or "").strip() or None,
            "email": str(r.get("email") or "").strip() or None,
            "contact_person": str(r.get("contact_person") or "").strip() or None,
            "bank_name": str(r.get("bank_name") or "").strip() or None,
            "bank_account": str(r.get("bank_account") or "").strip() or None,
        }

        if existing:
            if not upsert:
                skipped += 1
                continue
            for k, v in fields.items():
                if v is not None:
                    setattr(existing, k, v)
            updated += 1
        else:
            db.add(Customer(**fields, owner_id=user.id, tenant_id=tenant_id))
            created += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"저장 실패: {exc}")

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total_rows": len(rows),
    }


@router.get("/orders", response_model=Page[SalesOrderOut])
def list_orders(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    q = (
        _scoped_filter(user, tenant_id)(db.query(SalesOrder), SalesOrder)
        .options(selectinload(SalesOrder.customer), selectinload(SalesOrder.items))
        .order_by(SalesOrder.order_date.desc())
    )
    return paginate(q, params)


@router.get("/orders/export")
def export_orders(
    format: str = Query("csv"), inline: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    orders = service.list_orders(
        db, query_filter=lambda q, m: scope_to_owner(q, m, user, "sales")
    )
    headers = ["주문번호", "일자", "고객", "상태", "총액"]
    rows = [
        [
            o.order_no,
            o.order_date.isoformat(),
            o.customer.name if o.customer else "",
            o.status.value if hasattr(o.status, "value") else str(o.status),
            float(o.total),
        ]
        for o in orders
    ]
    return export_table(rows, headers, "orders", format, inline=inline)


# ---- 외부 쇼핑몰 주문 일괄 import ───────────────────────────────────


@router.get("/orders/import-template")
def orders_import_template(format: str = Query("xlsx")):
    """온라인 주문 일괄등록 양식 다운로드 (표준).

    헤더는 카페24·네이버·쿠팡 등 모든 주요 쇼핑몰의 export 양식과 호환되도록
    한글/영문 별칭 다중 인식. 한 SO에 라인 N개면 라인마다 한 행, '주문번호'로 묶음.
    """
    headers = [
        "주문번호", "주문일자", "고객명", "전화", "이메일",
        "배송주소", "SKU", "상품명", "수량", "단가",
        "쇼핑몰", "쇼핑몰주문ID", "비고",
    ]
    sample = [
        ["WEB-20260619-001", "2026-06-19", "홍길동", "010-1234-5678",
         "hong@example.com", "서울 강남구 테헤란로 1, 101호",
         "WG-RAD-LE-330", "웰그린 라들러 레몬 330ml", 24, 2500,
         "카페24", "C24-100001", "오전배송"],
        ["WEB-20260619-001", "2026-06-19", "홍길동", "010-1234-5678",
         "hong@example.com", "서울 강남구 테헤란로 1, 101호",
         "WG-COLA-355", "웰그린 콜라 355ml", 12, 1500,
         "카페24", "C24-100001", ""],
    ]
    return export_table(sample, headers, "orders_import_template", format)


@router.post(
    "/orders/import",
    dependencies=[Depends(require_role("admin"))],
)
async def import_orders(
    file: UploadFile = File(...),
    auto_confirm: bool = Query(
        False,
        description="True면 import 즉시 SO 확정 + 재고차감. 권장: False(draft)",
    ),
    default_customer_type: str = Query(
        "individual",
        description="새로 생성되는 고객 유형 — individual 또는 business",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    """외부 쇼핑몰 주문 일괄 import.

    1. 행마다 SKU/external_sku 로 Item 매칭 → 못 찾으면 errors
    2. (전화 또는 이메일 또는 쇼핑몰주문ID)로 Customer 매칭, 없으면 자동 생성
       · 새 고객의 customer_type = default_customer_type (기본 individual)
    3. 동일 '주문번호'끼리 묶어서 SO 1건 생성 (라인 N개)
    4. auto_confirm=true 면 즉시 SO confirm → 재고 차감 + COGS 분개
       (재고 부족이면 그 SO만 draft 유지하고 errors 기록)

    카페24/네이버 스마트스토어/쿠팡 양식 모두 헤더 별칭으로 매핑.
    """
    from datetime import date as _date
    from decimal import Decimal as _D, InvalidOperation

    from app.core.imports import parse_upload
    from app.modules.inventory.models import Item
    from app.modules.sales.models import (
        Customer, CustomerType, OrderStatus, SalesOrder, SalesOrderItem,
    )

    if default_customer_type not in ("individual", "business"):
        raise HTTPException(
            status_code=400,
            detail="default_customer_type은 individual 또는 business",
        )

    alias = {
        # 주문 번호 / 일자
        "주문번호": "order_no", "order_no": "order_no", "ordercode": "order_no",
        "주문일자": "order_date", "order_date": "order_date", "결제일": "order_date",
        # 고객
        "고객명": "customer_name", "이름": "customer_name", "구매자": "customer_name",
        "수령인": "customer_name", "name": "customer_name",
        "전화": "phone", "연락처": "phone", "phone": "phone", "휴대폰": "phone",
        "이메일": "email", "email": "email",
        "배송주소": "address", "주소": "address", "address": "address",
        # 품목
        "sku": "sku", "SKU": "sku", "상품코드": "sku", "코드": "sku",
        "상품명": "item_name", "품목명": "item_name", "item_name": "item_name",
        "수량": "qty", "qty": "qty", "quantity": "qty",
        "단가": "unit_price", "가격": "unit_price", "unit_price": "unit_price",
        "판매가": "unit_price",
        # 메타
        "쇼핑몰": "shop", "쇼핑몰명": "shop", "shop": "shop", "channel": "shop",
        "쇼핑몰주문id": "external_order_id", "외부주문id": "external_order_id",
        "쇼핑몰주문번호": "external_order_id",
        "비고": "notes", "memo": "notes", "notes": "notes",
    }
    rows = await parse_upload(file, alias)

    # 1) 주문번호별 그룹핑
    by_order: dict[str, list[dict]] = {}
    for idx, r in enumerate(rows, start=2):
        order_no = str(r.get("order_no") or "").strip()
        if not order_no:
            order_no = str(r.get("external_order_id") or "").strip()
        if not order_no:
            r["_idx"] = idx
            r["_error"] = "주문번호와 쇼핑몰주문ID 모두 비어있음"
            by_order.setdefault("__bad__", []).append(r)
            continue
        r["_idx"] = idx
        by_order.setdefault(order_no, []).append(r)

    created_orders = 0
    confirmed_orders = 0
    skipped_orders = 0
    errors: list[dict] = []
    enum_type = CustomerType.individual if default_customer_type == "individual" else CustomerType.business

    # 잘못된 행 먼저 에러 처리
    for bad in by_order.pop("__bad__", []):
        errors.append({"row": bad["_idx"], "reason": bad["_error"]})

    for order_no, lines in by_order.items():
        # 기존 SO 있으면 skip
        if db.query(SalesOrder).filter(SalesOrder.order_no == order_no).first():
            skipped_orders += 1
            continue

        first = lines[0]
        cust_name = str(first.get("customer_name") or "").strip() or "온라인고객"
        phone = str(first.get("phone") or "").strip() or None
        email = str(first.get("email") or "").strip() or None
        address = str(first.get("address") or "").strip() or None
        shop = str(first.get("shop") or "").strip() or None
        ext_order_id = str(first.get("external_order_id") or "").strip() or None

        # Customer 매칭 — 외부ID > 전화 > 이메일 > 이름
        cust = None
        if ext_order_id and shop:
            cust = (
                db.query(Customer)
                .filter(
                    Customer.external_id == ext_order_id,
                    Customer.external_source == shop,
                )
                .first()
            )
        if not cust and phone:
            cust = db.query(Customer).filter(Customer.phone == phone).first()
        if not cust and email:
            cust = db.query(Customer).filter(Customer.email == email).first()
        if not cust:
            cust = Customer(
                name=cust_name,
                phone=phone,
                email=email,
                address=address,
                customer_type=enum_type,
                external_id=ext_order_id,
                external_source=shop,
                owner_id=user.id,
                tenant_id=tenant_id,
            )
            db.add(cust)
            db.flush()

        # 일자 파싱
        try:
            order_date_raw = first.get("order_date")
            if isinstance(order_date_raw, _date):
                order_date = order_date_raw
            elif order_date_raw:
                # 2026-06-19 또는 2026/06/19 둘 다
                txt = str(order_date_raw).split(" ")[0].replace("/", "-")
                y, m, d = txt.split("-")[:3]
                order_date = _date(int(y), int(m), int(d))
            else:
                order_date = _date.today()
        except Exception:
            order_date = _date.today()

        # 라인 변환
        so_lines: list[SalesOrderItem] = []
        total = _D("0")
        line_errors: list[str] = []
        for ln in lines:
            sku = str(ln.get("sku") or "").strip()
            if not sku:
                line_errors.append(f"{ln['_idx']}행: SKU 누락")
                continue
            item = (
                db.query(Item)
                .filter((Item.sku == sku) | (Item.external_sku == sku))
                .first()
            )
            if not item:
                line_errors.append(f"{ln['_idx']}행: SKU '{sku}' 매칭 안됨")
                continue
            try:
                qty = _D(str(ln.get("qty") or "0"))
                unit_price = _D(str(ln.get("unit_price") or item.unit_price or 0))
            except InvalidOperation:
                line_errors.append(f"{ln['_idx']}행: 수량/단가 파싱 실패")
                continue
            if qty <= 0:
                line_errors.append(f"{ln['_idx']}행: 수량 0 이하")
                continue
            so_lines.append(
                SalesOrderItem(item_id=item.id, quantity=qty, unit_price=unit_price)
            )
            total += qty * unit_price

        if not so_lines:
            errors.append({
                "row": first["_idx"],
                "reason": f"{order_no}: 유효 라인 없음 ({'; '.join(line_errors)})",
            })
            continue
        if line_errors:
            # 일부 라인만 실패 — SO는 만들되 에러 기록
            for le in line_errors:
                errors.append({"row": first["_idx"], "reason": f"{order_no}: {le}"})

        so = SalesOrder(
            order_no=order_no,
            customer_id=cust.id,
            order_date=order_date,
            status=OrderStatus.draft,
            total=total,
            owner_id=user.id,
            tenant_id=tenant_id,
        )
        for sl in so_lines:
            so.items.append(sl)
        db.add(so)
        db.flush()
        created_orders += 1

        # auto_confirm: 재고 차감 + COGS — 부족하면 draft 유지하고 에러
        if auto_confirm:
            try:
                from app.modules.sales import service
                service.confirm_order(db, so.id)
                confirmed_orders += 1
            except ValueError as exc:
                errors.append({
                    "row": first["_idx"],
                    "reason": f"{order_no} 확정 실패 (draft 유지): {exc}",
                })

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"저장 실패: {exc}")

    return {
        "created_orders": created_orders,
        "confirmed_orders": confirmed_orders,
        "skipped_orders": skipped_orders,
        "errors": errors,
        "total_rows": len(rows),
    }


@router.post(
    "/orders",
    response_model=SalesOrderOut,
    dependencies=[Depends(require_module_role("sales", "staff"))],
)
def create_order(
    payload: SalesOrderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int | None = Depends(get_current_tenant_id),
):
    return service.create_order(db, payload, owner_id=user.id, tenant_id=tenant_id)


@router.post(
    "/orders/{order_id}/confirm",
    response_model=SalesOrderOut,
    dependencies=[Depends(require_module_role("sales", "manager"))],
)
def confirm_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = service.get_order(db, order_id)
    if not order or not can_access(order, user, "sales"):
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        order = service.confirm_order(db, order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return order


# ---- Admin-only edit / delete ---------------------------------------------


from app.core.auth import require_role  # noqa: E402
from app.modules.sales.schemas import CustomerUpdate, SalesOrderUpdate  # noqa: E402


@router.patch(
    "/customers/{customer_id}",
    response_model=CustomerOut,
    dependencies=[Depends(require_role("admin"))],
)
def update_customer(
    customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)
):
    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cust, k, v)
    db.commit()
    db.refresh(cust)
    return cust


@router.delete(
    "/customers/{customer_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    if db.query(SalesOrder).filter(SalesOrder.customer_id == customer_id).first():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete customer with existing orders",
        )
    db.delete(cust)
    db.commit()
    return {"ok": True}


@router.patch(
    "/orders/{order_id}",
    response_model=SalesOrderOut,
    dependencies=[Depends(require_role("admin"))],
)
def update_order(
    order_id: int, payload: SalesOrderUpdate, db: Session = Depends(get_db)
):
    order = service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    status_v = order.status.value if hasattr(order.status, "value") else str(order.status)
    if status_v != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot edit order in {status_v} state — must be draft",
        )
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(order, k, v)
    db.commit()
    db.refresh(order)
    return order


@router.delete(
    "/orders/{order_id}",
    dependencies=[Depends(require_role("admin"))],
)
def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    status_v = order.status.value if hasattr(order.status, "value") else str(order.status)
    if status_v != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete order in {status_v} state — only draft orders are removable",
        )
    db.delete(order)
    db.commit()
    return {"ok": True}
