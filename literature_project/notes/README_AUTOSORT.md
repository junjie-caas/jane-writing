# 文献整理自动化脚本说明

1. 将待整理文献PDF放入 papers_raw 目录。
2. 运行 scripts/paper_organizer.py，会自动：
   - 提取元数据并统���命名拷贝到 papers_text/
   - 生成 literature_list.csv 和 literature_list.xlsx（包含元数据/去重信息）
   - 去重标记 duplicate 字段为 True

依赖：pymupdf、pandas。