from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import a_yield_mysql_session
from services.payment_service import receive_payment_webhook
from services.payment_webhook_service import a_process_payment_webhooks
router = APIRouter()


@router.post("/razorpay", tags=["Payment Webhooks"])
async def razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_razorpay_signature: str = Header(default=""),
    x_razorpay_event_id: str = Header(default=""),
    db: AsyncSession = Depends(a_yield_mysql_session),
):
    accepted = await receive_payment_webhook(
        "razorpay", await request.body(), x_razorpay_signature, x_razorpay_event_id, db,
    )
    if accepted:
        # Uses a fresh session; the request session is never passed to background work.
        # Using batch_size as 1, since this endpoint is triggered via payment provider webhook on event of a payment captured for a single payment event,
        # hence we want to limit the PaymentWebhookEvent ORM to pick up only this event or None.
        background_tasks.add_task(a_process_payment_webhooks, event_id=x_razorpay_event_id, batch_size=1)
    return {"status": "accepted" if accepted else "ignored"}
