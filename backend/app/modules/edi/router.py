"""EDI / B2B integration.

Inbound: partners (or scheduled jobs) POST documents here. We persist the raw
payload, parse known message types, and try to translate them into ERP entities
(e.g. an inbound PO becomes a SalesOrder).

Outbound: a helper renders an INVOIC document for a given sales order.

Auth: API key (X-API-Key) is the typical partner-facing credential. JWT works
too for human testing.
"""
from app.core.time import utc_now
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_current_internal_user, require_role
from app.core.db import get_db
from app.core.pagination import Page, PageParams, paginate
from app.modules.auth.models import User
from app.modules.edi.models import (
    EDIDirection,
    EDIMessage,
    EDIMessageType,
    EDIStatus,
)

router = APIRouter(
    prefix="/api/edi",
    tags=["edi"],
    dependencies=[Depends(get_current_internal_user)],
)


# --- Schemas ----------------------------------------------------------------


class InboundIn(BaseModel):
    msg_type: EDIMessageType
    partner_code: str | None = None
    payload: dict | str
    payload_format: str = "json"


class EDIMessageOut(BaseModel):
    id: int
    direction: EDIDirection
    msg_type: EDIMessageType
    partner_code: str | None
    payload: str
    payload_format: str
    status: EDIStatus
    error: str | None
    related_resource_type: str | None
    related_resource_id: int | None
    processed_at: object | None  # datetime, but kept loose here

    model_config = ConfigDict(from_attributes=True)


# --- Inbound: partners post documents ---------------------------------------


@router.post("/inbound", response_model=EDIMessageOut)
def receive_inbound(
    body: InboundIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = json.dumps(body.payload, ensure_ascii=False) if isinstance(body.payload, dict) else body.payload
    msg = EDIMessage(
        direction=EDIDirection.inbound,
        msg_type=body.msg_type,
        partner_code=body.partner_code,
        payload=raw,
        payload_format=body.payload_format,
        status=EDIStatus.received,
        created_by_id=user.id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


@router.post("/messages/{message_id}/process", response_model=EDIMessageOut)
def process_message(
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Translate a stored EDI message into ERP entities.

    Idempotent: re-processing a message is a no-op (returns existing result).
    Transactional: failures roll back any partial entities the handler created.
    """
    msg = (
        db.query(EDIMessage)
        .filter(EDIMessage.id == message_id)
        .with_for_update()
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Not found")
    if msg.status in (EDIStatus.processed, EDIStatus.sent):
        return msg

    try:
        # SAVEPOINT — failure inside the handler rolls back any rows it created
        # without losing the outer state-change on `msg` itself.
        with db.begin_nested():
            if (
                msg.direction == EDIDirection.inbound
                and msg.msg_type == EDIMessageType.purchase_order
            ):
                order = _process_inbound_po(db, msg, user)
                msg.related_resource_type = "sales_order"
                msg.related_resource_id = order.id
                msg.status = EDIStatus.processed
                msg.processed_at = utc_now()
                msg.error = None
            else:
                msg.status = EDIStatus.parsed  # acknowledged but no automation
        db.commit()
        db.refresh(msg)
        return msg
    except Exception as exc:
        db.rollback()
        # Re-fetch and mark failed in a fresh transaction.
        msg = db.query(EDIMessage).filter(EDIMessage.id == message_id).first()
        msg.status = EDIStatus.failed
        msg.error = str(exc)[:2000]
        db.commit()
        db.refresh(msg)
        raise HTTPException(status_code=400, detail=msg.error)


def _process_inbound_po(db: Session, msg: EDIMessage, user: User):
    """Translate {customer_code, customer_name, order_no, items: [{sku, qty, unit_price}]}
    into a SalesOrder."""
    from app.modules.inventory.models import Item
    from app.modules.sales.models import (
        Customer,
        OrderStatus,
        SalesOrder,
        SalesOrderItem,
    )
    from datetime import date as _date
    from decimal import Decimal

    if msg.payload_format != "json":
        raise ValueError("Only JSON-format inbound POs are supported in PoC")

    body = json.loads(msg.payload)
    cust_code = body.get("customer_code") or msg.partner_code
    cust_name = body.get("customer_name") or cust_code or "EDI customer"
    order_no = body.get("order_no")
    if not order_no:
        raise ValueError("payload.order_no is required")

    customer = (
        db.query(Customer).filter(Customer.name == cust_name).first()
        if cust_name
        else None
    )
    if not customer:
        customer = Customer(name=cust_name, company=cust_code)
        db.add(customer)
        db.flush()

    if db.query(SalesOrder).filter(SalesOrder.order_no == order_no).first():
        raise ValueError(f"order_no {order_no} already exists")

    total = Decimal("0")
    order = SalesOrder(
        order_no=order_no,
        customer_id=customer.id,
        order_date=_date.today(),
        status=OrderStatus.draft,
        total=0,
        owner_id=user.id,
    )
    for line in body.get("items", []):
        sku = line.get("sku")
        item = db.query(Item).filter(Item.sku == sku).first()
        if not item:
            raise ValueError(f"unknown sku: {sku}")
        qty = Decimal(str(line.get("qty") or line.get("quantity") or 0))
        price = Decimal(str(line.get("unit_price") or item.unit_price))
        total += qty * price
        order.items.append(
            SalesOrderItem(item_id=item.id, quantity=qty, unit_price=price)
        )
    order.total = total

    db.add(order)
    # Caller wraps this in a SAVEPOINT and a final commit; just flush so we get an id.
    db.flush()
    return order


# --- Outbound: render documents from ERP entities ---------------------------


@router.post("/outbound/invoice/{order_id}", response_model=EDIMessageOut)
def emit_invoice(
    order_id: int,
    partner_code: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a JSON-INVOIC document for a confirmed sales order and store it
    as an outbound EDI message. In production a workflow would push this to the
    partner endpoint (AS2 / SFTP / VAN)."""
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Manager required")

    from app.modules.sales.models import OrderStatus, SalesOrder
    from sqlalchemy.orm import selectinload

    order = (
        db.query(SalesOrder)
        .options(selectinload(SalesOrder.items), selectinload(SalesOrder.customer))
        .filter(SalesOrder.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in (OrderStatus.confirmed, OrderStatus.shipped):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot invoice an order in {order.status.value} state",
        )

    invoice = {
        "doc_type": "INVOIC",
        "invoice_no": f"INV-{order.order_no}",
        "issued_at": utc_now().isoformat(),
        "supplier": {"name": "WellGreen ERP"},
        "buyer": {"name": order.customer.name if order.customer else None},
        "order_ref": order.order_no,
        "lines": [
            {"item_id": l.item_id, "qty": float(l.quantity), "unit_price": float(l.unit_price)}
            for l in order.items
        ],
        "total": float(order.total),
    }

    msg = EDIMessage(
        direction=EDIDirection.outbound,
        msg_type=EDIMessageType.invoice,
        partner_code=partner_code,
        payload=json.dumps(invoice, ensure_ascii=False),
        payload_format="json",
        status=EDIStatus.sent,  # PoC: assume successful delivery
        related_resource_type="sales_order",
        related_resource_id=order.id,
        processed_at=utc_now(),
        created_by_id=user.id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


# --- Browse/list ------------------------------------------------------------


@router.get("/messages", response_model=Page[EDIMessageOut])
def list_messages(
    params: PageParams = Depends(),
    direction: EDIDirection | None = None,
    status: EDIStatus | None = None,
    msg_type: EDIMessageType | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(EDIMessage)
    if direction:
        q = q.filter(EDIMessage.direction == direction)
    if status:
        q = q.filter(EDIMessage.status == status)
    if msg_type:
        q = q.filter(EDIMessage.msg_type == msg_type)
    return paginate(q.order_by(EDIMessage.created_at.desc()), params)
