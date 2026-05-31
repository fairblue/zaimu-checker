-- ============================================================
-- 財務安全チェッカー — Supabaseマイグレーション
-- 実行先: Supabase Dashboard > SQL Editor
-- ============================================================

-- usage_logs: 分析ログ（無料ユーザーの1日3回制限に使用）
CREATE TABLE IF NOT EXISTS usage_logs (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker      TEXT        NOT NULL,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usage_logs_user_date
    ON usage_logs (user_id, analyzed_at DESC);

-- user_plans: プラン情報（free / premium）
CREATE TABLE IF NOT EXISTS user_plans (
    user_id                UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    plan                   TEXT        NOT NULL DEFAULT 'free',
    stripe_customer_id     TEXT,
    stripe_subscription_id TEXT,
    plan_expires_at        TIMESTAMPTZ,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Row Level Security ────────────────────────────────────────

ALTER TABLE usage_logs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_plans  ENABLE ROW LEVEL SECURITY;

-- 自分のログのみ参照・追加可能
DROP POLICY IF EXISTS "own usage read"   ON usage_logs;
DROP POLICY IF EXISTS "own usage insert" ON usage_logs;
CREATE POLICY "own usage read"
    ON usage_logs FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "own usage insert"
    ON usage_logs FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- 自分のプランのみ参照可能（更新はservice_role経由のwebhookのみ）
DROP POLICY IF EXISTS "own plan read" ON user_plans;
CREATE POLICY "own plan read"
    ON user_plans FOR SELECT
    USING (auth.uid() = user_id);

-- service_roleはRLSをバイパス（webhook.pyのupgrade/downgradeに必要）
-- ※ Supabaseはデフォルトでservice_roleがRLSをバイパスするため追加ポリシー不要

-- ── テーブル権限付与 ──────────────────────────────────────
-- RLSポリシーとは別に、authenticatedロールへの基本アクセス権が必要
-- （「新しいテーブルを自動的に公開する」をOFFにした場合は手動付与が必須）
GRANT SELECT, INSERT ON public.usage_logs TO authenticated;
GRANT SELECT ON public.user_plans TO authenticated;