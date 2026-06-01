"""'한글로 미리 만든 양식(.hwpx) + 자리표시자 치환' 워크플로 데모.

실제 사용 시나리오:
  1) 선생님이 한글에서 학습지 양식을 디자인하고 {제목}, {과목} 같은 자리표시자를 넣어 .hwpx로 저장
  2) 노션에서 추출한 값으로 그 자리표시자를 치환 -> 완성된 학습지

이 스크립트는 자체 검증을 위해 (1)의 샘플 템플릿을 먼저 만든 뒤 (2)를 수행합니다.
실제로는 make_sample_template() 대신 선생님의 진짜 양식 파일을 열면 됩니다.

실행:
    python3 template_fill_demo.py
"""

from __future__ import annotations

import json
from pathlib import Path

from hwpx import HwpxDocument

TEMPLATE = Path("template.hwpx")
OUTPUT = Path("worksheet_from_template.hwpx")


def make_sample_template() -> None:
    """선생님이 한글에서 만들 법한 양식의 대역. 자리표시자 {key} 를 본문에 심는다."""
    doc = HwpxDocument.new()
    bold = doc.ensure_run_style(bold=True)

    doc.add_paragraph("{제목}", char_pr_id_ref=bold)
    doc.add_paragraph("")

    t = doc.add_table(2, 4)
    t.set_cell_text(0, 0, "과목")
    t.set_cell_text(0, 1, "{과목}")
    t.set_cell_text(0, 2, "학년")
    t.set_cell_text(0, 3, "{학년}")
    t.set_cell_text(1, 0, "단원")
    t.set_cell_text(1, 1, "{단원}")
    t.set_cell_text(1, 2, "날짜")
    t.set_cell_text(1, 3, "{날짜}")
    doc.add_paragraph("")

    doc.add_paragraph("이름: ____________________      지도교사: {선생님}")
    doc.add_paragraph("")
    doc.add_paragraph("※ {안내}", char_pr_id_ref=bold)

    doc.save_to_path(str(TEMPLATE))


def fill_template(data: dict) -> None:
    doc = HwpxDocument.open(str(TEMPLATE))

    values = {
        "제목": data.get("title", ""),
        "과목": data.get("subject", ""),
        "학년": data.get("grade", ""),
        "단원": data.get("unit", ""),
        "날짜": data.get("date", ""),
        "선생님": data.get("teacher", ""),
        "안내": data.get("instructions", ""),
    }

    # 1) 본문 단락의 자리표시자 치환 (제목/안내/지도교사)
    for key in ["제목", "선생님", "안내"]:
        doc.replace_text_in_runs("{" + key + "}", values[key])

    # 2) 표 셀은 라벨 기준으로 채운다 ("과목" 라벨의 오른쪽 셀 등)
    result = doc.fill_by_path({
        "과목 > right": values["과목"],
        "학년 > right": values["학년"],
        "단원 > right": values["단원"],
        "날짜 > right": values["날짜"],
    })
    print(f"      표 채움: {result['applied_count']}칸 적용, {result['failed_count']}칸 실패")

    doc.save_to_path(str(OUTPUT))


def main() -> None:
    data = json.loads(Path("worksheet_data.json").read_text(encoding="utf-8"))

    make_sample_template()
    print(f"[1/2] 샘플 양식 생성: {TEMPLATE}")

    fill_template(data)
    HwpxDocument.open(str(OUTPUT)).validate()
    print(f"[2/2] 자리표시자 치환 완료: {OUTPUT}")
    print("\n=== 결과 미리보기 ===")
    print(HwpxDocument.open(str(OUTPUT)).export_text())


if __name__ == "__main__":
    main()
