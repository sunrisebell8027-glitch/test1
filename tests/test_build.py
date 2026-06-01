"""build.py CLI 회귀 테스트: 한 줄 명령이 전체 파이프라인을 묶는지 확인."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from build import _extract_page_id, stats


# ── 페이지 ID 추출 ───────────────────────────────────────────────────


def test_extract_page_id_from_full_url():
    url = "https://www.notion.so/workspace/Title-36e1960d406c81e89f09f3cc62110ad0"
    assert _extract_page_id(url) == "36e1960d406c81e89f09f3cc62110ad0"


def test_extract_page_id_from_dashed_id():
    assert _extract_page_id("36e1960d-406c-81e8-9f09-f3cc62110ad0") == "36e1960d406c81e89f09f3cc62110ad0"


def test_extract_page_id_rejects_garbage():
    with pytest.raises(SystemExit):
        _extract_page_id("https://example.com/no-id-here")


# ── 통계 출력 ────────────────────────────────────────────────────────


def test_stats_counts_boxes_and_answer_boxes():
    data = {
        "activities": [
            {"passages": [{"images": [{"url": "x"}]}],
             "questions": [
                {"id": "Q1", "answer_box": True},
                {"id": "Q2", "box": {"images": [{"url": "y"}, {"url": "z"}]}},
             ]},
        ],
    }
    s = stats(data)
    assert "활동 1개" in s
    assert "문항 2개" in s
    assert "박스 2개" in s          # 활동 지문 1 + 문항 부속 박스 1
    assert "답안박스 1개" in s
    assert "이미지 3개" in s        # 1 + 2


# ── end-to-end CLI ───────────────────────────────────────────────────


def _run(*args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "build.py", *args]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=".")


def test_cli_md_to_hwpx(tmp_path):
    out = tmp_path / "w.hwpx"
    r = _run("--md", "notion_page.md", "-o", str(out))
    assert r.returncode == 0, r.stderr
    assert out.is_file() and out.stat().st_size > 1000
    assert "활동 3개" in r.stdout


def test_cli_schema_out(tmp_path):
    out = tmp_path / "w.hwpx"
    schema = tmp_path / "s.json"
    r = _run("--md", "notion_page.md", "-o", str(out), "--schema-out", str(schema))
    assert r.returncode == 0, r.stderr
    data = json.loads(schema.read_text(encoding="utf-8"))
    assert data["title"] == "1. OO문의 특성에 대해 알아봅시다"


def test_cli_rejects_empty_input(tmp_path):
    empty = tmp_path / "e.md"
    empty.write_text("", encoding="utf-8")
    r = _run("--md", str(empty), "-o", str(tmp_path / "x.hwpx"))
    assert r.returncode == 1
    assert "스키마 오류" in r.stderr


def test_cli_requires_input_mode():
    r = _run()
    assert r.returncode != 0


def test_cli_url_without_token_fails(tmp_path):
    """NOTION_TOKEN 없을 때 친절한 안내 메시지로 종료."""
    import os
    env = os.environ.copy()
    env.pop("NOTION_TOKEN", None)
    cmd = [sys.executable, "build.py", "--url", "https://www.notion.so/abc"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert r.returncode != 0
    assert "NOTION_TOKEN" in r.stderr


def test_cli_generated_hwpx_validates(tmp_path):
    """build.py 가 출력한 파일을 python-hwpx 가 그대로 검증."""
    from hwpx import HwpxDocument

    out = tmp_path / "w.hwpx"
    r = _run("--md", "notion_page.md", "-o", str(out))
    assert r.returncode == 0
    HwpxDocument.open(str(out)).validate()  # 예외 없으면 통과
