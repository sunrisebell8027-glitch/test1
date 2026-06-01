"""노션에서 추출한 학습지 데이터(JSON) -> 한글 HWPX 학습지 생성.

양식(레이아웃)은 build_worksheet() 안에 코드로 정의되어 있어 자유롭게 수정할 수 있습니다.
실행:
    python3 generate_worksheet.py                      # worksheet_data.json -> worksheet.hwpx
    python3 generate_worksheet.py data.json out.hwpx   # 입력/출력 직접 지정
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hwpx import HwpxDocument


def build_worksheet(data: dict) -> HwpxDocument:
    doc = HwpxDocument.new()

    bold = doc.ensure_run_style(bold=True)

    total = sum(p.get("points", 0) for p in data.get("problems", []))

    # 1) 제목
    doc.add_paragraph(data.get("title", "학습지"), char_pr_id_ref=bold)
    doc.add_paragraph("")

    # 2) 머리 정보 표 (과목/학년/단원/날짜)
    info = doc.add_table(2, 4)
    info.set_cell_text(0, 0, "과목")
    info.set_cell_text(0, 1, data.get("subject", ""))
    info.set_cell_text(0, 2, "학년")
    info.set_cell_text(0, 3, data.get("grade", ""))
    info.set_cell_text(1, 0, "단원")
    info.set_cell_text(1, 1, data.get("unit", ""))
    info.set_cell_text(1, 2, "날짜")
    info.set_cell_text(1, 3, data.get("date", ""))
    doc.add_paragraph("")

    # 3) 학생 기입란
    doc.add_paragraph(f"이름: ____________________      점수:  ______ / {total}점")
    doc.add_paragraph("")

    # 4) 안내문
    if data.get("instructions"):
        doc.add_paragraph(f"※ {data['instructions']}", char_pr_id_ref=bold)
        doc.add_paragraph("")

    # 5) 문항
    for p in data.get("problems", []):
        num = p.get("number", "")
        points = p.get("points", "")
        ptype = p.get("type", "")
        head = f"{num}. {p.get('question', '')}"
        if points != "":
            head += f"   ({points}점, {ptype})" if ptype else f"   ({points}점)"
        doc.add_paragraph(head, char_pr_id_ref=bold)

        for choice in p.get("choices", []):
            doc.add_paragraph(f"      {choice}")

        # 답안 공간
        doc.add_paragraph("      ▶ 답: ____________________________________________")
        doc.add_paragraph("")

    # 6) 머리말/꼬리말
    teacher = data.get("teacher", "")
    doc.set_header_text(data.get("title", "학습지"))
    doc.set_footer_text(f"{teacher} 선생님" if teacher else "")

    return doc


def main() -> None:
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("worksheet_data.json")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("worksheet.hwpx")

    data = json.loads(in_path.read_text(encoding="utf-8"))
    doc = build_worksheet(data)
    doc.save_to_path(str(out_path))

    # 검증 및 결과 미리보기
    HwpxDocument.open(str(out_path)).validate()
    print(f"[생성 완료] {out_path}  (문항 {len(data.get('problems', []))}개)")


if __name__ == "__main__":
    main()
