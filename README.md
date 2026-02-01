# TradeChart JP

EDINET/TDnet から取得した日本株の財務データと終値のテクニカル指標を Streamlit で表示するダッシュボードです。米国版 TradeChart の設計を踏襲しつつ、日本市場のデータソースとユースケースに合わせて再構築しています。

## セットアップ
1. 依存関係をインストール:
   ```bash
   pip install -r requirements.txt
   ```
2. `.env` に以下の環境変数を設定（必要に応じて）:
   ```env
   APP_COMPANY_NAME="Your Company"
   APP_EMAIL_ADDRESS="you@example.com"
   CHANNEL_ACCESS_TOKEN=""
   CHANNEL_SECRET=""
   LINE_TARGET_USER_ID=""
   ```
3. サンプルの証券コード対応は `data/mappings/code_mapping.json` に格納しています。必要に応じて拡張してください。

## 実行方法
```bash
streamlit run streamlit_app_jp.py
```

## 機能
- 証券コードを指定して EDINET から有価証券報告書/四半期報告書をダウンロード。
- XBRL から売上高/営業利益/当期純利益/営業CF を抽出し、YoY/CAGR を可視化。
- yfinance から終値を取得し、移動平均線・RSI を描画。
- 指定閾値に基づいたアラートを JSON 保存し、LINE に通知可能。

詳細な設計は `DESIGN_JP.md` を参照してください。
# TradeChartJp
