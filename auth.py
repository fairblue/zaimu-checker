import os
import streamlit as st
from supabase import create_client


FREE_DAILY_LIMIT = 3  # 無料ユーザーの1日あたり最大分析回数


def _sb():
    return create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_ANON_KEY", ""))


def is_supabase_configured() -> bool:
    """Supabase環境変数が設定されているか確認（未設定時はauth無効で動作）"""
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_ANON_KEY"))


def show_auth_wall() -> bool:
    """
    目的: Supabaseが設定済みの場合、ログイン/登録画面を表示する。
          認証済みなら True を返し、未認証なら False を返してここで描画を止める。
    引数: なし（st.session_state を参照）
    戻り値: bool — True=認証済み、False=未認証
    """
    if not is_supabase_configured():
        # 開発モード: 認証なしで全機能開放
        if "user" not in st.session_state:
            st.session_state["user"] = None
            st.session_state["access_token"] = None
            st.session_state["user_plan"] = "free"
        return True

    if st.session_state.get("user"):
        return True

    # ── ログイン/登録フォーム ──────────────────────────────
    st.title("🐻 財務安全チェッカー")
    st.caption("無料登録して、米国株の財務健全性をくまちゃんと一緒にチェックしよう！")
    st.info("無料プラン：1日3銘柄まで　｜　プレミアム（月額980円）：無制限")

    tab_login, tab_signup = st.tabs(["ログイン", "新規登録（無料）"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("メールアドレス")
            password = st.text_input("パスワード", type="password")
            submitted = st.form_submit_button("ログイン", use_container_width=True)
        if submitted:
            _handle_login(email, password)

    with tab_signup:
        with st.form("signup_form"):
            email = st.text_input("メールアドレス", key="su_email")
            password = st.text_input("パスワード（8文字以上）", type="password", key="su_pw")
            submitted = st.form_submit_button("無料で登録する", use_container_width=True)
        if submitted:
            _handle_signup(email, password)

    return False


def _handle_login(email: str, password: str):
    """ログイン処理。成功時はsession_stateにユーザー情報を格納してrerun。"""
    try:
        res = _sb().auth.sign_in_with_password({"email": email, "password": password})
        st.session_state["user"] = res.user
        st.session_state["access_token"] = res.session.access_token
        st.session_state["user_plan"] = None  # 次のrun時にDBから取得
        st.rerun()
    except Exception:
        st.error("メールアドレスまたはパスワードが正しくありません")


def _handle_signup(email: str, password: str):
    """新規登録処理。確認メール送信後にメッセージを表示。"""
    try:
        _sb().auth.sign_up({"email": email, "password": password})
        st.success("✅ 登録完了！確認メールをご確認ください。確認後にログインできます。")
    except Exception:
        st.error("このメールアドレスはすでに登録済みです")


def logout():
    """ログアウト: セッションをクリアしてrerun。"""
    for key in ["user", "access_token", "user_plan",
                "current_assets", "current_liab", "cash",
                "receivables", "net_income", "equity", "revenue",
                "ticker", "company_name", "sector"]:
        st.session_state.pop(key, None)
    st.rerun()
