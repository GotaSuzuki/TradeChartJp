# TradeChart JP 設計ドキュメント

## 1. 背景
- 既存の `/Users/suzukigouta/Documents/chart` プロジェクト（米国 SEC 10-K ダッシュボード）は、Streamlit を用いて EDGAR から財務情報を取得し、YoY/CAGR、テクニカル指標、アラート機能を提供している。
- 本計画では同じ UX とコード構造を踏襲しつつ、日本株（東証上場企業）向けにローカライズした **TradeChart JP** を新規作成する。

## 2. ゴールとスコープ
- 銘柄コード（4 桁）で EDINET/TDnet から最新の有価証券報告書・四半期報告書を取得し、主要指標（売上高 / 営業利益 / 当期純利益 / 営業CF）と YoY/CAGR を可視化する。
- JPX/日次終値 API から価格系列を取得し、移動平均線・RSI などのテクニカルビューを表示する。
- 価格・RSI・財務 YoY に基づくアラートを登録/通知（LINE 連携は既存コードを流用）。
- 既存チャート版と同様に、Streamlit 単一ページアプリ + ファイルキャッシュ構造で完結させる。
- 当面は **手動取得（ユーザーの操作トリガー）** を前提とし、後続でスケジューラ連携を追加できるようにする。

## 3. 参照プロジェクトとの差分
| 項目 | 既存チャート (米国) | TradeChart JP | 対応方針 |
| --- | --- | --- | --- |
| 財務データ | SEC EDGAR companyfacts (XBRL) | EDINET API (XBRL), TDnet JSON | `EdinetClient` でドキュメント ID / XBRL を取得し、`jp-gaap`/`ifrs-full` タクソノミを解析。TDnet は速報値や修正の確認に使用。 |
| ティッカー | ティッカー or CIK | 4 桁銘柄コード、英数ティッカー（ADR 等） | `code_mapping.json` で JPX コード⇔EDINET コード⇔証券コード協会コードを保持。 |
| 通貨 | USD 固定 | JPY (必要に応じて百万単位表示) | 正規化ステップで `unit` を `JPY`, `JPYMillions` 等に揃え、UI で単位を切替。 |
| 価格データ | yfinance (米株) | JPX (QUICK/JPX API) or yfinance `.T` | MVP では `yfinance` の東証サフィックス (`7203.T`) を利用、必要なら kabu+ API への差し替えが可能なインターフェース層を設計。 |
| 書類種別 | 10-K 固定 | 有価証券報告書・四半期報告書・臨報 | `filings_fetcher_jp` で取得対象フォームを `ASR`, `QSR` など設定可能に。 |
| 言語 | 日・英混在 | 日本語 UI + 指標名 | `i18n.py` で共通ラベルを定義。 |

## 4. 全体アーキテクチャ
```
ユーザー操作
   ↓ (銘柄コード入力)
Streamlit UI (streamlit_app_jp.py)
   ├─ Service Locator (_init_services)
   │    ├─ AppConfig (env + .env.local)
   │    ├─ DataCache (data/cache)
   │    ├─ EdinetClient / TdnetClient (requests)
   │    └─ PriceService (yfinance or JPX API)
   ├─ FilingsFetcherJP → XBRL Downloader → ParserJP
   │    └─ MetricsBuilder (YoY/CAGR/Tidy DataFrame)
   ├─ TechnicalView (price history + RSI/MA)
   └─ AlertsService (JSON + LineNotifier)
```

### ディレクトリ構成（案）
```
chartJP/
  app/
    clients/
      edinet_client.py
      tdnet_client.py
      price_service.py
    services/
      filings_fetcher_jp.py
      metrics_builder.py
      alerts.py (既存流用)
      notifier.py (既存流用)
    parsers/
      xbrl_parser.py
      taxonomy_map.py
    cache.py (既存流用)
    config.py (JP 用デフォルト)
  data/
    cache/
    mappings/code_mapping.json
  streamlit_app_jp.py
  tests/
    test_edinet_client.py
    test_parser_jp.py
    test_metrics_builder.py
  DESIGN_JP.md (本ドキュメント)
```

## 5. コンポーネント設計

### 5.1 Config & ブートストラップ
- `app/config.py`: JP 向けのデフォルト値（会社名・メールアドレス・ダウンロード先 `data/raw_jp`）と API キー（TDnet, JPX, LINE）。
- Streamlit 起動時に `_init_services()` で config, cache, clients を初期化。これは既存 `chart/streamlit_app.py` の構造をそのまま踏襲する。

### 5.2 EDINET クライアント (`app/clients/edinet_client.py`)
- 役割: EDINET API からドキュメントリスト (`documents.json`) を銘柄コードで取得し、必要な書類 (有価証券報告書=ASR、四半期報告書=QSR) の `docID` を特定、ZIP/XBRL をダウンロードする。
- API: `https://disclosure.edinet-fsa.go.jp/api/v2/documents.json?type=2&code=xxxx`、ダウンロード: `.../documents/{docID}?type=1`。
- 実装ポイント:
  - HTTP ヘッダで `User-Agent` を config と揃える（EDINET 利用規約準拠）。
  - `download_dir` 直下に `docID.zip` を保存し、キャッシュ TTL（デフォルト 12h）を `DataCache` と共通化。
  - `list_documents(form_codes: List[str], limit: int)` `download_xbrl(doc_id)` の 2 メソッドを公開。

### 5.3 TDnet クライアント (`app/clients/tdnet_client.py`)
- 速報用: TDnet の JSON API (example: `https://www.release.tdnet.info/inbs/I_main_00_{YYYYMMDD}.json`) をフェッチし、指定銘柄の最新開示を取得。
- 速報値や修正情報を UI の「イベントタイムライン」タブで表示する予定。EDINET 書類確定前の確認にも利用。

### 5.4 XBRL パーサ (`app/parsers/xbrl_parser.py`)
- 既存 `app/parser.py` の考え方を継承し、日本タクソノミ対応の概念マッピングを行う。
- `taxonomy_map.py` に `METRIC_CONCEPTS_JP` を定義:
  - 売上高: `jpcrp030000-asr:NetSales`, `ifrs-full:Revenue` etc
  - 営業利益: `jpcrp030000-asr:OperatingIncome`
  - 当期純利益: `jpcrp030000-asr:ProfitLossAttributableToOwnersOfParent`
  - 営業CF: `jpcrp030000-asr:NetCashProvidedByUsedInOperatingActivities`
- XBRL は多階層 XML のため、`arelle` / `BeautifulSoup` を使わず、Python の `lxml` + `pandas` で読み込み、`contextRef` の期間終了日から会計年度を推定する。抽出結果は `List[{'year': 2023, 'value': float, 'unit': 'JPY'}]` の形式に整える。

### 5.5 FilingsFetcher JP (`app/services/filings_fetcher_jp.py`)
- 流れ:
 1. `code_mapping.json` を参照し、EDINET コード ⇔ 銘柄コードの対応を取得。
 2. `EdinetClient.list_documents()` で過去 N 年分の ASR/QSR をフェッチ。
 3. ダウンロード済み ZIP から `XBRL` を抽出し、`xbrl_parser` に渡す。
 4. `MetricsBuilder` に引き渡す前に、`Meta` 情報（提出日、期末日、会計基準 IFRS/JGAAP 等）を整理。
- 既存 `FilingsFetcher` と同様に `DataCache` で JSON/解析結果をキャッシュし、ダウンロード回数を抑制する。

### 5.6 MetricsBuilder (`app/services/metrics_builder.py`)
- 既存 `app/metrics.py` の `compute_yoy`/`compute_cagr`/`to_dataframe` を再利用。
- 追加要件:
  - 通貨単位のスケーリング (`JPY` vs `JPYThousands`). UI 表示時に `value / scale` と `suffix` を返す関数を共通化。
  - 会計期間（年度 vs 四半期）を表す `period_type` を保持し、UI で切替可能にする。

### 5.7 価格サービス (`app/clients/price_service.py`)
- MVP: yfinance ラッパーで `7203.T` 形式に自動変換。
- オプション: kabu+ / JPX real-time API への切替に備え、`PriceService` インターフェース (`download_price_history(code: str, market: str) -> pd.DataFrame`) を定義。
- 出力 schema は既存 `market_data.py` と互換 (`Date`, `Close`, `Open`, `High`, `Low`, `Volume`).

### 5.8 UI (`streamlit_app_jp.py`)
- 既存 `streamlit_app.py` をベースに以下を調整:
  - 入力: `st.text_input("証券コード", value="7203")`
  - ビュー切替: `ファンダメンタル / テクニカル / タイムライン / アラート`
  - ファンダメンタル: `st.metric` + Plotly ラインチャート。YoY/CAGR を日本語で表示。
  - テクニカル: 終値 + MA20/50/200, RSI, 出来高ヒートマップ。
  - タイムライン: TDnet 開示と EDINET 提出履歴を縦型リストで表示。
  - アラート: 既存フォームを流用し、条件に「RSI < X」「YoY 売上 < 0」などを追加。

### 5.9 アラート/通知
- `app/alerts.py`, `app/notifier.py` をそのまま import し、警戒閾値だけ JP 設定へ変更。
- 価格や RSI の閾値チェックは、`PriceService` でフェッチした最新データを `st.button("最新データでチェック")` で実行できるようにする。
- 将来的な自動通知向けに `scripts/run_alerts.py` を追加し、cron や GitHub Actions で定期実行できるようにする。

## 6. データモデル
| モデル | 主フィールド | 説明 |
| --- | --- | --- |
| `FilingMeta` | `doc_id`, `fiscal_year`, `fiscal_period`, `form_code`, `filed_date`, `report_end_date` | EDINET/TDnet のメタ情報。 |
| `FactEntry` | `concept`, `value`, `unit`, `context_period_end`, `period_type` | XBRL から抽出された単一数値。 |
| `MetricSeries` | `metric`, `year`, `value`, `unit`, `period_type`, `yoy` | UI で扱う整形済みデータ。 |
| `PricePoint` | `date`, `close`, `open`, `high`, `low`, `volume`, `rsi`, `ma20/50/200` | テクニカル表示用。

## 7. 非機能要件
- **パフォーマンス**: 銘柄取得 1 回あたり 10 秒以内（EDINET API は 3 req/sec 制限のためキャッシュ必須）。
- **再利用性**: 元プロジェクトの `cache.py`, `metrics.py`, `alerts.py`, `notifier.py` を pip-install ではなくモジュールコピーで活用。
- **テスト**: `pytest` でクライアント/パーサのユニットテストを実施。EDINET/TDnet レスポンスはサンプル JSON/XBRL を `tests/fixtures` に格納。
- **国際化**: 初期は日本語固定だが、今後英語 UI を導入できるよう `labels.py` に辞書をまとめる。

## 8. 実装ロードマップ
1. **基盤構築** (Day 1-2)
   - chart プロジェクトをクローンし、`chartJP` に Streamlit/poetry 環境を準備。
   - 共有モジュール (cache, metrics, alerts, notifier) をコピー。
2. **データ取得層** (Day 3-5)
   - `EdinetClient` と `FilingsFetcherJP` を実装、ダミー銘柄で XBRL を取得。
   - `xbrl_parser` で主要指標を抽出、ユニットテスト作成。
3. **プレゼンテーション** (Day 6-7)
   - `streamlit_app_jp.py` のファンダメンタルビューを完成。
   - 価格サービス + テクニカルビューを統合。
4. **アラート/通知 + 仕上げ** (Day 8-9)
   - アラート UI/LINE 通知を接続し、TDnet タイムラインを追加。
   - README/ユーザーガイド/環境変数例を整備。
5. **将来拡張 (バックログ)**
   - 自動スケジューラ、DB 永続化、複数銘柄サマリー画面、ニュース分析（形態素解析によるサマリー）。

## 9. リスクと緩和策
- **EDINET レート制限**: キャッシュ TTL + 失敗時バックオフ (`tenacity` で再試行) を用意。
- **タクソノミ変更**: `taxonomy_map.py` を JSON 設定化し、追加概念を簡単に登録できるようにする。
- **価格 API の不安定さ**: インターフェース層で fallback（yfinance → kabu+ → 直近 CSV）を切替可能にする。
- **データ欠損**: UI で「データ不足」の警告を明示し、別指標（営業利益率など）を後日追加。

---
このドキュメントをベースに、`chart` プロジェクトの実装パターンを再利用しながら日本株版を段階的に構築する。
