# paper_extract skill

## 用途
将单篇英文论文从 PDF 转换为：
1) 结构化 JSON（先产出）
2) 中文摘要（后产出）

## 强制流程（不可跳步）
1. 提取 metadata：title/authors/year/doi。
2. 提取数字证据：样本量、关键结果数字、置信区间/显著性（若有）。
3. 为每个数字写入出处：页码 + 原句（英文）。
4. 生成 `notes_json/<paper_id>.json`。
5. 仅在 JSON 完整后，生成 `notes_cn/<paper_id>.md`。

## JSON 最小结构
```json
{
  "paper_id": "...",
  "title_en": "...",
  "authors": ["..."],
  "year": 2024,
  "doi": "...",
  "key_findings": ["..."],
  "limitations": ["..."],
  "causal_claim_level": "correlation",
  "evidence_spans": [
    {
      "claim": "...",
      "number": "...",
      "page": "12",
      "quote_en": "..."
    }
  ]
}
```

## 中文摘要要求
- 全文简体中文。
- 必须包含“局限性/争议”小节。
- 涉及因果判断时，明确写“相关”或“因果”。
- 若页码或原句缺失，直接标注“待人工核实”。
- 不直接生成公众号成稿，只生成单篇摘要。
