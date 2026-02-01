"""XBRL タクソノミから抽出する概念を定義。"""

from __future__ import annotations

METRIC_CONCEPTS_JP = {
    "revenue": [
        "jpcrp030000-asr:NetSales",
        "ifrs-full:Revenue",
    ],
    "operating_income": [
        "jpcrp030000-asr:OperatingIncome",
    ],
    "net_income": [
        "jpcrp030000-asr:ProfitLossAttributableToOwnersOfParent",
        "ifrs-full:ProfitLoss",
    ],
    "operating_cash_flow": [
        "jpcrp030000-asr:NetCashProvidedByUsedInOperatingActivities",
        "ifrs-full:NetCashFlowsFromUsedInOperatingActivities",
    ],
}
