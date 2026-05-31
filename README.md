# 🐻 財務安全チェッカー

ティッカーを入れるだけで米国株の財務健全性を🐻が解説するStreamlitアプリ。

## 見れる指標

| 指標 | 内容 |
|------|------|
| 流動比率 | 短期の支払い能力（≥2.0で安全） |
| 当座比率 | 在庫を除いた実質的な支払い能力 |
| ROE | 株主資本の効率性（≥15%で優秀） |
| デュポン判定 | 製品差別化型 vs コスト差別化型 |

## 起動方法

```bash
cd 財務安全チェッカー
pip install -r requirements.txt
streamlit run app.py
```

## Claude AI解説モードの有効化（任意）

```bash
cp .env.example .env
# .env を開いて ANTHROPIC_API_KEY を設定
```

APIキーなしでもルールベースの🐻解説は動作します。

## 動作確認銘柄

- `AAPL` — 流動比率<1.0でも「攻めの財務戦略」と解説
- `WMT` — 低流動比率を「業種の特性」として正しく解釈
- `TSLA` — ROE高・製品差別化型と判定

## 技術スタック

- Python 3.11+
- Streamlit 1.35
- yfinance 0.2.40（Yahoo Finance無料API）
- Anthropic Claude Haiku（AI解説、オプション）