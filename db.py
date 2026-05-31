import os
from datetime import datetime, date, timezone
from supabase import create_client, Client


def _client(access_token: str | None = None) -> Client:
    """
    目的: Supabaseクライアントを返す。access_tokenがあればユーザーJWTで認証し、
          RLSが有効なテーブルへ安全にアクセスする。
    引数: access_token — ログイン済みユーザーのJWT（Noneの場合はanonキー）
    戻り値: Supabase Client
    """
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_ANON_KEY", "")
    sb = create_client(url, key)
    if access_token:
        sb.postgrest.auth(access_token)
    return sb


def _service_client() -> Client:
    """RLSをバイパスするサービスロールクライアント（webhook専用）"""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    return create_client(url, key)


# ── 使用量 ──────────────────────────────────────────────

def get_today_usage_count(user_id: str, access_token: str) -> int:
    """
    目的: 今日の分析回数を返す（無料プランの3回/日制限に使用）
    引数: user_id — Supabase Auth のユーザーUUID
          access_token — ユーザーのJWT
    戻り値: 今日の分析回数（整数）
    """
    sb = _client(access_token)
    today_start = date.today().isoformat() + "T00:00:00+00:00"
    res = (
        sb.table("usage_logs")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("analyzed_at", today_start)
        .execute()
    )
    return res.count or 0


def log_usage(user_id: str, ticker: str, access_token: str):
    """
    目的: 分析ログを記録する（1回の「データ取得」ごとに呼ぶ）
    引数: user_id — ユーザーUUID
          ticker  — 分析した銘柄コード
          access_token — ユーザーのJWT
    戻り値: None
    """
    sb = _client(access_token)
    sb.table("usage_logs").insert({
        "user_id": user_id,
        "ticker": ticker,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


# ── プラン ──────────────────────────────────────────────

def get_user_plan(user_id: str, access_token: str) -> str:
    """
    目的: ユーザーの現在プランを返す
    引数: user_id, access_token
    戻り値: "premium" または "free"
    """
    sb = _client(access_token)
    res = (
        sb.table("user_plans")
        .select("plan, plan_expires_at")
        .eq("user_id", user_id)
        .execute()
    )
    if not res.data:
        return "free"
    row = res.data[0]
    if row["plan"] != "premium":
        return "free"
    expires = row.get("plan_expires_at")
    if expires is None:
        return "premium"
    exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    return "premium" if exp_dt > datetime.now(timezone.utc) else "free"


def upgrade_user_plan(
    user_id: str,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    plan_expires_at: str,
):
    """
    目的: service_roleでユーザーをpremiumにアップグレードする（webhook専用）
    引数: plan_expires_at — ISO8601形式のUTC日時文字列
    戻り値: None
    """
    sb = _service_client()
    sb.table("user_plans").upsert({
        "user_id": user_id,
        "plan": "premium",
        "stripe_customer_id": stripe_customer_id,
        "stripe_subscription_id": stripe_subscription_id,
        "plan_expires_at": plan_expires_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def downgrade_user_plan(user_id: str):
    """
    目的: サブスクキャンセル時にfreeプランへ戻す（webhook専用）
    """
    sb = _service_client()
    sb.table("user_plans").upsert({
        "user_id": user_id,
        "plan": "free",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
