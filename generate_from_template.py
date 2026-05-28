"""골든샘플(.hwpx)을 '스타일 원본'으로 삼아 학습지를 재생성한다.

핵심 아이디어: 새 문서를 만들면 글꼴/박스 스타일이 없으므로, 선생님이 만든
골든샘플을 열어 본문만 비우고 같은 글자속성·박스 테두리로 새 내용을 채운다.
=> 글꼴·여백·박스 모양이 원본과 동일하게 보존된다.

실행:
    python3 generate_from_template.py                       # golden_schema.json -> worksheet_styled.hwpx
    python3 generate_from_template.py data.json out.hwpx    # 입력/출력 지정
    python3 generate_from_template.py data.json out.hwpx donor.hwpx
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hwpx import HwpxDocument

# 골든샘플에서 추출한 디자인 토큰(글자속성 ID / 셀 테두리 ID).
# 다른 양식을 원본으로 쓰면 이 값만 그 양식에 맞게 바꾸면 된다.
STYLE = {
    "title": 34,        # 제목
    "goal": 35,         # 학습 목표
    "activity": 12,     # 활동 헤더 (HOP/STEP/JUMP)
    "question": 9,      # 질문(Q)
    "box_border": 4,    # 지문/답안 박스(1x1 표) 셀 테두리
}


def clear_body(doc: HwpxDocument) -> None:
    """섹션 본문을 비운다(최소 1개 단락은 남아야 하므로 마지막 하나는 유지)."""
    for p in list(doc.paragraphs)[:-1][::-1]:
        doc.remove_paragraph(p)


def drop_leading_blank(doc: HwpxDocument) -> None:
    """clear_body 후 맨 위에 남은 빈 단락 제거."""
    paras = list(doc.paragraphs)
    if len(paras) > 1 and not (paras[0].text or "").strip():
        doc.remove_paragraph(paras[0])


def render_passage(doc: HwpxDocument, passage: dict) -> None:
    """지문을 1x1 박스(표) 안에 제목+본문+각주+출처 순으로 넣는다."""
    lines: list[str] = []
    if passage.get("title"):
        lines.append(passage["title"])
    lines.extend(passage.get("body", []))
    for fn in passage.get("footnotes", []):
        lines.append("• " + fn)
    if passage.get("source"):
        lines.append(passage["source"])
    if not lines:
        lines = [""]

    table = doc.add_table(1, 1, border_fill_id_ref=STYLE["box_border"])
    table.set_cell_text(0, 0, lines[0])
    cell = table.cell(0, 0)
    for extra in lines[1:]:
        cell.add_paragraph(extra)


def render(doc: HwpxDocument, data: dict) -> None:
    doc.add_paragraph(data.get("title", ""), char_pr_id_ref=STYLE["title"])
    if data.get("learning_goal"):
        doc.add_paragraph(f"학습 목표: {data['learning_goal']}", char_pr_id_ref=STYLE["goal"])
    doc.add_paragraph("")

    for act in data.get("activities", []):
        header = f"{act.get('label', '')}({act.get('stage', '')}). {act.get('instruction', '')}"
        doc.add_paragraph(header, char_pr_id_ref=STYLE["activity"])

        for passage in act.get("passages", []):
            render_passage(doc, passage)

        for q in act.get("questions", []):
            doc.add_paragraph(f"{q.get('id', '')}. {q.get('text', '')}", char_pr_id_ref=STYLE["question"])
            if q.get("answer_box"):
                doc.add_table(1, 1, border_fill_id_ref=STYLE["box_border"]).set_cell_text(0, 0, "")
        doc.add_paragraph("")


def main() -> None:
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("golden_schema.json")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("worksheet_styled.hwpx")
    donor_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("golden_sample.hwpx")

    data = json.loads(in_path.read_text(encoding="utf-8"))

    doc = HwpxDocument.open(str(donor_path))
    clear_body(doc)
    render(doc, data)
    drop_leading_blank(doc)
    doc.save_to_path(str(out_path))

    HwpxDocument.open(str(out_path)).validate()
    n_act = len(data.get("activities", []))
    n_q = sum(len(a.get("questions", [])) for a in data.get("activities", []))
    print(f"[생성 완료] {out_path}  (활동 {n_act}개 · 문항 {n_q}개)")


if __name__ == "__main__":
    main()
