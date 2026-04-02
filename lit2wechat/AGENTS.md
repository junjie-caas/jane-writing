# AGENTS.md

## 目标
把英文学术文献加工成适合中文公众号发布的高质量内容。

## 固定要求
- 全部输出使用简体中文。
- 不得杜撰数据、结论、样本量、年份。
- 只要出现数字，必须附带原文出处信息（页码+原句）。
- 若无法确认页码或原句，标记为“待人工核实”。
- 先输出结构化JSON，再输出中文摘要，不允许直接跳到公众号成稿。
- 公众号文章风格：专业、清晰、少空话，避免学术腔过重。
- 每篇文章必须保留“局限性/争议”部分。
- 涉及因果判断时，必须区分“相关”与“因果”。

## 目录约定
- `papers_raw/`：原始 PDF，仅存档，不修改。
- `notes_json/`：每篇论文的结构化提取结果（`<paper_id>.json`）。
- `notes_cn/`：每篇论文中文摘要（`<paper_id>.md`）。
- `themes/`：多篇归纳后的主题与证据表。
- `drafts/`：公众号初稿（基于主题聚合后再生成）。
- `prompts/`：固定提示词与模板。

## 建议字段（notes_json）
- `paper_id`
- `title_en`
- `authors`
- `year`
- `doi`
- `sample_size`
- `effect_size_or_main_numbers`
- `key_findings`
- `limitations`
- `causal_claim_level`（`correlation` / `causal` / `unclear`）
- `evidence_spans`（每个数字的出处）

## 质量闸门
- 没有 `evidence_spans` 的数字不得进入中文摘要。
- `limitations` 为空时，摘要必须标记“待人工核实”。
- 出现因果词（如“导致/造成”）时，必须在同段注明证据级别。
