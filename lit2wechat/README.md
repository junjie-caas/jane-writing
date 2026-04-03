# lit2wechat：英文文献转中文公众号内容（自动化项目）

本项目用于批量读取 `papers_raw/` 中的英文论文 PDF，并为每篇文献输出：
1. 结构化 JSON（保存到 `notes_json/`）
2. 中文要点摘要（保存到 `notes_cn/`）
3. 主题标签（写入 JSON 的 `theme_tags` 字段）
4. 基于关键词相似性的分组结果（保存到 `themes/keyword_clusters_cn.md` 与 `themes/keyword_clusters.json`）

## 适用场景
- 领域：农业经济与政策研究
- 读者：研究人员、研究生、政策分析人员
- 重点：核心观点、关键数据、研究方法、局限性、政策启示

## 输出字段（每篇论文）
程序会提取下列字段：
- `title`, `year`, `journal`, `authors`
- `title_en`, `title_zh`, `keywords_en`, `keywords_zh`
- `abstract_en`, `abstract_zh`, `conclusion_en`, `conclusion_zh`
- `question`, `data`, `sample`, `methods`, `findings`
- `key_numbers`, `limitations`, `policy_implications`
- `source_quotes`, `page_refs`, `theme_tags`

> 约束：不杜撰内容；所有数字必须携带出处（页码+英文原句）；若缺失则标记“待人工核实”。

## 安装依赖
在仓库根目录执行：

```bash
python -m pip install -r lit2wechat/requirements.txt
```

## 批量处理命令
在仓库根目录执行：

```bash
python lit2wechat/pipeline.py --base-dir lit2wechat
```

## 按文件夹批量导出 Excel（新增）
在仓库根目录执行：

```bash
python lit2wechat/pdf_batch_to_excel.py --input-dir lit2wechat/papers_raw --output-dir lit2wechat
```

脚本会基于内置学术词汇表生成中文翻译草案，并输出：
- `lit2wechat/article_summary.xlsx`：逐篇文章信息表
- `lit2wechat/category_summary.xlsx`：分类汇总表

若只需抽取英文内容，可禁用翻译：

```bash
python lit2wechat/pdf_batch_to_excel.py --input-dir lit2wechat/papers_raw --output-dir lit2wechat --disable-translation
```

## 演示：用 `papers_raw/` 的一篇示例论文跑通
1) 生成示例 PDF：

```bash
python lit2wechat/make_demo_pdf.py
```

2) 运行批处理：

```bash
python lit2wechat/pipeline.py --base-dir lit2wechat
```

3) 查看输出：
- `lit2wechat/notes_json/*.json`
- `lit2wechat/notes_cn/*.md`
- `lit2wechat/themes/keyword_clusters_cn.md`
- `lit2wechat/themes/keyword_clusters.json`
- 解析失败日志：`lit2wechat/notes_json/failed_records.jsonl`


## 生成跨文献归纳（themes/overview_cn.md）
在仓库根目录执行：

```bash
python lit2wechat/build_overview.py
```

该命令会读取 `notes_json/` 中全部结构化结果，输出：
- 共同主题
- 相互冲突观点
- 最有传播性的关键数据（带出处）
- 公众号写作观点树
- 稳健/边际/争议性结论分层

## 失败处理
- 当 PDF 无法读取或解析异常时，程序会写入 `failed_records.jsonl`，记录文件名和失败原因。

## 注意事项
- 该版本使用启发式规则抽取字段，适合流程打样与批处理基线。
- 对关键数字与政策结论，建议人工复核后再进入公众号终稿。
