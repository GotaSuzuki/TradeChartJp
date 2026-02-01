"""財務メトリクスの加工（前年比など）。"""

from __future__ import annotations

from typing import Dict, List, Optional


def compute_yoy(metrics: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    """Compute YoY growth for each metric series.

    Returns a dict with the same keys as ``metrics`` where each point includes
    ``yoy`` (前年比) の割合を含む。
    """

    results: Dict[str, List[dict]] = {}
    for metric_name, series in metrics.items():
        if not series:
            results[metric_name] = []
            continue

        ordered = sorted(series, key=lambda item: item.get("year") or 0)
        prev_value: Optional[float] = None
        enriched: List[dict] = []
        for point in ordered:
            value = point.get("value")
            yoy = None
            if prev_value not in (None, 0) and value is not None:
                yoy = (value - prev_value) / abs(prev_value)
            enriched_point = dict(point)
            enriched_point["yoy"] = yoy
            enriched.append(enriched_point)
            prev_value = value if value is not None else prev_value
        results[metric_name] = enriched

    return results


def compute_cagr(metrics: Dict[str, List[dict]]) -> Dict[str, Optional[float]]:
    """Compute CAGR for each metric based on first/last available values."""

    cagr_values: Dict[str, Optional[float]] = {}
    for metric_name, series in metrics.items():
        cleaned = [
            (point.get("year"), point.get("value"))
            for point in series
            if point.get("year") is not None and point.get("value") is not None
        ]
        cleaned.sort(key=lambda item: item[0])
        if len(cleaned) < 2:
            cagr_values[metric_name] = None
            continue

        start_year, start_value = cleaned[0]
        end_year, end_value = cleaned[-1]
        if not start_value or not end_value:
            cagr_values[metric_name] = None
            continue

        periods = int(end_year) - int(start_year)
        if periods <= 0:
            cagr_values[metric_name] = None
            continue

        ratio = end_value / start_value
        if ratio <= 0:
            cagr_values[metric_name] = None
            continue

        cagr_values[metric_name] = ratio ** (1 / periods) - 1

    return cagr_values


def to_dataframe(metrics: Dict[str, List[dict]]):
    """Convert metric dict into a tidy DataFrame.

    分析や可視化で扱いやすいよう、年・値・メトリクス・YoY列を持つ。
    pandas が未インポートの場合の循環依存を避けるために局所 import。
    """

    import pandas as pd  # type: ignore

    rows = []
    for metric_name, series in metrics.items():
        for point in series:
            rows.append(
                {
                    "metric": metric_name,
                    "year": point.get("year"),
                    "value": point.get("value"),
                    "unit": point.get("unit"),
                    "yoy": point.get("yoy"),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["metric", "year", "value", "unit", "yoy"])

    df = pd.DataFrame(rows)
    df.sort_values(["metric", "year"], inplace=True)
    return df
