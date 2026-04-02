#!/usr/bin/env python3
"""生成一篇可用于流水线演示的英文示例论文 PDF。"""

from pathlib import Path

import fitz


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    papers_dir = base_dir / "papers_raw"
    papers_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = papers_dir / "demo_agri_policy_paper.pdf"

    doc = fitz.open()
    page = doc.new_page()

    lines = [
        "Impacts of Fertilizer Subsidy on Smallholder Rice Productivity",
        "Lina Chen, David Miller, Hao Zhang",
        "Journal of Agricultural Policy Studies (2024)",
        "DOI: 10.1234/agpolicy.2024.001",
        "Abstract: This study examines whether fertilizer subsidy improves rice yield and household income.",
        "We use a panel dataset from 2018 to 2022 covering 1,240 farm households in three provinces.",
        "Methods: difference-in-differences with household fixed effects and robustness checks.",
        "Results show average yield increased by 8.6% and net income increased by 12.4%.",
        "Policy implication: targeted subsidy design may improve welfare under budget constraints.",
        "Limitation: the sample is concentrated in irrigated areas and may not generalize nationwide.",
    ]

    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 20

    doc.save(pdf_path)
    doc.close()
    print(f"[OK] 已生成示例 PDF: {pdf_path}")


if __name__ == "__main__":
    main()
