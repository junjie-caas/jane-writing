#!/usr/bin/env python3
"""英文文献 -> JSON + 中文摘要 + 主题标签 批处理流水线。"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
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

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "these", "those", "into", "about",
    "across", "using", "use", "study", "paper", "evidence", "based", "effects", "effect",
    "analysis", "empirical", "approach", "model", "models", "results", "result", "data",
    "policy", "policies", "journal", "review", "introduction", "conclusion", "conclusions",
}

TRANSLATION_GLOSSARY = {
    "agriculture": "农业",
    "agricultural": "农业的",
    "climate": "气候",
    "change": "变化",
    "food": "食物",
    "security": "安全",
    "farmer": "农户",
    "farmers": "农户",
    "income": "收入",
    "productivity": "生产率",
    "trade": "贸易",
    "export": "出口",
    "import": "进口",
    "subsidy": "补贴",
    "subsidies": "补贴",
    "policy": "政策",
    "policies": "政策",
    "market": "市场",
    "welfare": "福利",
    "household": "家庭",
    "households": "家庭",
    "land": "土地",
    "yield": "单产",
    "drought": "干旱",
    "temperature": "温度",
    "rainfall": "降雨",
    "evidence": "证据",
    "impact": "影响",
    "impacts": "影响",
    "conclusion": "结论",
    "conclusions": "结论",
    "keyword": "关键词",
    "keywords": "关键词",
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

def _clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_complete_title(first_page: str) -> str:
    lines = [_clean_spaces(ln) for ln in first_page.splitlines() if ln.strip()]
    if not lines:
        return "待人工核实"
    for line in lines[:10]:
        m = re.match(r"(?i)^title\s*[:：]\s*(.+)$", line)
        if m:
            return m.group(1).strip()

    stop_patterns = [
        r"(?i)^abstract\b", r"(?i)^keywords?\b", r"(?i)^by\b", r"@",
        r"(?i)^doi\b", r"(?i)^journal\b", r"(?i)^author",
    ]
    title_lines: list[str] = []
    for line in lines[:8]:
        if any(re.search(p, line) for p in stop_patterns):
            break
        if len(line) < 5:
            continue
        title_lines.append(line)
        if len(title_lines) >= 3:
            break
    if title_lines:
        return _clean_spaces(" ".join(title_lines))
    return first_nonempty_line(first_page) or "待人工核实"


def _extract_block(full_text: str, start_patterns: list[str], end_patterns: list[str]) -> str:
    text = full_text.replace("\r\n", "\n")
    start_idx = -1
    for p in start_patterns:
        m = re.search(p, text, re.I)
        if m:
            start_idx = m.end()
            break
    if start_idx == -1:
        return "待人工核实"
    tail = text[start_idx:]
    end_idx = len(tail)
    for p in end_patterns:
        m = re.search(p, tail, re.I)
        if m and m.start() < end_idx:
            end_idx = m.start()
    block = _clean_spaces(tail[:end_idx])
    return block if block else "待人工核实"


def extract_abstract(full_text: str) -> str:
    abstract = _extract_block(
        full_text,
        [r"\babstract\b[:\s]*"],
        [r"\bkeywords?\b[:\s]*", r"\bindex terms\b[:\s]*", r"\b1\.?\s*introduction\b", r"\bintroduction\b"],
    )
    if abstract != "待人工核实":
        return abstract
    return find_sentence(full_text, [r"abstract", r"this study", r"we examine", r"we investigate", r"whether"])


def extract_conclusion(full_text: str) -> str:
    conclusion = _extract_block(
        full_text,
        [r"\bconclusions?\b[:\s]*", r"\b5\.?\s*conclusions?\b", r"\b6\.?\s*conclusions?\b"],
        [r"\breferences\b", r"\backnowledg", r"\bappendix\b"],
    )
    if conclusion != "待人工核实":
        return conclusion
    return find_sentence(full_text, [r"in conclusion", r"conclusion", r"we conclude", r"overall"])


def extract_keywords(full_text: str, title: str, abstract_en: str, conclusion_en: str, limit: int = 8) -> list[str]:
    normalized = full_text.replace("\r\n", "\n")
    kw_match = re.search(r"(?is)\bkeywords?\b\s*[:：]\s*(.+?)(?:\n\s*\n|\n[A-Z][^\n]{0,30}\n)", normalized)
    if not kw_match:
        kw_match = re.search(r"(?is)\bindex terms\b\s*[:：]\s*(.+?)(?:\n\s*\n|\n[A-Z][^\n]{0,30}\n)", normalized)
    if kw_match:
        raw = _clean_spaces(kw_match.group(1))
        parts = [p.strip(" .;:,") for p in re.split(r"[;,•·]| and ", raw) if p.strip()]
        unique = []
        for p in parts:
            if p.lower() not in [x.lower() for x in unique]:
                unique.append(p)
        if unique:
            return unique[:limit]

    fallback_text = f"{title} {abstract_en} {conclusion_en}".lower()
    tokens = re.findall(r"[a-z][a-z\-]{2,}", fallback_text)
    freq: dict[str, int] = defaultdict(int)
    for tok in tokens:
        if tok in STOPWORDS:
            continue
        freq[tok] += 1
    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    return [w for w, _ in ranked[:limit]] or ["待人工核实"]


def translate_to_zh(text: str) -> str:
    if not text or text == "待人工核实":
        return "待人工核实"
    translated = text
    for en, zh in sorted(TRANSLATION_GLOSSARY.items(), key=lambda x: len(x[0]), reverse=True):
        translated = re.sub(rf"\b{re.escape(en)}\b", zh, translated, flags=re.I)
    return f"【自动翻译草案，待人工校对】{translated}"


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

    title = extract_complete_title(first_page)
    year = find_year(first_page)
    journal = find_journal(first_page)
    authors = find_authors(first_page, title)

    abstract_en = extract_abstract(full_text)
    abstract_zh = translate_to_zh(abstract_en)
    question = find_sentence(full_text, [r"research question", r"this study", r"we examine", r"we investigate", r"whether"])
    data = find_sentence(full_text, [r"data", r"dataset", r"panel"])
    sample = find_sentence(full_text, [r"sample", r"observations", r"households", r"farms"])
    methods = find_sentence(full_text, [r"methods?:", r"regression", r"difference-in-differences", r"\biv\b", r"instrumental", r"fixed effects"])
    findings = find_sentence(full_text, [r"we find", r"results show", r"our findings", r"increase", r"decrease"])
    limitations = find_sentence(full_text, [r"limitation", r"caution", r"may not", r"future research"])
    policy_implications = find_sentence(full_text, [r"policy implication", r"policy implications", r"recommend", r"government"])
    conclusion_en = extract_conclusion(full_text)
    if conclusion_en == "待人工核实" and policy_implications != "待人工核实":
        conclusion_en = f"{policy_implications}（未检索到Conclusion段标题，暂以政策启示句代替，待人工核实）"
    conclusion_zh = translate_to_zh(conclusion_en)
    keywords_en = extract_keywords(full_text, title, abstract_en, conclusion_en)
    keywords_zh = [translate_to_zh(k) for k in keywords_en]

    evidence, page_refs = extract_number_evidence(pages_text)
    key_numbers_raw = extract_numbers_from_text(f"{sample} {findings} {policy_implications}")
    key_numbers = list(dict.fromkeys(key_numbers_raw))

    paper_id = normalize_paper_id(pdf_path, title, year if year != "待人工核实" else "")

    return {
        "paper_id": paper_id,
        "file_name": pdf_path.name,
        "title": title,
        "title_zh": translate_to_zh(title),
        "title_en": title,
        "keywords_en": keywords_en,
        "keywords_zh": keywords_zh,
        "year": year,
        "journal": journal,
        "authors": authors,
        "abstract_en": abstract_en,
        "abstract_zh": abstract_zh,
        "question": question,
        "data": data,
        "sample": sample,
        "methods": methods,
        "findings": findings,
        "key_numbers": key_numbers,
        "limitations": limitations,
        "policy_implications": policy_implications,
        "conclusion_en": conclusion_en,
        "conclusion_zh": conclusion_zh,
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
        f"- 标题（中文翻译）：{v('title_zh')}",
        f"- 标题（英文原文）：{v('title_en')}",
        f"- 年份：{v('year')}",
        f"- 期刊：{v('journal')}",
        f"- 作者：{', '.join(v('authors')) if isinstance(v('authors'), list) else v('authors')}",
        "",
        "## 标题、摘要与结论原文",
        f"- 关键词（英文）：{', '.join(record.get('keywords_en', ['待人工核实']))}",
        f"- 关键词（中文）：{', '.join(record.get('keywords_zh', ['待人工核实']))}",
        f"- 摘要原文：{v('abstract_en')}",
        f"- 结论原文：{v('conclusion_en')}",
        f"- 摘要中文翻译：{v('abstract_zh')}",
        f"- 结论中文翻译：{v('conclusion_zh')}",
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


def _keyword_roots(keywords: list[str]) -> set[str]:
    roots: set[str] = set()
    for kw in keywords:
        norm = re.sub(r"[^a-z0-9\u4e00-\u9fff\s-]", " ", kw.lower())
        for token in norm.split():
            if len(token) < 3:
                continue
            roots.add(token)
    return roots


def cluster_by_keywords(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for record in records:
        pid = record.get("paper_id", "待人工核实")
        kw_en = record.get("keywords_en", [])
        roots = _keyword_roots(kw_en if isinstance(kw_en, list) else [])
        if not roots:
            roots = {"待人工核实"}
        matched_idx = None
        for i, cluster in enumerate(clusters):
            c_roots = cluster["keyword_roots"]
            inter = len(roots & c_roots)
            union = len(roots | c_roots)
            jaccard = inter / union if union else 0
            if inter >= 2 or jaccard >= 0.35:
                matched_idx = i
                break
        if matched_idx is None:
            clusters.append(
                {
                    "cluster_id": f"C{len(clusters) + 1:02d}",
                    "keyword_roots": set(roots),
                    "papers": [{"paper_id": pid, "keywords_en": kw_en}],
                }
            )
        else:
            clusters[matched_idx]["keyword_roots"].update(roots)
            clusters[matched_idx]["papers"].append({"paper_id": pid, "keywords_en": kw_en})
    return sorted(clusters, key=lambda c: len(c["papers"]), reverse=True)


def write_keyword_clusters(themes_dir: Path, records: list[dict[str, Any]]) -> None:
    themes_dir.mkdir(parents=True, exist_ok=True)
    clusters = cluster_by_keywords(records)
    serializable = []
    lines = ["# 按相似关键词聚类结果", ""]
    for cluster in clusters:
        roots_sorted = sorted(cluster["keyword_roots"])
        serializable.append(
            {
                "cluster_id": cluster["cluster_id"],
                "keyword_roots": roots_sorted,
                "papers": cluster["papers"],
            }
        )
        lines.append(f"## {cluster['cluster_id']}（{len(cluster['papers'])} 篇）")
        lines.append(f"- 关键词根：{', '.join(roots_sorted)}")
        for p in cluster["papers"]:
            kws = p["keywords_en"] if p["keywords_en"] else ["待人工核实"]
            lines.append(f"- {p['paper_id']}：{', '.join(kws)}")
        lines.append("")
    (themes_dir / "keyword_clusters.json").write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (themes_dir / "keyword_clusters_cn.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_pipeline(base_dir: Path) -> None:
    papers_dir = base_dir / "papers_raw"
    notes_json_dir = base_dir / "notes_json"
    notes_cn_dir = base_dir / "notes_cn"
    themes_dir = base_dir / "themes"

    notes_json_dir.mkdir(parents=True, exist_ok=True)
    notes_cn_dir.mkdir(parents=True, exist_ok=True)

    failed_log = notes_json_dir / "failed_records.jsonl"

    pdf_files = sorted(papers_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[WARN] 未在 {papers_dir} 找到 PDF 文件。")
        return

    processed_records: list[dict[str, Any]] = []
    for pdf in pdf_files:
        try:
            pid = process_one_pdf(pdf, notes_json_dir, notes_cn_dir)
            record_path = notes_json_dir / f"{pid}.json"
            if record_path.exists():
                processed_records.append(json.loads(record_path.read_text(encoding="utf-8")))
            print(f"[OK] 已处理: {pdf.name} -> {pid}")
        except Exception as exc:  # noqa: BLE001
            failed = {
                "file_name": pdf.name,
                "reason": str(exc),
            }
            with failed_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(failed, ensure_ascii=False) + "\n")
            print(f"[FAIL] 处理失败: {pdf.name}，原因已记录")
    if processed_records:
        write_keyword_clusters(themes_dir, processed_records)
        print(f"[OK] 已生成关键词聚类：{themes_dir / 'keyword_clusters_cn.md'}")


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
