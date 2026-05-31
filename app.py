# ====================================================
# 🐻 財務安全チェッカー
# pip install -r requirements.txt
# streamlit run app.py
# ====================================================

import os
import streamlit as st
import yfinance as yf
import pandas as pd
import stripe
from dotenv import load_dotenv
from auth import show_auth_wall, logout, FREE_DAILY_LIMIT, is_supabase_configured
from db import get_today_usage_count, log_usage, get_user_plan

load_dotenv()

# ページ設定（最初に呼ぶ必要がある）
st.set_page_config(
    page_title="🐻 財務安全チェッカー",
    page_icon="🐻",
    layout="wide"
)

# Gemini API（任意 — キーがあればAI解説モードが有効になる）
_gemini_model = None
_gemini_ready = False
try:
    import google.generativeai as genai
    _google_api_key = os.getenv("GOOGLE_API_KEY")
    if _google_api_key:
        genai.configure(api_key=_google_api_key)
        _gemini_model = genai.GenerativeModel(
            "gemini-2.5-flash",
            system_instruction=(
                "あなたは「くまちゃん」という名前の財務分析の専門家です。"
                "初心者の投資家に対して、以下のルールで話してください：\n"
                "- 難しい専門用語は使わず、具体的な例えで説明する\n"
                "- クマらしい温かみのある口調（「〜だよ！」「〜だね。」「〜してみよう！」）\n"
                "- 数字の良し悪しだけでなく、業種・ビジネスモデルの文脈も考慮して解説する\n"
                "- 400文字以内でコンパクトに\n"
                "- マークダウンの見出しは使わず、自然な文章で"
            ),
        )
        _gemini_ready = True
except ImportError:
    pass

# Claude API（任意 — ANTHROPIC_API_KEY があれば有効）
_anthropic_client = None
try:
    import anthropic as _anthropic_mod
    _claude_key = os.getenv("ANTHROPIC_API_KEY")
    if _claude_key:
        _anthropic_client = _anthropic_mod.Anthropic(api_key=_claude_key)
except ImportError:
    pass

# ── 認証ゲート ────────────────────────────────────────────
# Supabase未設定時は開発モードとして全機能開放する

if not show_auth_wall():
    st.stop()

# ── ユーザー情報・プラン取得 ──────────────────────────────

user = st.session_state.get("user")
access_token = st.session_state.get("access_token")
user_id = user.id if user else None
user_email = user.email if user else "ゲスト"

# プランはセッション中キャッシュ（ページリロードのたびにDB問い合わせを抑制）
if st.session_state.get("user_plan") is None and user_id and is_supabase_configured():
    st.session_state["user_plan"] = get_user_plan(user_id, access_token)

user_plan = st.session_state.get("user_plan", "free")

# ── アップグレード完了通知（Stripe success_url からの復帰）──

if st.query_params.get("upgraded") == "true":
    st.session_state["user_plan"] = None  # 強制再取得
    st.query_params.clear()
    st.success("🎉 プレミアムプランへのアップグレードが完了しました！")

# ── Stripe Checkout URL 生成 ─────────────────────────────

def create_checkout_url() -> str | None:
    """
    目的: StripeのCheckoutセッションURLを生成する。
          未設定時はNoneを返す（UIでPayment Linkにフォールバック）
    戻り値: StripeチェックアウトURL文字列 または None
    """
    secret_key = os.getenv("STRIPE_SECRET_KEY", "")
    price_id = os.getenv("STRIPE_PRICE_ID", "")
    app_url = os.getenv("APP_URL", "http://localhost:8501")
    if not secret_key or not price_id:
        return None
    try:
        stripe.api_key = secret_key
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=user_email,
            line_items=[{"price": price_id, "quantity": 1}],
            metadata={"user_id": user_id or ""},
            success_url=app_url + "?upgraded=true",
            cancel_url=app_url,
        )
        return session.url
    except Exception:
        return None

# ── アップグレード壁 ──────────────────────────────────────

def _show_upgrade_wall():
    """
    目的: 無料枠上限到達時にアップグレードを促すブロッキングUIを表示する
    """
    st.warning(f"🐻 今日の無料枠（{FREE_DAILY_LIMIT}銘柄）を使い切ったよ！明日またチェックできます。")
    st.markdown("---")
    st.subheader("⭐ プレミアムプランで無制限に使おう")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
**無料プラン**
- 1日3銘柄まで
- ルールベース解説
- 基本4指標
        """)
    with col2:
        st.markdown("""
**⭐ プレミアム（月額980円）**
- **無制限** の銘柄分析
- **Claude AI** によるパーソナライズ解説
- ウォッチリスト（最大20銘柄）
- 2銘柄比較・CSVエクスポート
        """)

    checkout_url = create_checkout_url()
    target = checkout_url or os.getenv("STRIPE_PAYMENT_LINK", "")
    if target:
        st.link_button(
            "💳 今すぐプレミアムにアップグレード（月額980円）",
            target,
            use_container_width=True,
            type="primary",
        )
    else:
        st.info("準備中です。しばらくお待ちください。")

# ── サイドバー ────────────────────────────────────────────

with st.sidebar:
    st.header("👤 アカウント")
    st.caption(user_email)

    if user_plan == "premium":
        st.success("⭐ プレミアムプラン")
    else:
        st.info("🆓 無料プラン（1日3銘柄）")
        if user_id and is_supabase_configured():
            used = get_today_usage_count(user_id, access_token)
            remaining = max(0, FREE_DAILY_LIMIT - used)
            st.progress(used / FREE_DAILY_LIMIT, text=f"本日の残り：{remaining}/{FREE_DAILY_LIMIT} 回")

    if is_supabase_configured() and st.button("ログアウト", use_container_width=True):
        logout()

    st.divider()
    st.header("📝 数値の確認・修正")
    st.caption("自動取得値を上書き可能（単位：十億USD）")

    ca   = st.number_input("流動資産 (Current Assets)",      value=float(st.session_state.get("current_assets", 0.0)), format="%.3f", key="ca")
    cl   = st.number_input("流動負債 (Current Liabilities)", value=float(st.session_state.get("current_liab", 0.0)),   format="%.3f", key="cl")
    cash = st.number_input("現金同等物 (Cash & Equiv.)",     value=float(st.session_state.get("cash", 0.0)),           format="%.3f", key="cash_in")
    rec  = st.number_input("売上債権 (Net Receivables)",     value=float(st.session_state.get("receivables", 0.0)),    format="%.3f", key="rec")
    ni   = st.number_input("当期純利益 (Net Income)",        value=float(st.session_state.get("net_income", 0.0)),     format="%.3f", key="ni")
    eq   = st.number_input("株主資本 (Stockholders Equity)", value=float(st.session_state.get("equity", 0.0)),         format="%.3f", key="eq")
    rev  = st.number_input("純売上高 (Total Revenue)",       value=float(st.session_state.get("revenue", 0.0)),        format="%.3f", key="rev")

    st.divider()
    if _anthropic_client:
        st.success("🤖 Claude AI 解説モード ON")
    else:
        st.info("💡 ANTHROPIC_API_KEY を .env に設定するとAI解説が有効になります")

# ── メインUI ──────────────────────────────────────────────

st.title("🐻 財務安全チェッカー")
st.caption("初心者でも3分でわかる！企業の財務健全性を🐻が解説します")

# ── セッションステート初期化 ──────────────────────────────

_defaults = {
    "current_assets": 0.0,
    "current_liab":   0.0,
    "cash":           0.0,
    "receivables":    0.0,
    "net_income":     0.0,
    "equity":         0.0,
    "revenue":        0.0,
    "ticker":         "",
    "company_name":   "",
    "sector":         "",
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── データ取得関数 ────────────────────────────────────────

def fetch_financials(ticker: str) -> dict:
    """
    目的: yfinanceで米国株の財務データを取得する
    引数: ticker — 銘柄コード（例: AAPL）
    戻り値: 各財務項目の値（十億USD）を格納した辞書。取得失敗項目はNone
    """
    try:
        t = yf.Ticker(ticker)
        bs = t.balance_sheet
        inc = t.income_stmt

        def safe_get(df, key):
            try:
                val = df.loc[key].iloc[0]
                return float(val) if pd.notna(val) else None
            except Exception:
                return None

        return {
            "current_assets": safe_get(bs,  "Current Assets"),
            "current_liab":   safe_get(bs,  "Current Liabilities"),
            "cash":           safe_get(bs,  "Cash And Cash Equivalents"),
            "receivables":    safe_get(bs,  "Net Receivables"),
            "net_income":     safe_get(inc, "Net Income"),
            "equity":         safe_get(bs,  "Stockholders Equity"),
            "revenue":        safe_get(inc, "Total Revenue"),
        }
    except Exception:
        return {}


def fetch_company_info(ticker: str) -> dict:
    """
    目的: 銘柄の会社名・業種を取得する（🐻コメントの文脈づけに使用）
    引数: ticker — 銘柄コード
    戻り値: name・sector を含む辞書
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "name":   info.get("longName", ticker),
            "sector": info.get("sector", "不明"),
        }
    except Exception:
        return {"name": ticker, "sector": "不明"}

# ── ティッカー入力 & データ取得 ───────────────────────────

col_input, col_btn = st.columns([3, 1])
with col_input:
    ticker_input = st.text_input(
        "米国株ティッカーを入力",
        placeholder="例: AAPL / TSLA / WMT / NVDA",
        value=st.session_state["ticker"],
    )
with col_btn:
    st.write("")
    fetch_btn = st.button("📊 データ取得", use_container_width=True)

if fetch_btn and ticker_input:
    ticker_clean = ticker_input.upper().strip()

    # 無料プランの上限チェック
    if user_plan == "free" and user_id and is_supabase_configured():
        used_today = get_today_usage_count(user_id, access_token)
        if used_today >= FREE_DAILY_LIMIT:
            _show_upgrade_wall()
            st.stop()

    with st.spinner(f"{ticker_clean} のデータを取得中..."):
        data = fetch_financials(ticker_clean)
        info = fetch_company_info(ticker_clean)

    if data:
        for k in ["current_assets", "current_liab", "cash", "receivables",
                  "net_income", "equity", "revenue"]:
            if data.get(k) is not None:
                # yfinanceの値は実数ドルなので十億ドル単位に変換
                st.session_state[k] = data[k] / 1e9
        st.session_state["ticker"]       = ticker_clean
        st.session_state["company_name"] = info["name"]
        st.session_state["sector"]       = info["sector"]

        # 使用ログを記録（Supabase設定済みのときのみ）
        if user_id and is_supabase_configured():
            log_usage(user_id, ticker_clean, access_token)
            st.session_state["user_plan"] = None  # プランキャッシュをリセット

        st.success(f"✅ {info['name']}（{ticker_clean}）のデータを取得しました（単位：十億USD）")
    else:
        st.error("❌ データ取得に失敗しました。ティッカーを確認するか、サイドバーで手動入力してください。")

# ── 財務指標の計算 ────────────────────────────────────────

def safe_div(a, b):
    """0除算を回避して除算する。bが0またはNoneの場合はNoneを返す"""
    if b is None or b == 0:
        return None
    return a / b


current_ratio = safe_div(ca, cl)
quick_ratio   = safe_div((cash + rec), cl)
roe           = safe_div(ni, eq)
net_margin    = safe_div(ni, rev)

# デュポン：利益率10%超を製品差別化の目安とする
strategy = None
if net_margin is not None:
    strategy = "製品差別化戦略" if net_margin >= 0.10 else "コスト差別化戦略"

# ── ダッシュボード表示 ────────────────────────────────────

st.divider()

ticker_label = f"— {st.session_state['company_name']}" if st.session_state["company_name"] else ""
st.subheader(f"📊 財務指標ダッシュボード {ticker_label}")

m1, m2, m3 = st.columns(3)

with m1:
    st.markdown("#### 流動比率")
    if current_ratio is not None:
        icon = "🟢" if current_ratio >= 2.0 else ("🟡" if current_ratio >= 1.0 else "🔴")
        st.metric("Current Ratio", f"{current_ratio:.2f}", icon)
        st.progress(min(current_ratio / 3.0, 1.0))
        st.caption("🟢 ≥2.0　🟡 ≥1.0　🔴 <1.0")
    else:
        st.metric("Current Ratio", "N/A")

with m2:
    st.markdown("#### 当座比率")
    if quick_ratio is not None:
        icon = "🟢" if quick_ratio >= 1.0 else ("🟡" if quick_ratio >= 0.5 else "🔴")
        st.metric("Quick Ratio", f"{quick_ratio:.2f}", icon)
        st.progress(min(quick_ratio / 2.0, 1.0))
        st.caption("🟢 ≥1.0　🟡 ≥0.5　🔴 <0.5")
    else:
        st.metric("Quick Ratio", "N/A")

with m3:
    st.markdown("#### ROE")
    if roe is not None:
        roe_pct = roe * 100
        icon = "🟢" if roe_pct >= 15 else ("🟡" if roe_pct >= 8 else "🔴")
        st.metric("Return on Equity", f"{roe_pct:.1f}%", icon)
        st.progress(min(abs(roe_pct) / 50.0, 1.0))
        st.caption("🟢 ≥15%　🟡 ≥8%　🔴 <8%")
    else:
        st.metric("Return on Equity", "N/A")

# デュポン判定バッジ
if strategy:
    badge = "✨ 製品差別化戦略（高付加価値型）" if strategy == "製品差別化戦略" else "🔄 コスト差別化戦略（薄利多売型）"
    st.info(f"**デュポン判定：** {badge}")

# ── 🐻 解説コメント生成（Claude API → フォールバックの順）──

def generate_bear_comment_ai(
    ticker: str,
    company_name: str,
    sector: str,
    current_ratio_val,
    quick_ratio_val,
    roe_val,
    net_margin_val,
    strategy_val: str,
) -> str:
    """
    目的: Claude Haiku APIを使って文脈を考慮した🐻解説文を生成する
    引数: 銘柄情報・財務指標の値
    戻り値: 初心者向けの日本語解説文（クマキャラクター口調）。失敗時はNone
    """
    if not _anthropic_client:
        return None

    user_prompt = f"""以下の銘柄の財務指標を解説してください。

銘柄: {company_name}（{ticker}）
セクター: {sector}
流動比率: {f"{current_ratio_val:.2f}" if current_ratio_val is not None else "不明"}
当座比率: {f"{quick_ratio_val:.2f}" if quick_ratio_val is not None else "不明"}
ROE: {f"{roe_val*100:.1f}%" if roe_val is not None else "不明"}
利益率: {f"{net_margin_val*100:.1f}%" if net_margin_val is not None else "不明"}
デュポン判定: {strategy_val if strategy_val else "不明"}

この会社の財務状況を、初心者投資家が「なるほど！」と感じられるように解説してください。
特に業種の特性と数字の意味を結びつけて説明してください。"""

    try:
        response = _anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=(
                "あなたは「くまちゃん」という名前の財務分析の専門家です。"
                "初心者の投資家に対して、以下のルールで話してください：\n"
                "- 難しい専門用語は使わず、具体的な例えで説明する\n"
                "- クマらしい温かみのある口調（「〜だよ！」「〜だね。」「〜してみよう！」）\n"
                "- 数字の良し悪しだけでなく、業種・ビジネスモデルの文脈も考慮して解説する\n"
                "- 400文字以内でコンパクトに\n"
                "- マークダウンの見出しは使わず、自然な文章で"
            ),
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
    except Exception:
        return None  # フォールバックに委譲


def show_bear_comment(msg: str):
    """🐻のチャットバブルとしてコメントを表示する"""
    with st.chat_message("assistant", avatar="🐻"):
        st.write(msg)


def show_bear_comments_fallback():
    """
    目的: Claude APIなし時のフォールバック解説（ルールベース）
    """
    # 流動比率コメント
    if current_ratio is not None:
        if current_ratio >= 2.0:
            show_bear_comment(
                f"流動比率が **{current_ratio:.2f}** だね！手元の資金が潤沢で、"
                "短期的な支払いはバッチリ安全。財務的にとても余裕がある状態だよ！"
            )
        elif current_ratio >= 1.0:
            show_bear_comment(
                f"流動比率は **{current_ratio:.2f}**。ギリギリ安全圏だけど、余裕はそんなに多くないね。"
                "業種や事業内容をもう少し確認してみよう。"
            )
        else:
            show_bear_comment(
                f"流動比率が **{current_ratio:.2f}** で1.0を下回ってるよ！"
                "理論上、短期的な資金繰りがタイトな状態。"
                "ただ業種によっては普通のこともあるから、文脈を見てね。"
            )

    # 在庫リスクの検出（流動比率と当座比率の乖離が大きい場合）
    if current_ratio is not None and quick_ratio is not None:
        gap = current_ratio - quick_ratio
        if gap > 0.8:
            show_bear_comment(
                f"流動比率（{current_ratio:.2f}）と当座比率（{quick_ratio:.2f}）の差が大きいね。"
                "在庫（棚卸資産）をかなり抱えてる可能性があるよ。"
                "その在庫がちゃんと売れる見込みがあるかどうか、確認してみよう！"
            )

    # ROEコメント
    if roe is not None:
        roe_pct = roe * 100
        if roe_pct >= 20:
            show_bear_comment(
                f"ROEが **{roe_pct:.1f}%** ！株主のお金をめちゃくちゃ効率よく使えてる優秀な会社だよ。"
                "稼ぐ力がかなり強い！"
            )
        elif roe_pct >= 8:
            show_bear_comment(
                f"ROEは **{roe_pct:.1f}%**。平均的な水準で、堅実に稼げてる会社だね。"
            )
        else:
            show_bear_comment(
                f"ROEが **{roe_pct:.1f}%** でちょっと低め。"
                "株主のお金をうまく使えてないかも。理由があるか調べてみよう。"
            )

    # デュポン戦略コメント
    if strategy == "製品差別化戦略":
        show_bear_comment(
            "利益率が高いね！これは **製品差別化戦略** タイプだよ。"
            "ブランド力や技術力で1回の売上から大きな利益を取る高付加価値路線。"
            "TeslaやAppleと同じ稼ぎ方だよ！"
        )
    elif strategy == "コスト差別化戦略":
        show_bear_comment(
            "利益率は低めだけど、たくさん売って稼ぐ **コスト差別化戦略** タイプだよ！"
            "WalmartやAmazonみたいに、薄利多売・効率重視で勝負してる会社だね。"
        )


# 解説を表示する
st.divider()
st.subheader("🐻 くまちゃんの解説")

has_data = any([ca > 0, cl > 0, ni != 0, eq > 0])

if not has_data:
    show_bear_comment("ティッカーを入力して「データ取得」ボタンを押してね！気になる銘柄の財務を一緒に調べよう🐻")
elif _anthropic_client and st.session_state["ticker"]:
    # Gemini APIによる統合解説
    with st.spinner("🐻 くまちゃんが分析中..."):
        ai_comment = generate_bear_comment_ai(
            ticker=st.session_state["ticker"],
            company_name=st.session_state["company_name"],
            sector=st.session_state["sector"],
            current_ratio_val=current_ratio,
            quick_ratio_val=quick_ratio,
            roe_val=roe,
            net_margin_val=net_margin,
            strategy_val=strategy,
        )
    if ai_comment:
        show_bear_comment(ai_comment)
    else:
        show_bear_comments_fallback()
else:
    show_bear_comments_fallback()

# ── プレミアムCTA（無料ユーザーの解説下部に常時表示）────

if user_plan == "free" and has_data and is_supabase_configured():
    st.divider()
    with st.container(border=True):
        st.markdown("**⭐ プレミアムプランで、くまちゃんのAI解説が使い放題に！**")
        st.caption("月額980円 • いつでもキャンセル可 • 無制限の銘柄分析")
        checkout_url = create_checkout_url()
        target = checkout_url or os.getenv("STRIPE_PAYMENT_LINK", "")
        if target:
            st.link_button("今すぐアップグレード →", target, type="primary")

st.divider()
st.caption("⚠️ このアプリは教育目的です。投資判断はご自身の責任でお願いします。データはYahoo Financeから取得しています。")
