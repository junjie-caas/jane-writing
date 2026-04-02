#!/usr/bin/env python3
"""英文文献 -> JSON + 中文摘要 + 主题标签 批处理流水线。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF


THEME_RULES = {
    "粮食安全": ["food security", "grain", "rice", "wheat", "maize"],
    "农业补贴": ["subsidy", "support payment", "direct payment"],
    "贸易政策": ["trade policy", "tariff", "import", "export"],
    "气候与农业": ["climate", "drought", "temperature", "rainfall"],
    "农户行为与福利": ["household", "farmer", "welfare", "income"],
    "土地与生产率": ["land", "productivity", "yield", "efficiency"],
}


def read_pdf_pages(pdf_path: Path) -> list[str]:
    with fitz.open(pdf_path) as doc:
        return [page.get_text("text") or "" for page in doc]


def normalize_paper_id(pdf_path: Path, title: str, year: str) -> str:
    base = re.sub(r"\W+", "_", title.lower()).strip("_")[:40] if title else "untitled"
    year_part = year if year else "yyyy"
    file_part = re.sub(r"\W+", "_", pdf_path.stem.lower())[:20]
    return f"{year_part}_{file_part}_{base}".strip("_")


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def find_year(text: str) -> str:
    m = re.search(r"\b(19|20)\d{2}\b", text)
    return m.group(0) if m else "待人工核实"


def find_journal(text: str) -> str:
    for line in text.splitlines()[:30]:
        if re.search(r"journal|review|policy|economics", line, re.I):
            return line.strip()
    return "待人工核实"


def find_authors(text: str, title: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in lines[:12]:
        if line == title:
            continue
        if "@" in line:
            continue
        if len(line.split()) <= 12 and re.search(r"[A-Za-z]", line):
            if not re.search(r"abstract|journal|doi", line, re.I):
                parts = re.split(r",| and ", line)
                names = [p.strip() for p in parts if p.strip()]
                if names:
                    return names
    return ["待人工核实"]


def find_sentence(full_text: str, patterns: list[str]) -> str:
    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
    stitched = ". ".join(lines)
    sentences = re.split(r"(?<=[.!?])\s+", stitched)
    for s in sentences:
        for p in patterns:
            if re.search(p, s, re.I):
                return s.strip()
    return "待人工核实"




def extract_numbers_from_text(text: str) -> list[str]:
    pattern = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?%?\b")
    return pattern.findall(text)


def extract_number_evidence(pages_text: list[str], limit: int = 8) -> tuple[list[dict[str, Any]], list[int]]:
    evidence: list[dict[str, Any]] = []
    page_refs: list[int] = []
    num_pattern = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?%?\b")

    for idx, page in enumerate(pages_text, start=1):
        page_clean = page.replace("\n", " ")
        for m in num_pattern.finditer(page_clean):
            number = m.group(0)
            local = page_clean[max(0, m.start()-12):min(len(page_clean), m.end()+12)].lower()
            if "doi" in local:
                continue
            start = max(0, m.start() - 60)
            end = min(len(page_clean), m.end() + 60)
            quote = page_clean[start:end].strip()
            if not quote or "doi" in quote.lower():
                continue
            evidence.append(
                {
                    "number": number,
                    "page": idx,
                    "quote_en": quote,
                    "source": f"p.{idx}",
                }
            )
            if idx not in page_refs:
                page_refs.append(idx)
            if len(evidence) >= limit:
                return evidence, page_refs
    return evidence, page_refs


def detect_theme_tags(full_text: str) -> list[str]:
    lower = full_text.lower()
    tags = [tag for tag, keys in THEME_RULES.items() if any(k in lower for k in keys)]
    return tags or ["待人工核实"]


def build_structured_json(pdf_path: Path, pages_text: list[str]) -> dict[str, Any]:
    first_page = pages_text[0] if pages_text else ""
    full_text = "\n".join(pages_text)

    title = first_nonempty_line(first_page) or "待人工核实"
    year = find_year(first_page)
    journal = find_journal(first_page)
    authors = find_authors(first_page, title)

    question = find_sentence(full_text, [r"research question", r"this study", r"we examine", r"we investigate", r"whether"])
    data = find_sentence(full_text, [r"data", r"dataset", r"panel"])
    sample = find_sentence(full_text, [r"sample", r"observations", r"households", r"farms"])
    methods = find_sentence(full_text, [r"methods?:", r"regression", r"difference-in-differences", r"\biv\b", r"instrumental", r"fixed effects"])
    findings = find_sentence(full_text, [r"we find", r"results show", r"our findings", r"increase", r"decrease"])
    limitations = find_sentence(full_text, [r"limitation", r"caution", r"may not", r"future research"])
    policy_implications = find_sentence(full_text, [r"policy implication", r"policy implications", r"recommend", r"government"])

    evidence, page_refs = extract_number_evidence(pages_text)
    key_numbers_raw = extract_numbers_from_text(f"{sample} {findings} {policy_implications}")
    key_numbers = list(dict.fromkeys(key_numbers_raw))

    paper_id = normalize_paper_id(pdf_path, title, year if year != "待人工核实" else "")

    return {
        "paper_id": paper_id,
        "file_name": pdf_path.name,
        "title": title,
        "year": year,
        "journal": journal,
        "authors": authors,
        "question": question,
        "data": data,
        "sample": sample,
        "methods": methods,
        "findings": findings,
        "key_numbers": key_numbers,
        "limitations": limitations,
        "policy_implications": policy_implications,
        "source_quotes": evidence,
        "page_refs": page_refs if page_refs else ["待人工核实"],
        "theme_tags": detect_theme_tags(full_text),
    }


def build_chinese_summary(record: dict[str, Any]) -> str:
    def v(key: str) -> Any:
        val = record.get(key, "待人工核实")
        return val if val else "待人工核实"

    numbers = record.get("source_quotes", [])
    if numbers:
        num_lines = [
            f"- 数字：{n['number']}（出处：{record['paper_id']}, p.{n['page']}，原句：{n['quote_en']}）"
            for n in numbers[:5]
        ]
    else:
        num_lines = ["- 待人工核实（未提取到可引用数字或页码）"]

    lines = [
        f"# {v('paper_id')} 中文要点摘要",
        "",
        "## 基本信息",
        f"- 标题：{v('title')}",
        f"- 年份：{v('year')}",
        f"- 期刊：{v('journal')}",
        f"- 作者：{', '.join(v('authors')) if isinstance(v('authors'), list) else v('authors')}",
        "",
        "## 研究核心",
        f"- 研究问题：{v('question')}",
        f"- 数据来源：{v('data')}",
        f"- 样本信息：{v('sample')}",
        f"- 研究方法：{v('methods')}",
        f"- 主要发现：{v('findings')}",
        "",
        "## 关键数字（保留出处）",
        *num_lines,
        "",
        "## 政策启示",
        f"- {v('policy_implications')}",
        "",
        "## 局限性/争议",
        f"- {v('limitations')}",
        "",
        "## 主题标签",
        f"- {', '.join(record.get('theme_tags', ['待人工核实']))}",
    ]
    return "\n".join(lines)


def process_one_pdf(pdf_path: Path, notes_json_dir: Path, notes_cn_dir: Path) -> str:
    pages = read_pdf_pages(pdf_path)
    record = build_structured_json(pdf_path, pages)
    paper_id = record["paper_id"]

    json_path = notes_json_dir / f"{paper_id}.json"
    summary_path = notes_cn_dir / f"{paper_id}.md"

    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(build_chinese_summary(record), encoding="utf-8")
    return paper_id


def run_pipeline(base_dir: Path) -> None:
    papers_dir = base_dir / "papers_raw"
    notes_json_dir = base_dir / "notes_json"
    notes_cn_dir = base_dir / "notes_cn"

    notes_json_dir.mkdir(parents=True, exist_ok=True)
    notes_cn_dir.mkdir(parents=True, exist_ok=True)

    failed_log = notes_json_dir / "failed_records.jsonl"

    pdf_files = sorted(papers_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[WARN] 未在 {papers_dir} 找到 PDF 文件。")
        return

    for pdf in pdf_files:
        try:
            pid = process_one_pdf(pdf, notes_json_dir, notes_cn_dir)
            print(f"[OK] 已处理: {pdf.name} -> {pid}")
        except Exception as exc:  # noqa: BLE001
            failed = {
                "file_name": pdf.name,
                "reason": str(exc),
            }
            with failed_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(failed, ensure_ascii=False) + "\n")
            print(f"[FAIL] 处理失败: {pdf.name}，原因已记录")


def main() -> None:
    parser = argparse.ArgumentParser(description="批量处理英文论文 PDF")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="项目根目录（默认当前脚本所在目录）",
    )
    args = parser.parse_args()
    run_pipeline(args.base_dir)


if __name__ == "__main__":
    main()
