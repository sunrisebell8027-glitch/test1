"""골든샘플(.hwpx)을 '스타일 원본'으로 삼아 학습지를 재생성한다.

핵심 아이디어: 새 문서를 만들면 글꼴/박스/편집용지 설정이 없으므로, 선생님이 만든
골든샘플을 열어 본문만 비우고 같은 스타일로 새 내용을 채운다.

보존/적용 항목:
- 편집용지(여백·용지)·머릿말·꼬리말 : 첫 단락의 secPr를 그대로 보존
- 머릿말 텍스트(과목/단원/학교/학년·반·이름) : 스키마 header 값으로 갱신
- 박스(지문/답안) : 1x1 표, 너비를 본문폭(52160)에 맞춤, 원본 셀 테두리 재사용
- 정렬/글꼴 : 지문 제목=가운데(para23,char14), 본문=양쪽정렬(para22,char10)

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

# 골든샘플에서 추출한 디자인 토큰. 다른 양식을 원본으로 쓰면 이 값만 맞추면 된다.
STYLE = {
    "title": 34,          # 제목 글자속성
    "goal": 35,           # 학습 목표 글자속성
    "activity": 12,       # 활동 헤더(HOP/STEP/JUMP) 글자속성
    "question": 9,        # 질문(Q) 글자속성
    "box_border": 4,      # 지문/답안 박스(1x1 표) 셀 테두리
    "box_width": 52160,   # 박스 너비(본문폭, HWPUNIT) = 용지폭 - 좌우여백
    "passage_title_para": 23,   # 지문 제목 문단속성(가운데 정렬)
    "passage_title_char": 14,   # 지문 제목 글자속성(굵게)
    "passage_body_para": 22,    # 지문 본문 문단속성(양쪽 정렬)
    "passage_body_char": 10,    # 지문 본문 글자속성
    "answer_box_height": 12000, # 답안 박스 기본 높이(HWPUNIT)
    # 전역 서식
    "font_face": "한컴산뜻돋움",   # 모든 폰트 슬롯을 이 글꼴로 통일
    "title_height": 1700,        # 제목 글자 크기(=17pt, 1pt=100). 굵게는 골든샘플 유지
    # 박스(셀) 안쪽 여백(HWPUNIT). 1mm≈283
    "cell_margin": {"left": 540, "right": 540, "top": 340, "bottom": 340},
}


def _wlen(s: str) -> int:
    """한글 등 전각 문자는 2칸으로 세어 머릿말 좌우 간격 계산용 길이를 구한다."""
    return sum(2 if ord(c) > 0x2E7F else 1 for c in s)


def set_header(doc: HwpxDocument, left: str, right: str, total_width: int = 74) -> None:
    """기존 머릿말(secPr 안)을 제자리에서 좌/우 텍스트로 갱신한다.

    set_header_text()는 머릿말을 중복 생성하므로 쓰지 않고, 기존 머릿말의
    텍스트 런만 교체한다. 좌우 배치는 원본과 동일하게 공백으로 처리한다.
    """
    headers = getattr(doc, "headers", None)
    if not headers:
        return
    text_nodes = [n for n in headers[0].element.iter() if n.tag.endswith("}t")]
    if not text_nodes:
        return
    gap = max(4, total_width - _wlen(left) - _wlen(right))
    text_nodes[0].text = f"{left}{' ' * gap}{right}"
    for n in text_nodes[1:]:
        n.text = ""


def clear_body(doc: HwpxDocument) -> None:
    """본문을 비우되 첫 단락은 보존한다(편집용지·머릿말·꼬리말을 담은 secPr 앵커)."""
    for p in list(doc.paragraphs)[1:][::-1]:
        doc.remove_paragraph(p)


def apply_global_styles(doc: HwpxDocument) -> None:
    """문서 header.xml을 편집해 전체 글꼴 통일 + 제목 글자 크기를 설정한다."""
    pkg = doc.package
    root = pkg.get_xml(pkg.HEADER_PATH)
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "font":
            el.set("face", STYLE["font_face"])
        elif tag == "charPr" and el.get("id") == str(STYLE["title"]):
            el.set("height", str(STYLE["title_height"]))
    pkg.set_xml(pkg.HEADER_PATH, root)


def set_cell_margin(cell) -> None:
    """셀 안쪽 여백을 STYLE['cell_margin'] 값으로 설정한다."""
    tc = cell.element
    tc.set("hasMargin", "1")
    m = STYLE["cell_margin"]
    for child in tc:
        if child.tag.split("}")[-1] == "cellMargin":
            child.set("left", str(m["left"]))
            child.set("right", str(m["right"]))
            child.set("top", str(m["top"]))
            child.set("bottom", str(m["bottom"]))
            return


def render_passage(doc: HwpxDocument, passage: dict) -> None:
    """지문을 1x1 박스에 제목(가운데)+본문/각주/출처(양쪽정렬) 순으로 넣는다."""
    lines: list[tuple[str, int, int]] = []
    if passage.get("title"):
        lines.append((passage["title"], STYLE["passage_title_para"], STYLE["passage_title_char"]))
    for body in passage.get("body", []):
        lines.append((body, STYLE["passage_body_para"], STYLE["passage_body_char"]))
    for fn in passage.get("footnotes", []):
        lines.append(("• " + fn, STYLE["passage_body_para"], STYLE["passage_body_char"]))
    if passage.get("source"):
        lines.append((passage["source"], STYLE["passage_body_para"], STYLE["passage_body_char"]))
    if not lines:
        lines = [("", STYLE["passage_body_para"], STYLE["passage_body_char"])]

    table = doc.add_table(1, 1, width=STYLE["box_width"], border_fill_id_ref=STYLE["box_border"])
    cell = table.cell(0, 0)
    first_text, first_para, first_char = lines[0]
    table.set_cell_text(0, 0, first_text)
    p0 = cell.paragraphs[0]
    p0.element.set("paraPrIDRef", str(first_para))
    for run in p0.element:
        if run.tag.split("}")[-1] == "run":
            run.set("charPrIDRef", str(first_char))
    for text, para, char in lines[1:]:
        cell.add_paragraph(text, para_pr_id_ref=para, char_pr_id_ref=char)
    set_cell_margin(cell)


def render_answer_box(doc: HwpxDocument) -> None:
    table = doc.add_table(
        1, 1,
        width=STYLE["box_width"],
        height=STYLE["answer_box_height"],
        border_fill_id_ref=STYLE["box_border"],
    )
    table.set_cell_text(0, 0, "")
    set_cell_margin(table.cell(0, 0))


def render(doc: HwpxDocument, data: dict) -> None:
    header = data.get("header") or {}
    if header.get("left") or header.get("right"):
        set_header(doc, header.get("left", ""), header.get("right", ""))

    doc.add_paragraph(data.get("title", ""), char_pr_id_ref=STYLE["title"])
    if data.get("learning_goal"):
        doc.add_paragraph(f"학습 목표: {data['learning_goal']}", char_pr_id_ref=STYLE["goal"])
    doc.add_paragraph("")

    for act in data.get("activities", []):
        head = f"{act.get('label', '')}({act.get('stage', '')}). {act.get('instruction', '')}"
        doc.add_paragraph(head, char_pr_id_ref=STYLE["activity"])

        for passage in act.get("passages", []):
            render_passage(doc, passage)

        for q in act.get("questions", []):
            doc.add_paragraph(f"{q.get('id', '')}. {q.get('text', '')}", char_pr_id_ref=STYLE["question"])
            if q.get("answer_box"):
                render_answer_box(doc)
        doc.add_paragraph("")


def main() -> None:
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("golden_schema.json")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("worksheet_styled.hwpx")
    donor_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("golden_sample.hwpx")

    data = json.loads(in_path.read_text(encoding="utf-8"))

    doc = HwpxDocument.open(str(donor_path))
    clear_body(doc)
    render(doc, data)
    apply_global_styles(doc)
    doc.save_to_path(str(out_path))

    HwpxDocument.open(str(out_path)).validate()
    n_act = len(data.get("activities", []))
    n_q = sum(len(a.get("questions", [])) for a in data.get("activities", []))
    print(f"[생성 완료] {out_path}  (활동 {n_act}개 · 문항 {n_q}개)")


if __name__ == "__main__":
    main()
