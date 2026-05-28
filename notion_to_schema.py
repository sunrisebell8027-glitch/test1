"""노션 페이지(마크다운) -> 학습지 스키마(JSON) 변환.

▣ 노션 작성 규칙 (이대로 노션에 작성하면 자동 변환됨)
- 페이지 제목               → 학습지 제목
- `머리말좌: ...`           → 머릿말 좌측 (과목/단원)
- `머리말우: ...`           → 머릿말 우측 (학교/학년·반·이름)
- `학습목표: ...`          → 학습 목표
- `## 활동N(STAGE). 지시문` → 활동.  예) `## 활동1(HOP). 아래 글을 읽고 ...`
- `### 지문제목`            → 지문 박스 시작(제목)
-   `> 본문`                → 지문 본문 문단(여러 줄 가능)
-   `> • 용어: 뜻`          → 각주(`•`)
-   `> 출처: ...`           → 출처
- `QN. 질문`               → 문항.  예) `Q1. 위의 글을 뭐라고 부를까요?`
-   질문 끝에 `#답안`        → 빈 답안 박스 표시
-   질문 '뒤'의 `###`+`>` 박스 → 그 문항에 딸린 지문 박스(예: Q7 고쳐쓰기)

같은 활동 안에서 첫 질문 '앞'에 나온 박스는 활동 지문, 질문 '뒤'에 나온 박스는
그 질문의 부속 박스로 분류된다.

실행:
    python3 notion_to_schema.py notion_page.md notion_schema.json

입력 파일은 notion-fetch 결과(<properties>/<content> 래퍼 포함) 또는 순수 마크다운 모두 허용.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

Q_RE = re.compile(r"Q\d+\.")
ACT_RE = re.compile(r"##\s*(.+?)\((\w+)\)\.\s*(.*)")


def extract(fetched: str) -> tuple[str, str]:
    """notion-fetch 래퍼에서 제목/본문을 분리. 래퍼가 없으면 전체를 본문으로 본다."""
    title = ""
    m = re.search(r"<properties>\s*(\{.*?\})\s*</properties>", fetched, re.S)
    if m:
        try:
            title = json.loads(m.group(1)).get("title", "")
        except json.JSONDecodeError:
            pass
    cm = re.search(r"<content>\n?(.*?)\n?</content>", fetched, re.S)
    return title, (cm.group(1) if cm else fetched)


def _clean(s: str) -> str:
    return s.replace("\\*", "*").replace("\\_", "_").strip()


def _new_passage(title: str | None) -> dict:
    return {"title": title, "body": [], "footnotes": [], "images": [], "source": None}


def parse_markdown(md: str, title: str = "") -> dict:
    data: dict = {"header": {}, "title": title, "learning_goal": "", "activities": []}
    act: dict | None = None
    passage: dict | None = None
    target: tuple[str, dict | None] = ("activity", None)
    last_q: dict | None = None

    def flush() -> None:
        nonlocal passage
        if passage is None:
            return
        kind, qref = target
        if kind == "question" and qref is not None:
            qref["box"] = passage
        elif act is not None:
            act["passages"].append(passage)
        passage = None

    for raw in md.splitlines():
        s = raw.strip()
        if not s:
            continue

        if s.startswith("머리말좌:"):
            data["header"]["left"] = s.split(":", 1)[1].strip()
        elif s.startswith("머리말우:"):
            data["header"]["right"] = s.split(":", 1)[1].strip()
        elif s.startswith("학습목표:"):
            data["learning_goal"] = s.split(":", 1)[1].strip()
        elif s.startswith("## "):
            flush()
            m = ACT_RE.match(s)
            if m:
                act = {"label": m.group(1).strip(), "stage": m.group(2).strip(),
                       "instruction": m.group(3).strip(), "passages": [], "questions": []}
            else:
                act = {"label": s[3:].strip(), "stage": "", "instruction": "",
                       "passages": [], "questions": []}
            data["activities"].append(act)
            last_q = None
        elif s.startswith("### "):
            flush()
            passage = _new_passage(_clean(s[4:]))
            target = ("question", last_q) if last_q is not None else ("activity", None)
        elif s.startswith(">"):
            if passage is None:
                passage = _new_passage(None)
                target = ("question", last_q) if last_q is not None else ("activity", None)
            content = _clean(s[1:])
            if content.startswith("•"):
                passage["footnotes"].append(content[1:].strip())
            elif content.startswith("출처"):
                passage["source"] = content
            else:
                passage["body"].append(content)
        elif Q_RE.match(s):
            flush()
            text, answer_box = s, False
            if "#답안" in text:
                answer_box = True
                text = text.replace("#답안", "").strip()
            qid, qtext = text.split(".", 1)
            last_q = {"id": qid.strip(), "text": qtext.strip(), "answer_box": answer_box}
            if act is not None:
                act["questions"].append(last_q)
        else:
            # 그 외 문단: 진행 중인 지문이 있으면 본문에 이어붙인다.
            if passage is not None:
                passage["body"].append(_clean(s))

    flush()
    return data


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python3 notion_to_schema.py <notion_page.md> [out.json]")
        sys.exit(1)
    src = Path(sys.argv[1]).read_text(encoding="utf-8")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("notion_schema.json")

    title, body = extract(src)
    data = parse_markdown(body, title)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    n_act = len(data["activities"])
    n_q = sum(len(a["questions"]) for a in data["activities"])
    print(f"[변환 완료] {out}  (제목: {data['title']!r} · 활동 {n_act}개 · 문항 {n_q}개)")


if __name__ == "__main__":
    main()
