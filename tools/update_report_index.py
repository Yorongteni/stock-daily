#!/usr/bin/env python3
"""reports/README.md 에 날짜별 PDF 목록(최신순)을 만든다. 휴대폰에서 보기 편하게."""
import re
from pathlib import Path

d = Path("reports")
pdfs = sorted((p for p in d.glob("*.pdf") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem)), reverse=True)
lines = ["# 매일 시장 리포트 PDF", "", f"총 {len(pdfs)}건 · 최신순", ""]
month = ""
for p in pdfs:
    if p.stem[:7] != month:
        month = p.stem[:7]
        lines += ["", f"## {month[:4]}년 {int(month[5:])}월", ""]
    lines.append(f"- [{p.stem}]({p.name})")
lines += ["", "> 본 리포트는 투자 권유가 아닌 정보 제공 목적입니다."]
(d / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"목록 갱신: {len(pdfs)}건")
