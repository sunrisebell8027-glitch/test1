"""골든샘플(.hwpx)을 '스타일 원본'으로 삼아 학습지를 재생성한다.

핵심 아이디어: 새 문서를 만들면 글꼴/박스/편집용지 설정이 없으므로, 선생님이 만든
골든샘플을 열어 본문만 비우고 같은 스타일로 새 내용을 채운다.

보존/적용 항목:
- 편집용지(여백·용지)·머릿말·꼬리말 : 첫 단락의 secPr를 그대로 보존
- 머릿말 텍스트(과목/단원/학교/학년·반·이름) : 스키마 header 값으로 갱신
- 박스(지문/답안) : 1x1 표, 너비를 본문폭(52160)에 맞춤, 원본 셀 테두리 재사용
- 정렬/글꼴 : 지문 제목=가운데(para23,char14), 본문=양쪽정렬(para22,char10)

────────────────────────────────────────────────────────────────────
데이터 구조(스키마) — 노션 등에서 추출한 학습지 내용을 이 형태로 만든다.

{
  "header": { "left": str, "right": str },        # 머릿말 좌/우 (선택)
  "title": str,                                    # 제목 (필수)
  "learning_goal": str,                            # 학습 목표 (선택)
  "activities": [                                  # 활동 목록 (1개 이상)
    {
      "label": str,            # "활동1"
      "stage": str,            # "HOP" | "STEP" | "JUMP"
      "instruction": str,      # 활동 지시문
      "passages": [ <지문> ],   # 박스 지문 0개 이상 (선택)
      "questions": [ <문항> ]   # 문항 0개 이상
    }
  ]
}

<지문> = {
  "title": str | null,         # 지문 제목 (가운데, 본문+1pt)
  "body": [str, ...],          # 문단 목록
  "images": [ {"path"|"url"|"data"(base64): str, "format"?: "png|jpg", "caption"?: str} ],
                               # 이미지: 박스 폭에 맞춰 자동 축소(가로 최대 120mm).
                               # path=로컬파일 / url=다운로드 / data=base64 인코딩 바이트
  "footnotes": [str, ...],     # 각주. "• " 접두가 자동으로 붙음
  "source": str | null         # 출처/안내 (지문 마지막 줄)
}

<문항> = {
  "id": str,                   # "Q1"
  "text": str,                 # 질문 내용
  "box": <지문> | null,         # 문항에 딸린 지문 박스 (예: Q7 고쳐쓰기)
  "answer_box": bool,          # 빈 답안 박스 표시 여부
  "answer_box_height": int|null# 답안 박스 높이(HWPUNIT, 선택)
}
────────────────────────────────────────────────────────────────────

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

import hwpx_picture

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
    "passage_title_height": 1200,  # 지문 박스 제목 크기(=12pt). 본문 11pt보다 1pt 큼
    # 박스(셀) 안쪽 여백(HWPUNIT). 1mm≈283
    "cell_margin": {"left": 540, "right": 540, "top": 340, "bottom": 340},
}


def _validate_passage(passage: object, loc: str, errors: list[str]) -> None:
    if not isinstance(passage, dict):
        errors.append(f"{loc}: 객체(dict)여야 합니다")
        return
    body = passage.get("body", [])
    if not isinstance(body, list) or any(not isinstance(x, str) for x in body):
        errors.append(f"{loc}.body: 문자열 배열이어야 합니다")
    for k in ("footnotes",):
        v = passage.get(k, [])
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            errors.append(f"{loc}.{k}: 문자열 배열이어야 합니다")
    for j, img in enumerate(passage.get("images", []) or []):
        if not isinstance(img, dict):
            errors.append(f"{loc}.images[{j}]: 객체여야 합니다")


def validate_data(data: object) -> None:
    """스키마에 맞는지 검사하고, 어긋나면 위치를 짚어 ValueError를 던진다."""
    errors: list[str] = []
    if not isinstance(data, dict):
        raise ValueError("최상위 데이터는 객체(dict)여야 합니다")
    if not data.get("title"):
        errors.append("title: 제목이 필요합니다")

    activities = data.get("activities")
    if not isinstance(activities, list) or not activities:
        errors.append("activities: 활동이 1개 이상 필요합니다")
    else:
        for i, act in enumerate(activities):
            loc = f"activities[{i}]"
            if not isinstance(act, dict):
                errors.append(f"{loc}: 객체여야 합니다")
                continue
            for key in ("label", "stage", "instruction"):
                if not act.get(key):
                    errors.append(f"{loc}.{key}: 값이 필요합니다")
            for j, p in enumerate(act.get("passages", []) or []):
                _validate_passage(p, f"{loc}.passages[{j}]", errors)
            for j, q in enumerate(act.get("questions", []) or []):
                ql = f"{loc}.questions[{j}]"
                if not isinstance(q, dict):
                    errors.append(f"{ql}: 객체여야 합니다")
                    continue
                if not q.get("id"):
                    errors.append(f"{ql}.id: 값이 필요합니다 (예: 'Q1')")
                if "text" not in q:
                    errors.append(f"{ql}.text: 값이 필요합니다")
                if q.get("box"):
                    _validate_passage(q["box"], f"{ql}.box", errors)

    if errors:
        raise ValueError("데이터 구조 오류:\n - " + "\n - ".join(errors))


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
    heights = {
        str(STYLE["title"]): STYLE["title_height"],
        str(STYLE["passage_title_char"]): STYLE["passage_title_height"],
    }
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "font":
            el.set("face", STYLE["font_face"])
        elif tag == "charPr" and el.get("id") in heights:
            el.set("height", str(heights[el.get("id")]))
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


def _load_image(img: dict) -> tuple[bytes, str] | tuple[None, None]:
    """이미지 dict에서 바이트와 확장자(png/jpg)를 얻는다."""
    import base64
    if img.get("path"):
        p = Path(img["path"])
        if not p.is_file():
            return None, None
        return p.read_bytes(), (img.get("format") or p.suffix.lstrip(".").lower() or "png")
    if "data" in img:
        return base64.b64decode(img["data"]), (img.get("format") or "png")
    if "url" in img:
        from urllib.request import Request, urlopen
        req = Request(img["url"], headers={"User-Agent": "hwpx-worksheet/1.0"})
        with urlopen(req, timeout=15) as r:
            data = r.read()
        fmt = img.get("format")
        if not fmt:
            url = img["url"].lower().split("?", 1)[0]
            fmt = next((e for e in ("png", "jpg", "jpeg", "gif", "bmp") if url.endswith("." + e)), "png")
        return data, ("jpg" if fmt == "jpeg" else fmt)
    return None, None


def render_passage(doc: HwpxDocument, passage: dict) -> None:
    """지문을 1x1 박스에 제목(가운데)+본문/이미지/각주/출처 순으로 채운다."""
    table = doc.add_table(1, 1, width=STYLE["box_width"], border_fill_id_ref=STYLE["box_border"])
    cell = table.cell(0, 0)
    set_cell_margin(cell)
    first_written = False

    def _set_first(text: str, para: int, char: int) -> object:
        nonlocal first_written
        table.set_cell_text(0, 0, text)
        p = cell.paragraphs[0]
        p.element.set("paraPrIDRef", str(para))
        for run in p.element:
            if run.tag.split("}")[-1] == "run":
                run.set("charPrIDRef", str(char))
        first_written = True
        return p

    def add_text(text: str, para: int, char: int) -> None:
        if not first_written:
            _set_first(text, para, char)
        else:
            cell.add_paragraph(text, para_pr_id_ref=para, char_pr_id_ref=char)

    def add_picture(img_bytes: bytes, img_fmt: str) -> None:
        if not first_written:
            p = _set_first("", STYLE["passage_title_para"], STYLE["passage_body_char"])
        else:
            p = cell.add_paragraph(
                "",
                para_pr_id_ref=STYLE["passage_title_para"],
                char_pr_id_ref=STYLE["passage_body_char"],
            )
        hwpx_picture.add_picture_to_paragraph(doc, p, img_bytes, img_fmt, max_width_mm=120)

    if passage.get("title"):
        add_text(passage["title"], STYLE["passage_title_para"], STYLE["passage_title_char"])
    for body in passage.get("body", []):
        add_text(body, STYLE["passage_body_para"], STYLE["passage_body_char"])
    for img in passage.get("images", []) or []:
        data, fmt = _load_image(img)
        if data and fmt:
            add_picture(data, fmt)
        if img.get("caption"):
            add_text(img["caption"], STYLE["passage_title_para"], STYLE["passage_body_char"])
    for fn in passage.get("footnotes", []):
        add_text("• " + fn, STYLE["passage_body_para"], STYLE["passage_body_char"])
    if passage.get("source"):
        add_text(passage["source"], STYLE["passage_body_para"], STYLE["passage_body_char"])
    if not first_written:
        add_text("", STYLE["passage_body_para"], STYLE["passage_body_char"])


def render_answer_box(doc: HwpxDocument, height: int | None = None) -> None:
    table = doc.add_table(
        1, 1,
        width=STYLE["box_width"],
        height=height or STYLE["answer_box_height"],
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
            if q.get("box"):
                render_passage(doc, q["box"])
            if q.get("answer_box"):
                render_answer_box(doc, q.get("answer_box_height"))
        doc.add_paragraph("")


def main() -> None:
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("golden_schema.json")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("worksheet_styled.hwpx")
    donor_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("golden_sample.hwpx")

    data = json.loads(in_path.read_text(encoding="utf-8"))
    validate_data(data)

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
