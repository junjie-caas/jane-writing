#!/usr/bin/env python3
"""自动生成每日水稻经济热点报告。

功能：
1. 抓取与水稻/稻米经济相关的 RSS 新闻；
2. 按关键词打分并筛选热点；
3. 生成 Markdown 日报，支持定时任务调用。

示例：
    python daily_rice_hotspot_report.py
    python daily_rice_hotspot_report.py --top-n 12 --output-dir reports
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 使用 Google News RSS，避免额外 API Key。
RSS_SOURCES = {
    "中文-水稻经济": "https://news.google.com/rss/search?hl=zh-CN&gl=CN&ceid=CN:zh-Hans&q={query}",
    "中文-粮食政策": "https://news.google.com/rss/search?hl=zh-CN&gl=CN&ceid=CN:zh-Hans&q={query}",
    "英文-Rice Market": "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q={query}",
}

SOURCE_QUERIES = {
    "中文-水稻经济": "水稻 价格 OR 稻米 市场 OR 粮食 供需",
    "中文-粮食政策": "水稻 政策 OR 粮食 安全 OR 最低收购价",
    "英文-Rice Market": "rice price OR rice export OR paddy market",
}

KEYWORD_WEIGHTS = {
    # 政策类
    "政策": 3,
    "最低收购价": 4,
    "补贴": 3,
    "关税": 3,
    "出口禁令": 5,
    "粮食安全": 4,
    # 市场类
    "价格": 4,
    "涨价": 3,
    "下跌": 3,
    "库存": 3,
    "供需": 4,
    "出口": 3,
    "进口": 3,
    "拍卖": 2,
    # 国际类
    "india": 2,
    "thailand": 2,
    "vietnam": 2,
    "el nino": 3,
    "climate": 2,
    # 水稻相关
    "水稻": 2,
    "稻米": 2,
    "rice": 2,
    "paddy": 2,
}


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    published_at: dt.datetime | None
    summary: str
    score: int = 0
    matched_keywords: tuple[str, ...] = ()


def fetch_rss_xml(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_datetime(raw: str | None) -> dt.datetime | None:
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
        if d.tzinfo is None:
            return d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except Exception:
        return None


def parse_rss_items(xml_text: str, source_name: str) -> list[NewsItem]:
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []

    for node in root.findall("./channel/item"):
        title = clean_text(node.findtext("title"))
        link = clean_text(node.findtext("link"))
        desc = clean_text(node.findtext("description"))
        pub_date = parse_datetime(node.findtext("pubDate"))

        if title and link:
            items.append(
                NewsItem(
                    title=title,
                    link=link,
                    source=source_name,
                    published_at=pub_date,
                    summary=desc,
                )
            )
    return items


def score_item(item: NewsItem) -> NewsItem:
    corpus = f"{item.title} {item.summary}".lower()
    matched = []
    score = 0
    for kw, weight in KEYWORD_WEIGHTS.items():
        if kw.lower() in corpus:
            score += weight
            matched.append(kw)

    # 对“当天新闻”有轻微加分
    now = dt.datetime.now(dt.timezone.utc)
    if item.published_at:
        delta_hours = (now - item.published_at).total_seconds() / 3600
        if 0 <= delta_hours <= 24:
            score += 2
        elif 24 < delta_hours <= 72:
            score += 1

    item.score = score
    item.matched_keywords = tuple(matched)
    return item


def dedupe_by_link(items: Iterable[NewsItem]) -> list[NewsItem]:
    seen = set()
    deduped = []
    for item in items:
        key = item.link.split("?")[0]
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def collect_news() -> list[NewsItem]:
    all_items: list[NewsItem] = []
    for source_name, url_tpl in RSS_SOURCES.items():
        query = SOURCE_QUERIES[source_name]
        url = url_tpl.format(query=urllib.parse.quote(query))
        try:
            xml_text = fetch_rss_xml(url)
            items = parse_rss_items(xml_text, source_name)
            all_items.extend(items)
        except Exception as exc:
            print(f"[WARN] 抓取失败: {source_name} ({exc})")
    return dedupe_by_link(all_items)


def format_datetime_zh(d: dt.datetime | None) -> str:
    if d is None:
        return "时间未知"
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_report(items: list[NewsItem], report_date: dt.date, top_n: int) -> str:
    scored = [score_item(x) for x in items]
    scored.sort(key=lambda x: (x.score, x.published_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc)), reverse=True)
    top_items = scored[:top_n]

    keyword_counter = Counter()
    for item in top_items:
        keyword_counter.update(item.matched_keywords)

    headline_lines = [
        f"# 每日水稻经济热点报告（{report_date.isoformat()}）",
        "",
        f"- 抓取条目数：{len(items)}",
        f"- 入选热点数：{len(top_items)}",
        f"- 生成时间（UTC）：{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 今日关键词热度",
    ]

    if keyword_counter:
        for kw, cnt in keyword_counter.most_common(12):
            headline_lines.append(f"- {kw}: {cnt}")
    else:
        headline_lines.append("- 暂无明显热点关键词")

    headline_lines += ["", "## 热点清单", ""]

    if not top_items:
        headline_lines.append("今日未抓取到可用新闻，请检查网络或调整关键词。")
    else:
        for idx, item in enumerate(top_items, start=1):
            short_summary = textwrap.shorten(item.summary, width=120, placeholder="...")
            kw_text = "、".join(item.matched_keywords[:6]) if item.matched_keywords else "无"
            headline_lines.extend(
                [
                    f"### {idx}. {item.title}",
                    f"- 链接：{item.link}",
                    f"- 来源：{item.source}",
                    f"- 发布时间：{format_datetime_zh(item.published_at)}",
                    f"- 热点评分：{item.score}",
                    f"- 命中关键词：{kw_text}",
                    f"- 摘要：{short_summary or '无摘要'}",
                    "",
                ]
            )

    headline_lines += [
        "## 使用建议",
        "- 可将本报告接入 crontab / Windows 任务计划，每日固定时间生成。",
        "- 如需更聚焦中国市场，可在 SOURCE_QUERIES 中增加省级粮食交易中心关键词。",
        "- 若用于正式对外发布，建议人工复核政策与价格数字。",
        "",
    ]

    return "\n".join(headline_lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="自动生成每日水稻经济热点报告")
    parser.add_argument("--top-n", type=int, default=10, help="报告中保留的热点条目数（默认 10）")
    parser.add_argument("--output-dir", type=Path, default=Path("reports"), help="报告输出目录（默认 reports/）")
    parser.add_argument(
        "--date",
        type=str,
        default=dt.date.today().isoformat(),
        help="报告日期（YYYY-MM-DD，默认当天）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        report_date = dt.date.fromisoformat(args.date)
    except ValueError as exc:
        raise SystemExit(f"--date 格式错误，应为 YYYY-MM-DD: {exc}")

    items = collect_news()
    report = build_report(items=items, report_date=report_date, top_n=max(args.top_n, 1))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    filename = args.output_dir / f"rice_hotspots_{report_date.strftime('%Y%m%d')}.md"
    filename.write_text(report, encoding="utf-8")

    print(f"[OK] 报告已生成：{filename}")


if __name__ == "__main__":
    main()
