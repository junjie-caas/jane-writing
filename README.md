# jane-writing

本仓库当前仅保留 `lit2wechat/` 主流程，用于将英文学术论文加工为适合中文公众号发布的内容。

## 仓库结构

```text
lit2wechat/
  AGENTS.md                 # 硬性规则
  papers_raw/               # 原始 PDF（输入）
  notes_json/               # 结构化提取结果（第一产物）
  notes_cn/                 # 单篇中文摘要（第二产物）
  themes/                   # 多篇归纳结果
  drafts/                   # 公众号草稿
  prompts/                  # 模板与提示词
  pipeline.py               # 批处理入口：PDF -> JSON + 中文摘要
  build_overview.py         # 汇总入口：notes_json -> themes/overview_cn.md
```

## 流程梳理（执行顺序）

1. 将论文 PDF 放入 `lit2wechat/papers_raw/`。
2. 执行批处理：`python lit2wechat/pipeline.py --base-dir lit2wechat`
   - 输出结构化结果到 `notes_json/`
   - 输出单篇中文摘要到 `notes_cn/`
3. 执行跨文献归纳：`python lit2wechat/build_overview.py`
   - 输出 `themes/overview_cn.md`
4. 在 `themes/` 基础上再写 `drafts/` 公众号草稿。

## 质量约束（摘要）

- 禁止跳过 `notes_json` 直接写公众号成稿。
- 所有数字必须有出处（页码 + 原句）；缺失则标记“待人工核实”。
- 必须保留“局限性/争议”并区分“相关”与“因果”。

## 国家粮食和物资储备局收购数据表（新增）

已新增自动整理脚本：

- 脚本：`tools/lswz_scraper.py`
- 输出：
  - `data/lswz_purchase_data.csv`
  - `data/lswz_purchase_data.md`
- 目标页面：`https://www.lswz.gov.cn/html/zmhd/lysj/lssg-szym.shtml`

本地手动更新命令：

```bash
python tools/lswz_scraper.py --out-csv data/lswz_purchase_data.csv --out-md data/lswz_purchase_data.md
```

每周自动更新：

- 已配置 GitHub Actions：`.github/workflows/lswz_weekly_update.yml`
- 定时规则：每周一 `02:00 UTC` 自动运行
- 也可在 Actions 页手动触发（`workflow_dispatch`）
