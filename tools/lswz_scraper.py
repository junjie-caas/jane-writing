#!/usr/bin/env python3
"""抓取国家粮食和物资储备局“收购数据”列表并导出 CSV/Markdown 表格。"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import List

SOURCE_URL = "https://www.lswz.gov.cn/html/zmhd/lysj/lssg-szym.shtml"


@dataclass
class Record:
    title: str
    publish_date: str
    detail_url: str


class PurchaseListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_li = False
        self.current_href = ""
        self.current_anchor_text: List[str] = []
        self.current_li_text: List[str] = []
        self.records: List[Record] = []
        self.in_a = False

    def handle_starttag(self, tag: str, attrs):
        if tag == "li":
            self.in_li = True
            self.current_href = ""
            self.current_anchor_text = []
            self.current_li_text = []
            return
        if self.in_li and tag == "a":
            self.in_a = True
            attr_dict = dict(attrs)
            self.current_href = attr_dict.get("href", "")

    def handle_data(self, data: str):
        if not self.in_li:
            return
        cleaned = data.strip()
        if not cleaned:
            return
        self.current_li_text.append(cleaned)
        if self.in_a:
            self.current_anchor_text.append(cleaned)

    def handle_endtag(self, tag: str):
        if tag == "a":
            self.in_a = False
            return

        if tag != "li" or not self.in_li:
            return

        li_text = " ".join(self.current_li_text)
        title = " ".join(self.current_anchor_text).strip()
        date_match = re.search(r"(20\d{2}-\d{2}-\d{2})", li_text)

        if title and date_match and ("收购" in title or "主产区" in title):
            href = self.current_href.strip()
            detail = urllib.parse.urljoin(SOURCE_URL, href) if href else ""
            self.records.append(
                Record(title=title, publish_date=date_match.group(1), detail_url=detail)
            )

        self.in_li = False
        self.current_href = ""
        self.current_anchor_text = []
        self.current_li_text = []


def fetch_html(url: str, timeout: int) -> str:
    req = urllib.request.Request(
        url=url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; lswz-weekly-updater/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read()
    return content.decode("utf-8", errors="ignore")


def parse_records(page_html: str) -> List[Record]:
    parser = PurchaseListParser()
    parser.feed(page_html)

    uniq = {}
    for row in parser.records:
        uniq[(row.title, row.publish_date)] = row

    records = list(uniq.values())
    records.sort(key=lambda x: x.publish_date, reverse=True)
    return records


def write_csv(records: List[Record], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["标题", "发布日期", "详情链接"])
        for r in records:
            writer.writerow([r.title, r.publish_date, r.detail_url])


def write_markdown(records: List[Record], path: Path, source_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# 国家粮食和物资储备局收购数据（自动整理）",
        "",
        f"- 数据来源：{source_url}",
        f"- 生成时间：{generated_at}",
        f"- 记录数：{len(records)}",
        "",
        "| 标题 | 发布日期 | 详情链接 |",
        "|---|---|---|",
    ]
    for r in records:
        title = html.escape(r.title)
        lines.append(f"| {title} | {r.publish_date} | [查看]({r.detail_url}) |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 lswz 收购数据列表")
    parser.add_argument("--url", default=SOURCE_URL, help="目标页面 URL")
    parser.add_argument(
        "--out-csv", default="data/lswz_purchase_data.csv", help="CSV 输出路径"
    )
    parser.add_argument(
        "--out-md", default="data/lswz_purchase_data.md", help="Markdown 输出路径"
    )
    parser.add_argument("--timeout", type=int, default=30, help="请求超时（秒）")
    parser.add_argument(
        "--html-file",
        default="",
        help="从本地 HTML 文件读取（用于离线调试）；若为空则在线抓取",
    )
    args = parser.parse_args()

    if args.html_file:
        raw_html = Path(args.html_file).read_text(encoding="utf-8", errors="ignore")
    else:
        raw_html = fetch_html(args.url, timeout=args.timeout)

    records = parse_records(raw_html)
    if not records:
        raise RuntimeError("未解析到任何收购数据记录，请检查页面结构是否变化。")

    write_csv(records, Path(args.out_csv))
    write_markdown(records, Path(args.out_md), args.url)
    print(f"已输出 {len(records)} 条记录到 {args.out_csv} 和 {args.out_md}")


if __name__ == "__main__":
    main()
