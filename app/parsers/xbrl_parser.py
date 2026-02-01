"""EDINET XBRL から財務指標を抽出する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from lxml import etree

from .taxonomy_map import METRIC_CONCEPTS_JP


@dataclass
class FactPoint:
    metric: str
    year: Optional[int]
    value: Optional[float]
    unit: Optional[str]
    period_type: str


class XbrlParser:
    def __init__(self, metric_concepts: Dict[str, List[str]] | None = None) -> None:
        self.metric_concepts = metric_concepts or METRIC_CONCEPTS_JP

    def parse_file(self, xbrl_path: str) -> Dict[str, List[dict]]:
        tree = etree.parse(xbrl_path)
        root = tree.getroot()
        nsmap = {k or "": v for k, v in root.nsmap.items() if v}
        contexts = _build_context_map(root, nsmap)
        units = _build_unit_map(root, nsmap)

        metrics: Dict[str, List[dict]] = {}
        for metric, concepts in self.metric_concepts.items():
            points: List[dict] = []
            for concept in concepts:
                prefix, local = concept.split(":", 1)
                namespace = nsmap.get(prefix)
                if not namespace:
                    continue
                xpath = f".//{{{namespace}}}{local}"
                for node in root.findall(xpath):
                    context_ref = node.get("contextRef")
                    context = contexts.get(context_ref or "")
                    if not context:
                        continue
                    year = context.year
                    try:
                        value = float(node.text) if node.text else None
                    except (TypeError, ValueError):
                        value = None
                    unit_ref = node.get("unitRef")
                    unit = units.get(unit_ref or "")
                    points.append(
                        {
                            "year": year,
                            "value": value,
                            "unit": unit,
                            "period_type": context.period_type,
                        }
                    )
            metrics[metric] = _merge_series(points)

        return metrics


@dataclass
class ContextInfo:
    year: Optional[int]
    period_type: str


def _build_context_map(root, nsmap) -> Dict[str, ContextInfo]:
    contexts: Dict[str, ContextInfo] = {}
    xbrli = nsmap.get("xbrli")
    if not xbrli:
        return contexts
    for context in root.findall(f".//{{{xbrli}}}context"):
        context_id = context.get("id") or ""
        period_elem = context.find(f".//{{{xbrli}}}period")
        year: Optional[int] = None
        period_type = "duration"
        if period_elem is not None:
            end = period_elem.find(f".//{{{xbrli}}}endDate")
            instant = period_elem.find(f".//{{{xbrli}}}instant")
            if end is not None and end.text:
                year = _safe_year(end.text)
            elif instant is not None and instant.text:
                year = _safe_year(instant.text)
                period_type = "instant"
        contexts[context_id] = ContextInfo(year=year, period_type=period_type)
    return contexts


def _build_unit_map(root, nsmap) -> Dict[str, str]:
    units: Dict[str, str] = {}
    xbrli = nsmap.get("xbrli")
    if not xbrli:
        return units
    measures = root.findall(f".//{{{xbrli}}}unit")
    for unit in measures:
        unit_id = unit.get("id") or ""
        measure_elem = unit.find(f".//{{{xbrli}}}measure")
        if measure_elem is None or measure_elem.text is None:
            continue
        units[unit_id] = measure_elem.text.split(":")[-1]
    return units


def _merge_series(points: List[dict]) -> List[dict]:
    filtered = [p for p in points if p.get("year") is not None and p.get("value") is not None]
    filtered.sort(key=lambda item: item["year"])
    merged: Dict[int, dict] = {}
    for point in filtered:
        year = int(point["year"])
        if year not in merged:
            merged[year] = point
            continue
        existing = merged[year]
        if existing.get("value") is None:
            merged[year] = point
    return list(merged.values())


def _safe_year(value: str) -> Optional[int]:
    try:
        return datetime.fromisoformat(value[:10]).year
    except ValueError:
        try:
            return int(value[:4])
        except ValueError:
            return None
