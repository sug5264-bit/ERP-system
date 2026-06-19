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
