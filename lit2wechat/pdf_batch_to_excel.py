#!/usr/bin/env python3
"""批量处理英文 PDF，提取关键信息、翻译并输出 Excel。"""

from __future__ import annotations

import argparse
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF


MISSING_VALUE = "未提取到"

CATEGORY_RULES: dict[str, list[str]] = {
    "粮食安全与作物供给": ["food security", "rice", "wheat", "maize", "grain", "crop supply"],
    "农业政策与补贴": ["subsidy", "support payment", "policy", "government program", "input subsidy"],
    "贸易与市场": ["trade", "tariff", "import", "export", "market integration", "price transmission"],
    "气候变化与韧性": ["climate", "drought", "temperature", "rainfall", "adaptation", "resilience"],
    "农户行为与福利": ["household", "farmer", "welfare", "income", "consumption", "livelihood"],
    "土地与生产率": ["land", "productivity", "yield", "efficiency", "farm size", "technology adoption"],
}


@dataclass
class ArticleRecord:
    filename: str
    title_en: str
    title_zh: str
    keywords_en: str
    keywords_zh: str
    abstract_en: str
    abstract_zh: str
    conclusion_en: str
    conclusion_zh: str
    category_main: str
    category_secondary: str
    extraction_note: str


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def split_chunks(text: str, max_chars: int = 4200) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = []
    current_len = 0
    for sent in sentences:
        if current_len + len(sent) + 1 > max_chars and current:
            chunks.append(" ".join(current))
            current = [sent]
            current_len = len(sent)
        else:
            current.append(sent)
            current_len += len(sent) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


class Translator:
    """简易学术翻译器：术语替换 + 结构化表达（离线可用）。"""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._cache: dict[str, str] = {}
        self._glossary = {
            "abstract": "摘要",
            "conclusion": "结论",
            "conclusions": "结论",
            "keyword": "关键词",
            "keywords": "关键词",
            "agriculture": "农业",
            "agricultural": "农业",
            "food security": "粮食安全",
            "policy": "政策",
            "subsidy": "补贴",
            "trade": "贸易",
            "climate": "气候",
            "farmer": "农户",
            "farmers": "农户",
            "household": "家庭",
            "income": "收入",
            "land": "土地",
            "productivity": "生产率",
            "yield": "产量",
            "market": "市场",
            "welfare": "福利",
            "impact": "影响",
            "effects": "效应",
            "results": "结果",
        }

    def translate(self, text: str) -> str:
        text = clean_spaces(text)
        if not text or text == MISSING_VALUE:
            return MISSING_VALUE
        if not self.enabled:
            return MISSING_VALUE
        if text in self._cache:
            return self._cache[text]
        lowered = text.lower()
        translated = text
        for en, zh in sorted(self._glossary.items(), key=lambda kv: len(kv[0]), reverse=True):
            translated = re.sub(rf"\b{re.escape(en)}\b", zh, translated, flags=re.I)
        has_chinese = bool(re.search(r"[\u4e00-\u9fff]", translated))
        result = f"【自动翻译草案】{clean_spaces(translated)}" if has_chinese else MISSING_VALUE
        self._cache[text] = result
        return result


def extract_title(first_page_text: str) -> str:
    lines = [clean_spaces(line) for line in first_page_text.splitlines() if clean_spaces(line)]
    if not lines:
        return MISSING_VALUE
    for line in lines[:12]:
        m = re.match(r"(?i)^title\s*[:：]\s*(.+)$", line)
        if m:
            return clean_spaces(m.group(1))

    stop_patterns = [r"(?i)^abstract\b", r"(?i)^keywords?\b", r"(?i)^by\b", r"@", r"(?i)^doi\b"]
    title_lines: list[str] = []
    for line in lines[:10]:
        if any(re.search(p, line) for p in stop_patterns):
            break
        if len(line.split()) <= 1:
            continue
        title_lines.append(line)
        if len(title_lines) >= 3:
            break
    return clean_spaces(" ".join(title_lines)) if title_lines else lines[0]


def extract_section_block(text: str, start_patterns: list[str], end_patterns: list[str]) -> str:
    normalized = text.replace("\r\n", "\n")
    start_idx = -1
    for pattern in start_patterns:
        m = re.search(pattern, normalized, flags=re.I)
        if m:
            start_idx = m.end()
            break
    if start_idx == -1:
        return MISSING_VALUE

    tail = normalized[start_idx:]
    end_idx = len(tail)
    for pattern in end_patterns:
        m = re.search(pattern, tail, flags=re.I)
        if m and m.start() < end_idx:
            end_idx = m.start()
    section = clean_spaces(tail[:end_idx])
    return section if section else MISSING_VALUE


def extract_keywords(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n")
    match = re.search(
        r"(?is)\b(keywords?|index terms)\b\s*[:：]?\s*(.+?)(?:\n\s*\n|\n\s*(?:\d+\.?\s*)?(?:introduction|1\.))",
        normalized,
    )
    if not match:
        return []
    raw = clean_spaces(match.group(2))
    if not raw:
        return []
    parts = [p.strip(" .;:,") for p in re.split(r"[;,•·]| and ", raw) if p.strip()]
    unique: list[str] = []
    for part in parts:
        if part.lower() not in [u.lower() for u in unique]:
            unique.append(part)
    return unique


def classify_article(keywords: list[str], abstract_en: str) -> tuple[str, str]:
    corpus = f"{' '.join(keywords)} {abstract_en}".lower()
    if not corpus.strip() or corpus == MISSING_VALUE.lower():
        return "其他主题", MISSING_VALUE

    scores: dict[str, int] = defaultdict(int)
    for category, rules in CATEGORY_RULES.items():
        for token in rules:
            if token in corpus:
                scores[category] += 1
    if not scores:
        return "其他主题", MISSING_VALUE

    sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    main = sorted_cats[0][0]
    secondary = sorted_cats[1][0] if len(sorted_cats) > 1 and sorted_cats[1][1] > 0 else MISSING_VALUE
    return main, secondary


def keyword_core_tokens(records: list[ArticleRecord]) -> str:
    counter: Counter[str] = Counter()
    for rec in records:
        if rec.keywords_en == MISSING_VALUE:
            continue
        parts = [p.strip().lower() for p in re.split(r"[;,]", rec.keywords_en) if p.strip()]
        for part in parts:
            counter[part] += 1
    if not counter:
        return MISSING_VALUE
    return ", ".join([w for w, _ in counter.most_common(8)])


def parse_single_pdf(pdf_path: Path, translator: Translator) -> ArticleRecord:
    notes: list[str] = []
    try:
        with fitz.open(pdf_path) as doc:
            pages = [page.get_text("text") or "" for page in doc]
    except Exception as exc:  # noqa: BLE001
        return ArticleRecord(
            filename=pdf_path.name,
            title_en=MISSING_VALUE,
            title_zh=MISSING_VALUE,
            keywords_en=MISSING_VALUE,
            keywords_zh=MISSING_VALUE,
            abstract_en=MISSING_VALUE,
            abstract_zh=MISSING_VALUE,
            conclusion_en=MISSING_VALUE,
            conclusion_zh=MISSING_VALUE,
            category_main="解析失败",
            category_secondary=MISSING_VALUE,
            extraction_note=f"PDF解析失败：{exc}",
        )

    full_text = "\n".join(pages)
    first_page = pages[0] if pages else ""

    title_en = extract_title(first_page) if first_page else MISSING_VALUE
    keywords_list = extract_keywords(full_text)
    abstract_en = extract_section_block(
        full_text,
        [r"\babstract\b[:\s]*"],
        [r"\bkeywords?\b[:\s]*", r"\bindex terms\b[:\s]*", r"\b1\.?\s*introduction\b", r"\bintroduction\b"],
    )
    conclusion_en = extract_section_block(
        full_text,
        [r"\bconclusions?\b[:\s]*", r"\b5\.?\s*conclusions?\b", r"\b6\.?\s*conclusions?\b"],
        [r"\breferences\b", r"\backnowledg", r"\bappendix\b"],
    )

    if title_en == MISSING_VALUE:
        notes.append("标题未提取到")
    if not keywords_list:
        notes.append("关键词未提取到")
    if abstract_en == MISSING_VALUE:
        notes.append("摘要未提取到")
    if conclusion_en == MISSING_VALUE:
        notes.append("结论未提取到")

    keywords_en = ", ".join(keywords_list) if keywords_list else MISSING_VALUE
    title_zh = translator.translate(title_en)
    keywords_zh = translator.translate(keywords_en)
    abstract_zh = translator.translate(abstract_en)
    conclusion_zh = translator.translate(conclusion_en)

    if translator.enabled is False:
        notes.append("翻译未启用或翻译依赖缺失")
    elif MISSING_VALUE in [title_zh, keywords_zh, abstract_zh, conclusion_zh]:
        notes.append("部分翻译失败")

    category_main, category_secondary = classify_article(keywords_list, abstract_en)
    extraction_note = "；".join(notes) if notes else "提取成功"

    return ArticleRecord(
        filename=pdf_path.name,
        title_en=title_en,
        title_zh=title_zh,
        keywords_en=keywords_en,
        keywords_zh=keywords_zh,
        abstract_en=abstract_en,
        abstract_zh=abstract_zh,
        conclusion_en=conclusion_en,
        conclusion_zh=conclusion_zh,
        category_main=category_main,
        category_secondary=category_secondary,
        extraction_note=extraction_note,
    )


def build_category_summary(records: list[ArticleRecord]) -> list[dict[str, Any]]:
    grouped: dict[str, list[ArticleRecord]] = defaultdict(list)
    for rec in records:
        grouped[rec.category_main].append(rec)

    output: list[dict[str, Any]] = []
    for category, items in sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True):
        output.append(
            {
                "category_name": category,
                "article_count": len(items),
                "filenames": "; ".join([i.filename for i in items]),
                "core_keywords": keyword_core_tokens(items),
            }
        )
    return output


def _column_name(index: int) -> str:
    name = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def write_xlsx(path: Path, rows: list[dict[str, Any]], headers: list[str], sheet_name: str) -> None:
    """最小化 XLSX 写出器（无第三方依赖）。"""

    def cell_xml(row_idx: int, col_idx: int, value: Any) -> str:
        ref = f"{_column_name(col_idx)}{row_idx}"
        val = escape(str(value if value is not None else ""))
        return f'<c r="{ref}" t="inlineStr"><is><t>{val}</t></is></c>'

    all_rows = [headers] + [[r.get(h, "") for h in headers] for r in rows]
    row_xml_parts: list[str] = []
    for r_idx, row_values in enumerate(all_rows, start=1):
        cells = "".join([cell_xml(r_idx, c_idx, val) for c_idx, val in enumerate(row_values, start=1)])
        row_xml_parts.append(f'<row r="{r_idx}">{cells}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(row_xml_parts)}</sheetData>"
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>lit2wechat</Application></Properties>"
    )
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>PDF Summary</dc:title>"
        "<dc:creator>lit2wechat</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        "</cp:coreProperties>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        zf.writestr("docProps/app.xml", app_xml)
        zf.writestr("docProps/core.xml", core_xml)


def run(input_dir: Path, output_dir: Path, enable_translation: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"未在目录中找到 PDF：{input_dir}")

    translator = Translator(enabled=enable_translation)
    records = [parse_single_pdf(pdf, translator) for pdf in pdf_files]
    article_rows = [rec.__dict__ for rec in records]
    category_rows = build_category_summary(records)

    article_path = output_dir / "article_summary.xlsx"
    category_path = output_dir / "category_summary.xlsx"
    write_xlsx(
        article_path,
        article_rows,
        headers=[
            "filename", "title_en", "title_zh", "keywords_en", "keywords_zh",
            "abstract_en", "abstract_zh", "conclusion_en", "conclusion_zh",
            "category_main", "category_secondary", "extraction_note",
        ],
        sheet_name="article_summary",
    )
    write_xlsx(
        category_path,
        category_rows,
        headers=["category_name", "article_count", "filenames", "core_keywords"],
        sheet_name="category_summary",
    )

    print(f"[OK] 已输出逐篇文章信息表：{article_path}")
    print(f"[OK] 已输出分类汇总表：{category_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="批量提取英文 PDF 并输出中文翻译与分类 Excel")
    parser.add_argument("--input-dir", type=Path, required=True, help="PDF 文件夹路径")
    parser.add_argument("--output-dir", type=Path, default=Path("."), help="结果输出目录")
    parser.add_argument(
        "--disable-translation",
        action="store_true",
        help="禁用翻译（仅输出英文提取结果）",
    )
    args = parser.parse_args()

    run(args.input_dir, args.output_dir, enable_translation=not args.disable_translation)


if __name__ == "__main__":
    main()
