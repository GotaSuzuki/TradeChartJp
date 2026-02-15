"""companyfacts から主要財務指標を抽出する。"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

METRIC_CONCEPTS = {
    "revenue": [
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
}


def extract_financials(filings: List[dict]) -> Dict[str, List[dict]]:
    if not filings:
        return {}

    facts = filings[0].get("facts", {})
    if not facts:
        return {}

    fiscal_years = _collect_fiscal_years(filings)
    if not fiscal_years:
        return {}

    concepts = (facts.get("facts") or {}).get("us-gaap", {})
    metrics: Dict[str, List[dict]] = {}
    for metric_name, concept_names in METRIC_CONCEPTS.items():
        series: List[dict] = []
        for year in fiscal_years:
            value, unit = _lookup_value(concepts, concept_names, year)
            series.append({
                "year": year,
                "value": value,
                "unit": unit,
            })
        metrics[metric_name] = series

    return metrics


def _collect_fiscal_years(filings: List[dict]) -> List[int]:
    years = []
    for filing in filings:
        meta = filing.get("meta", {})
        fiscal_year = meta.get("fiscal_year") or meta.get("fy")
        if fiscal_year is None:
            continue
        try:
            year = int(fiscal_year)
        except (ValueError, TypeError):
            continue
        years.append(year)

    unique_years = sorted(set(years))
    return unique_years


def _lookup_value(
    concepts: Dict[str, dict],
    concept_names: Iterable[str],
    fiscal_year: int,
) -> Tuple[Optional[float], Optional[str]]:
    for name in concept_names:
        concept = concepts.get(name)
        if not concept:
            continue

        units = concept.get("units", {})
        # まずUSD優先、次にその他
        unit_order = ["USD"] + [unit for unit in units.keys() if unit != "USD"]
        for unit_name in unit_order:
            facts = units.get(unit_name) or []
            for fact in sorted(facts, key=lambda item: item.get("end") or "", reverse=True):
                if fact.get("fy") != fiscal_year:
                    continue
                if fact.get("form") not in {"10-K", "20-F"}:
                    continue
                value = fact.get("val")
                if value is None:
                    continue
                try:
                    return float(value), unit_name
                except (TypeError, ValueError):
                    continue

    return None, None
