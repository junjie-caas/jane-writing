#!/usr/bin/env python3
"""读取 notes_json 全量结果，生成跨文献中文归纳。"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_records(notes_json_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for fp in sorted(notes_json_dir.glob("*.json")):
        if fp.name == "failed_records.jsonl":
            continue
        try:
            records.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            continue
    return records


def finding_polarity(text: str) -> str:
    t = (text or "").lower()
    positive_words = ["increase", "improve", "higher", "gain", "positive"]
    negative_words = ["decrease", "reduce", "lower", "decline", "negative"]
    pos = sum(1 for w in positive_words if w in t)
    neg = sum(1 for w in negative_words if w in t)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def collect_theme_support(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    support: dict[str, list[str]] = defaultdict(list)
    for r in records:
        pid = r.get("paper_id", "待人工核实")
        for tag in r.get("theme_tags", ["待人工核实"]):
            support[tag].append(pid)
    return support


def detect_conflicts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_theme: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in records:
        pid = r.get("paper_id", "待人工核实")
        finding = r.get("findings", "待人工核实")
        polarity = finding_polarity(finding)
        for tag in r.get("theme_tags", ["待人工核实"]):
            by_theme[tag].append({"paper_id": pid, "finding": finding, "polarity": polarity})

    conflicts: list[dict[str, Any]] = []
    for theme, items in by_theme.items():
        polarities = {i["polarity"] for i in items}
        if "positive" in polarities and "negative" in polarities:
            conflicts.append({"theme": theme, "items": items})
    return conflicts


def collect_viral_numbers(records: list[dict[str, Any]], top_n: int = 8) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for r in records:
        pid = r.get("paper_id", "待人工核实")
        for item in r.get("source_quotes", []):
            num = str(item.get("number", "")).strip()
            page = item.get("page", "待人工核实")
            quote = str(item.get("quote_en", "待人工核实")).strip()
            if not num:
                continue
            score = 0
            if "%" in num:
                score += 3
            if any(x in quote.lower() for x in ["increase", "decrease", "income", "yield", "productivity"]):
                score += 2
            if len(num) >= 4:
                score += 1
            candidates.append(
                {
                    "paper_id": pid,
                    "number": num,
                    "page": str(page),
                    "quote_en": quote,
                    "score": str(score),
                }
            )
    candidates.sort(key=lambda x: int(x["score"]), reverse=True)
    return candidates[:top_n]


def classify_conclusions(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    theme_support = collect_theme_support(records)
    conflicts = {c["theme"] for c in detect_conflicts(records)}

    robust: list[str] = []
    marginal: list[str] = []
    controversial: list[str] = []

    for theme, pids in theme_support.items():
        count = len(set(pids))
        if theme in conflicts:
            controversial.append(f"{theme}（存在相互冲突结果，涉及 {count} 篇）")
        elif count >= 2:
            robust.append(f"{theme}（多篇支持，涉及 {count} 篇）")
        else:
            marginal.append(f"{theme}（目前仅 1 篇支持，属边际结论）")

    if not robust:
        robust = ["待人工核实（当前样本不足以形成稳健结论）"]
    if not marginal:
        marginal = ["待人工核实"]
    if not controversial:
        controversial = ["未检测到明确冲突（待后续样本增加）"]

    return {"robust": robust, "marginal": marginal, "controversial": controversial}


def build_view_tree(theme_support: dict[str, list[str]]) -> list[str]:
    lines: list[str] = []
    for theme, pids in sorted(theme_support.items(), key=lambda kv: len(set(kv[1])), reverse=True):
        uniq = sorted(set(pids))
        lines.append(f"- 主题：{theme}")
        lines.append("  - 核心主张：基于现有文献，需结合具体 findings 人工审读。")
        lines.append(f"  - 证据来源：{', '.join(uniq)}")
        lines.append("  - 公众号表达建议：先讲问题，再给数字证据，最后补局限性。")
    return lines or ["- 待人工核实（无可用主题数据）"]


def render_overview(records: list[dict[str, Any]]) -> str:
    total = len(records)
    theme_support = collect_theme_support(records)
    theme_counter = Counter({k: len(set(v)) for k, v in theme_support.items()})
    conflicts = detect_conflicts(records)
    viral_numbers = collect_viral_numbers(records)
    conclusion_levels = classify_conclusions(records)
    tree_lines = build_view_tree(theme_support)

    lines: list[str] = [
        "# 跨文献归纳总览（中文）",
        "",
        "## 数据范围",
        f"- 纳入文献数：{total}",
        "- 数据来源：`notes_json/` 全部结构化结果。",
        "",
        "## 共同主题",
    ]

    if theme_counter:
        for theme, cnt in theme_counter.most_common():
            lines.append(f"- {theme}：{cnt} 篇涉及")
    else:
        lines.append("- 待人工核实（暂无主题标签）")

    lines.extend(["", "## 相互冲突的观点"])
    if conflicts:
        for c in conflicts:
            lines.append(f"- 主题：{c['theme']}")
            for item in c["items"]:
                lines.append(
                    f"  - {item['paper_id']}：{item['finding']}（方向：{item['polarity']}）"
                )
    else:
        lines.append("- 未检测到明显正负冲突（当前样本下）。")

    lines.extend(["", "## 最有传播性的关键数据（含出处）"])
    if viral_numbers:
        for v in viral_numbers:
            lines.append(
                f"- {v['number']}（来源：{v['paper_id']}, p.{v['page']}，原句：{v['quote_en']}）"
            )
    else:
        lines.append("- 待人工核实（缺少可用数字出处）")

    lines.extend(["", "## 适合公众号写作的观点树"])
    lines.extend(tree_lines)

    lines.extend(["", "## 结论分层"])
    lines.append("### 稳健结论")
    lines.extend([f"- {x}" for x in conclusion_levels["robust"]])
    lines.append("### 边际结论")
    lines.extend([f"- {x}" for x in conclusion_levels["marginal"]])
    lines.append("### 争议性结论")
    lines.extend([f"- {x}" for x in conclusion_levels["controversial"]])

    lines.extend([
        "",
        "## 使用提醒",
        "- 该文件用于跨文献选题和写作提纲，不替代逐篇事实核验。",
        "- 若出现缺页码或原句缺失，需在原始 PDF 中补证后再发布。",
    ])
    return "\n".join(lines)


def main() -> None:
    base = Path(__file__).resolve().parent
    notes_json_dir = base / "notes_json"
    themes_dir = base / "themes"
    themes_dir.mkdir(parents=True, exist_ok=True)

    records = load_records(notes_json_dir)
    out = render_overview(records)

    output_path = themes_dir / "overview_cn.md"
    output_path.write_text(out, encoding="utf-8")
    print(f"[OK] 已生成跨文献归纳：{output_path}")


if __name__ == "__main__":
    main()
