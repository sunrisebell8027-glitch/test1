"""한 줄로 노션 마크다운(또는 URL) → 한글(.hwpx) 학습지를 만든다.

기본 사용:
    python3 build.py --md notion_page.md             # -> worksheet.hwpx
    python3 build.py --md notion_page.md -o out.hwpx
    python3 build.py --md notion_page.md --max-image-mm 100

노션 URL 자동 fetch (NOTION_TOKEN 환경변수 필요, 공식 통합 발급 후 페이지 공유):
    export NOTION_TOKEN=secret_xxxxx
    python3 build.py --url https://www.notion.so/...

처리 흐름:
    1. 입력 마크다운 확보 (파일 또는 노션 API)
    2. notion_to_schema.parse_markdown   -> 스키마(JSON)
    3. generate_from_template.render     -> HWPX (이미지 URL은 그 자리에서 다운로드)
    4. HwpxDocument.validate             -> 구조 검증
    5. 통계 출력

종료 코드: 검증 실패/스키마 오류 시 1, 정상 0.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from hwpx import HwpxDocument

from generate_from_template import (
    STYLE,
    apply_global_styles,
    clear_body,
    render,
    validate_data,
)
from notion_to_schema import extract, parse_markdown


# ── 노션 API 어댑터 (NOTION_TOKEN 사용; 선택 기능) ─────────────────


def _extract_page_id(url_or_id: str) -> str:
    """노션 URL/ID에서 32자리 페이지 ID를 추출.

    URL은 `…/Title-<32hex>` 또는 `…/<32hex>?…` 형태이므로
    쿼리스트링·앞 경로를 떼어내고 마지막 세그먼트 끝의 32-hex 를 잡는다.
    제목 슬러그에 hex 글자가 우연히 끼어 있어도 끝쪽 ID 만 정확히 가져온다.
    """
    s = url_or_id.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1].replace("-", "")
    m = re.search(r"[0-9a-fA-F]{32}$", s)
    if not m:
        raise SystemExit(f"노션 URL에서 페이지 ID를 찾을 수 없습니다: {url_or_id}")
    return m.group(0)


def fetch_notion_markdown(url_or_id: str, token: str) -> tuple[str, str]:
    """노션 공식 API로 페이지 제목과 본문 블록을 마크다운에 가깝게 가져온다.

    notion-fetch (MCP) 와 100% 동일하지는 않으나, 같은 작성 규칙
    (## 활동, ### 지문제목, > 본문, QN. 질문)에 맞춰 직렬화한다.
    """
    page_id = _extract_page_id(url_or_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
    }
    # 1) 페이지 메타(제목)
    req = urllib.request.Request(
        f"https://api.notion.com/v1/pages/{page_id}", headers=headers,
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        page = json.loads(r.read())
    title = ""
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            title = "".join(rt.get("plain_text", "") for rt in prop.get("title", []))
            break

    # 2) 자식 블록 평탄 순회 (1단 깊이로 충분; 더 깊은 중첩은 드묾)
    def _children(block_id: str) -> list[dict]:
        out: list[dict] = []
        start = None
        while True:
            qs = f"?start_cursor={start}" if start else ""
            req2 = urllib.request.Request(
                f"https://api.notion.com/v1/blocks/{block_id}/children{qs}",
                headers=headers,
            )
            with urllib.request.urlopen(req2, timeout=15) as r:
                data = json.loads(r.read())
            out.extend(data.get("results", []))
            if not data.get("has_more"):
                return out
            start = data.get("next_cursor")

    def _rich(rt_list: list[dict]) -> str:
        return "".join(rt.get("plain_text", "") for rt in (rt_list or []))

    lines: list[str] = []
    for b in _children(page_id):
        t = b["type"]
        d = b[t]
        if t == "paragraph":
            lines.append(_rich(d.get("rich_text", [])))
        elif t == "heading_2":
            lines.append("## " + _rich(d["rich_text"]))
        elif t == "heading_3":
            lines.append("### " + _rich(d["rich_text"]))
        elif t == "quote":
            lines.append("> " + _rich(d["rich_text"]))
        elif t == "image":
            kind = d.get("type")
            url = d.get(kind, {}).get("url", "")
            cap = _rich(d.get("caption", []))
            lines.append(f"![{cap}]({url})")
    return title, "\n".join(lines)


# ── 메인 파이프라인 ───────────────────────────────────────────────


def load_markdown(args: argparse.Namespace) -> tuple[str, str]:
    """입력 옵션에 따라 (title, markdown body) 를 돌려준다."""
    if args.md:
        src = Path(args.md).read_text(encoding="utf-8")
        return extract(src)
    if args.url:
        token = os.environ.get("NOTION_TOKEN")
        if not token:
            raise SystemExit(
                "--url 사용 시 환경변수 NOTION_TOKEN 이 필요합니다.\n"
                "  1) https://www.notion.so/profile/integrations 에서 통합 생성\n"
                "  2) 노션 페이지를 그 통합에 공유\n"
                "  3) export NOTION_TOKEN=secret_xxxxx"
            )
        try:
            return fetch_notion_markdown(args.url, token)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"노션 API 오류 {e.code}: {e.read().decode(errors='replace')[:200]}")
    raise SystemExit("--md <파일> 또는 --url <노션URL> 중 하나는 지정해야 합니다.")


def build(args: argparse.Namespace) -> dict:
    title, body = load_markdown(args)
    data = parse_markdown(body, title)
    validate_data(data)

    # 박스 폭 한도(이미지 자동 축소) 옵션 적용
    if args.max_image_mm:
        import hwpx_picture
        original = hwpx_picture.add_picture_to_paragraph

        def _patched(*a, **kw):
            kw["max_width_mm"] = args.max_image_mm
            return original(*a, **kw)

        hwpx_picture.add_picture_to_paragraph = _patched

    donor = args.donor or "golden_sample.hwpx"
    if not Path(donor).is_file():
        raise SystemExit(f"기증자 HWPX 가 없습니다: {donor}")

    doc = HwpxDocument.open(donor)
    clear_body(doc)
    render(doc, data)
    apply_global_styles(doc)
    doc.save_to_path(args.out)

    HwpxDocument.open(args.out).validate()
    return data


def stats(data: dict) -> str:
    n_act = len(data.get("activities", []))
    n_q = sum(len(a.get("questions", [])) for a in data.get("activities", []))
    n_box = sum(
        len(a.get("passages", [])) + sum(1 for q in a.get("questions", []) if q.get("box"))
        for a in data.get("activities", [])
    )
    n_ans = sum(1 for a in data.get("activities", []) for q in a.get("questions", []) if q.get("answer_box"))
    n_img = sum(
        len(p.get("images", []) or []) for a in data.get("activities", []) for p in a.get("passages", [])
    ) + sum(
        len((q.get("box") or {}).get("images", []) or [])
        for a in data.get("activities", []) for q in a.get("questions", [])
    )
    return (
        f"활동 {n_act}개 · 문항 {n_q}개 · 박스 {n_box}개 · 답안박스 {n_ans}개 · 이미지 {n_img}개"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="build.py",
        description="노션 마크다운(또는 URL)에서 한 줄로 한글 학습지 생성",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--md", metavar="FILE", help="노션에서 fetch한 마크다운 파일")
    src.add_argument("--url", metavar="URL", help="노션 페이지 URL(NOTION_TOKEN 필요)")
    p.add_argument("-o", "--out", default="worksheet.hwpx", help="출력 HWPX 경로 (기본: worksheet.hwpx)")
    p.add_argument("--donor", default=None, help="기증자 HWPX (기본: golden_sample.hwpx)")
    p.add_argument("--max-image-mm", type=float, default=None,
                   help="박스 안 이미지 최대 가로(mm). 기본 120mm")
    p.add_argument("--schema-out", metavar="FILE", default=None,
                   help="중간 스키마(JSON)도 함께 저장")
    args = p.parse_args(argv)

    try:
        data = build(args)
    except ValueError as e:
        print(f"[스키마 오류]\n{e}", file=sys.stderr)
        return 1

    if args.schema_out:
        Path(args.schema_out).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
        )

    size_kb = Path(args.out).stat().st_size / 1024
    print(f"[완료] {args.out}  ({size_kb:,.0f} KB)  {stats(data)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
