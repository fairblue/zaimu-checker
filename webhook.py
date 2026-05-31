"""
Stripe Webhookハンドラ（FastAPI）

目的: Stripeからのイベントを受け取り、Supabaseのuser_plansテーブルを更新する。
      このサーバーはStreamlitとは別プロセスで動作する（render.yaml参照）。
実行: uvicorn webhook:app --host 0.0.0.0 --port 8000
"""

import os
import stripe
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
from db import upgrade_user_plan, downgrade_user_plan

load_dotenv()

app = FastAPI()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    目的: Stripeのwebhookイベントを受信し、プラン更新をSupabaseに反映する
    引数: Stripe署名ヘッダー付きのHTTPリクエスト
    戻り値: {"status": "ok"}（失敗時は400/500エラー）
    """
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event["type"]
    data = event["data"]["object"]

    # サブスク開始・更新
    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        _handle_subscription_active(data)

    # サブスクキャンセル・失効
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(data)

    # 支払い成功（月次更新時の期限延長）
    elif event_type == "invoice.payment_succeeded":
        _handle_invoice_paid(data)

    return {"status": "ok"}


def _handle_subscription_active(sub: dict):
    """
    目的: サブスク開始・更新時にpremiumプランを付与する
    引数: sub — Stripe Subscriptionオブジェクト
    """
    user_id = sub.get("metadata", {}).get("user_id")
    if not user_id:
        return
    expires_at = datetime.fromtimestamp(
        sub["current_period_end"], tz=timezone.utc
    ).isoformat()
    upgrade_user_plan(
        user_id=user_id,
        stripe_customer_id=sub.get("customer", ""),
        stripe_subscription_id=sub["id"],
        plan_expires_at=expires_at,
    )


def _handle_subscription_deleted(sub: dict):
    """
    目的: サブスクキャンセル時にfreeプランへ戻す
    引数: sub — Stripe Subscriptionオブジェクト
    """
    user_id = sub.get("metadata", {}).get("user_id")
    if user_id:
        downgrade_user_plan(user_id)


def _handle_invoice_paid(invoice: dict):
    """
    目的: 月次更新時、Subscriptionを取得してplan_expires_atを延長する
    引数: invoice — Stripe Invoiceオブジェクト
    """
    sub_id = invoice.get("subscription")
    if not sub_id:
        return
    try:
        sub = stripe.Subscription.retrieve(sub_id)
        _handle_subscription_active(sub)
    except Exception:
        pass
