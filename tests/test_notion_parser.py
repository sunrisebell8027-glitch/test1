"""변환기 회귀 테스트: 노션 마크다운 → 스키마 파싱이 깨지지 않는지 확인."""

from __future__ import annotations

import pytest

from notion_to_schema import parse_markdown, extract


def _md(activities: str = "") -> str:
    """공통 머릿말/제목과 함께 활동 본문을 붙여 마크다운 한 줄 묶음을 만든다."""
    return (
        "머리말좌: 국어 5-1\n"
        "머리말우: 칠서초 5학년\n"
        "학습목표: 테스트용 학습 목표.\n"
        f"{activities}"
    )


# ── 머릿말/학습목표/제목 ──────────────────────────────────────────────


def test_header_and_goal_parsed():
    data = parse_markdown(_md(), title="제목")
    assert data["title"] == "제목"
    assert data["header"] == {"left": "국어 5-1", "right": "칠서초 5학년"}
    assert data["learning_goal"] == "테스트용 학습 목표."


def test_extract_wrapper_pulls_title_and_body():
    src = (
        '<properties>\n{"title":"T"}\n</properties>\n'
        "<content>\n머리말좌: A\n## 활동1(HOP). x\n</content>\n"
    )
    title, body = extract(src)
    assert title == "T"
    assert "## 활동1(HOP). x" in body
    assert "<content>" not in body


def test_extract_raw_markdown_returns_as_is():
    title, body = extract("머리말좌: A\n## 활동1(HOP). x\n")
    assert title == ""
    assert body.startswith("머리말좌:")


# ── 활동 헤더 파싱 ───────────────────────────────────────────────────


def test_activity_label_stage_instruction():
    md = _md("## 활동1(HOP). 아래 글을 읽고 답하시오.\nQ1. 첫 질문\n")
    data = parse_markdown(md)
    act = data["activities"][0]
    assert act["label"] == "활동1"
    assert act["stage"] == "HOP"
    assert act["instruction"] == "아래 글을 읽고 답하시오."


def test_multiple_activities_separated():
    md = _md(
        "## 활동1(HOP). 첫 지시문\nQ1. q1\n"
        "## 활동2(STEP). 둘째 지시문\nQ2. q2\n"
    )
    data = parse_markdown(md)
    stages = [a["stage"] for a in data["activities"]]
    assert stages == ["HOP", "STEP"]


# ── 지문 박스(### + >) ───────────────────────────────────────────────


def test_passage_title_body_footnote_source():
    md = _md(
        "## 활동1(HOP). x\n"
        "### 함안에 다녀와서\n"
        "> 본문 첫 줄\n"
        "> 본문 둘째 줄\n"
        "> • 용어: 뜻 설명\n"
        "> 출처: 어디서\n"
        "Q1. 질문\n"
    )
    p = parse_markdown(md)["activities"][0]["passages"][0]
    assert p["title"] == "함안에 다녀와서"
    assert p["body"] == ["본문 첫 줄", "본문 둘째 줄"]
    assert p["footnotes"] == ["용어: 뜻 설명"]
    assert p["source"].startswith("출처:")


def test_two_adjacent_passages_split_by_h3():
    """인접 인용블록이 ### 헤딩으로 분리되어 별도 박스가 되어야 함."""
    md = _md(
        "## 활동2(STEP). x\n"
        "### 박스 A\n> a 본문\n"
        "### 박스 B\n> b 본문\n"
        "Q3. q\n"
    )
    passages = parse_markdown(md)["activities"][0]["passages"]
    assert [p["title"] for p in passages] == ["박스 A", "박스 B"]
    assert passages[0]["body"] == ["a 본문"]
    assert passages[1]["body"] == ["b 본문"]


# ── 문항/답안박스/부속박스 ────────────────────────────────────────────


def test_question_with_answer_marker():
    md = _md("## 활동3(JUMP). x\nQ6. 좋은 글은? #답안\n")
    q = parse_markdown(md)["activities"][0]["questions"][0]
    assert q["id"] == "Q6"
    assert q["answer_box"] is True
    assert "#답안" not in q["text"]


def test_question_followed_by_box_attaches_as_box():
    md = _md(
        "## 활동3(JUMP). x\n"
        "Q7. 고쳐 써 봅시다.\n"
        "### 함안에 다녀와서\n"
        "> 한 줄\n"
    )
    act = parse_markdown(md)["activities"][0]
    assert act["passages"] == []  # 박스가 활동 지문이 아님
    q = act["questions"][0]
    assert q["box"]["title"] == "함안에 다녀와서"
    assert q["box"]["body"] == ["한 줄"]


def test_passage_before_first_question_belongs_to_activity():
    md = _md(
        "## 활동1(HOP). x\n"
        "### 활동 박스\n> 활동 본문\n"
        "Q1. 첫 질문\n"
    )
    act = parse_markdown(md)["activities"][0]
    assert len(act["passages"]) == 1
    assert act["passages"][0]["title"] == "활동 박스"
    assert act["questions"][0].get("box") is None


# ── 이미지 마크다운 ───────────────────────────────────────────────────


def test_image_inside_quote_attaches_to_passage():
    md = _md(
        "## 활동1(HOP). x\n"
        "### 함안에 다녀와서\n"
        "> 본문\n"
        '> ![alt](https://example.com/h.jpg "그림 1. 함안")\n'
        "Q1. q\n"
    )
    p = parse_markdown(md)["activities"][0]["passages"][0]
    assert p["images"] == [{"url": "https://example.com/h.jpg", "caption": "그림 1. 함안"}]


def test_standalone_image_attaches_to_passage_when_present():
    md = _md(
        "## 활동1(HOP). x\n"
        "### 박스\n"
        "> 본문\n"
        "![캡션](https://example.com/x.png)\n"
        "Q1. q\n"
    )
    p = parse_markdown(md)["activities"][0]["passages"][0]
    assert p["images"][0]["url"] == "https://example.com/x.png"
    assert p["images"][0]["caption"] == "캡션"


# ── 종합 골든 케이스 ─────────────────────────────────────────────────


def test_golden_notion_page_counts():
    """notion_page.md 의 기본 구조가 변환기 출력과 일치."""
    from pathlib import Path

    md = Path("notion_page.md").read_text(encoding="utf-8")
    title, body = extract(md)
    data = parse_markdown(body, title)
    assert data["title"] == "1. OO문의 특성에 대해 알아봅시다"
    assert len(data["activities"]) == 3
    n_q = sum(len(a["questions"]) for a in data["activities"])
    assert n_q == 6
    # Q6 답안박스, Q7 부속박스
    q6 = next(q for a in data["activities"] for q in a["questions"] if q["id"] == "Q6")
    q7 = next(q for a in data["activities"] for q in a["questions"] if q["id"] == "Q7")
    assert q6["answer_box"] is True
    assert q7.get("box") is not None
