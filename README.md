# jane-writing

项目已按 `lit2wechat/` 目录组织，用于将英文学术论文加工为中文公众号内容。

## 当前主目录

```text
lit2wechat/
  papers_raw/         # 原始PDF
  notes_json/         # 每篇论文的结构化提取结果（先产出）
  notes_cn/           # 每篇论文的中文摘要（后产出）
  themes/             # 多篇归纳后的主题与数据
  drafts/             # 公众号初稿
  prompts/            # 固定提示词与模板
  AGENTS.md           # 项目规则（硬性约束）
  skills/
    paper_extract/
      SKILL.md
```

## 工作流（强制）
1. 从 `papers_raw/` 提取结构化信息到 `notes_json/`。
2. 仅在 JSON 完整后，生成单篇中文摘要到 `notes_cn/`。
3. 基于多篇摘要归纳 `themes/`。
4. 最后生成 `drafts/` 公众号初稿。

> 禁止跳过 JSON 直接写公众号成稿；所有数字必须附原文出处，缺失时标注“待人工核实”。
