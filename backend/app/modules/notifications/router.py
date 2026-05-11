from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_current_internal_user, require_role
from app.core.db import SessionLocal, get_db
from app.core.email import send_email_safe
from app.core.security import decode_token
from app.core.ws import manager
from app.modules.auth.models import User
from app.modules.inventory.models import Item
from app.modules.sales.models import OrderStatus, SalesOrder

router = APIRouter(
    prefix="/api/notifications",
    tags=["notifications"],
    dependencies=[Depends(get_current_internal_user)],
)


@router.get("")
def list_notifications(
    low_stock_threshold: int = Query(10, ge=0),
    db: Session = Depends(get_db),
):
    """Compute alerts from current state. No persistence layer in PoC."""
    notifications: list[dict] = []

    low_stock_items = (
        db.query(Item).filter(Item.stock_qty < low_stock_threshold).order_by(Item.stock_qty).all()
    )
    for item in low_stock_items:
        qty = Decimal(item.stock_qty)
        notifications.append(
            {
                "id": f"low-stock-{item.id}",
                "level": "warning" if qty > 0 else "error",
                "type": "low_stock",
                "title": f"재고 부족: {item.name}",
                "message": f"SKU {item.sku} 재고가 {qty}로 임계치({low_stock_threshold}) 미만입니다.",
                "module": "inventory",
                "ref_id": item.id,
            }
        )

    open_orders = (
        db.query(SalesOrder)
        .filter(SalesOrder.status == OrderStatus.draft)
        .order_by(SalesOrder.order_date.desc())
        .all()
    )
    for order in open_orders:
        notifications.append(
            {
                "id": f"draft-order-{order.id}",
                "level": "info",
                "type": "draft_order",
                "title": f"미확정 주문: {order.order_no}",
                "message": f"주문 {order.order_no} 가 아직 확정되지 않았습니다.",
                "module": "sales",
                "ref_id": order.id,
            }
        )

    return {
        "count": len(notifications),
        "items": notifications,
    }


@router.post(
    "/email-alerts",
    dependencies=[Depends(require_role("admin"))],
)
def email_low_stock_alerts(
    background_tasks: BackgroundTasks,
    threshold: int = Query(10, ge=0),
    db: Session = Depends(get_db),
):
    """Queue a low-stock digest to every admin (sent after the response)."""
    from app.core.email import queue_email

    items = (
        db.query(Item).filter(Item.stock_qty < threshold).order_by(Item.stock_qty).all()
    )
    if not items:
        return {"queued": 0, "reason": "no low-stock items"}

    body_lines = [
        f"- {i.sku} {i.name}: 재고 {i.stock_qty} (단가 {i.unit_price})" for i in items
    ]
    body = "다음 품목의 재고가 임계치 미만입니다:\n\n" + "\n".join(body_lines)

    admins = db.query(User).filter(User.role == "admin").all()
    for admin in admins:
        queue_email(background_tasks, admin.email, "[ERP] 재고 부족 알림", body)
    return {"queued": len(admins), "items": len(items)}


ws_router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@ws_router.websocket("/ws")
async def ws_notifications(websocket: WebSocket, token: str | None = None):
    """WebSocket connection for live push notifications.

    Auth via ?token=<jwt> query param.
    """
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub", 0))
    except (JWTError, ValueError, TypeError):
        await websocket.close(code=4401)
        return
    if not user_id:
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            await websocket.close(code=4401)
            return
    finally:
        db.close()

    await manager.connect(user_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "user_id": user_id})
        while True:
            await websocket.receive_text()  # ignore client messages (could be heartbeat)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(user_id, websocket)


# ---- Multi-channel dispatch ------------------------------------------------


from pydantic import BaseModel as _BM_n  # noqa: E402

from app.core.auth import require_role as _require_role_n  # noqa: E402
from app.modules.notifications.channels import EmailAdapter, SlackAdapter  # noqa: E402


class DispatchIn(_BM_n):
    subject: str
    body: str
    channels: list[str] = ["email"]  # email|slack|ws
    recipients: list[str] = []          # for email
    user_ids: list[int] = []            # for websocket


@router.post(
    "/dispatch",
    dependencies=[Depends(_require_role_n("manager"))],
)
async def dispatch(payload: DispatchIn):
    """Send a notification through one or more channels at once.

    Returns per-channel success flags. A no-op for any unconfigured channel.
    """
    results: dict[str, bool] = {}
    if "email" in payload.channels:
        results["email"] = EmailAdapter().send(
            payload.subject, payload.body, payload.recipients
        )
    if "slack" in payload.channels:
        results["slack"] = SlackAdapter().send(payload.subject, payload.body)
    if "ws" in payload.channels:
        sent = 0
        for uid in payload.user_ids:
            try:
                await manager.send_to_user(uid, {
                    "type": "notification",
                    "subject": payload.subject,
                    "body": payload.body,
                })
                sent += 1
            except Exception:
                pass
        results["ws"] = sent > 0
    return {"results": results}
