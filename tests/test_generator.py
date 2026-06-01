"""생성기 회귀 테스트: 스키마 → HWPX 생성 및 구조 검증."""

from __future__ import annotations

import base64
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from generate_from_template import (
    STYLE,
    apply_global_styles,
    clear_body,
    render,
    validate_data,
    _load_image,
)
from hwpx import HwpxDocument


# ── 헬퍼 ─────────────────────────────────────────────────────────────


def _build(data: dict, out: Path, donor: str = "golden_sample.hwpx") -> Path:
    """golden_sample 을 기증자로 새 학습지를 생성(production 경로와 동일)."""
    doc = HwpxDocument.open(donor)
    clear_body(doc)
    render(doc, data)
    apply_global_styles(doc)
    doc.save_to_path(str(out))
    return out


def _png_bytes(w: int = 200, h: int = 120, fill: str = "#cfe8ff") -> bytes:
    img = Image.new("RGB", (w, h), fill)
    buf = io.BytesIO(); img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def minimal_data() -> dict:
    return {
        "header": {"left": "국어 5-1", "right": "칠서초 5학년"},
        "title": "회귀 테스트 학습지",
        "learning_goal": "테스트 학습 목표",
        "activities": [
            {
                "label": "활동1", "stage": "HOP", "instruction": "테스트 활동.",
                "passages": [
                    {"title": "지문 박스", "body": ["본문 한 줄"], "footnotes": [],
                     "images": [], "source": None},
                ],
                "questions": [
                    {"id": "Q1", "text": "첫 질문", "answer_box": False},
                    {"id": "Q2", "text": "답안 박스", "answer_box": True},
                ],
            }
        ],
    }


# ── 스키마 검증 ───────────────────────────────────────────────────────


def test_validate_data_accepts_minimal(minimal_data):
    validate_data(minimal_data)  # 예외 없음


def test_validate_data_rejects_non_dict():
    with pytest.raises(ValueError):
        validate_data("문자열")  # type: ignore[arg-type]


def test_validate_data_rejects_bad_passage_body(minimal_data):
    minimal_data["activities"][0]["passages"][0]["body"] = "문자열은 안됨"
    with pytest.raises(ValueError):
        validate_data(minimal_data)


def test_validate_data_rejects_non_string_footnote(minimal_data):
    minimal_data["activities"][0]["passages"][0]["footnotes"] = [123]
    with pytest.raises(ValueError):
        validate_data(minimal_data)


# ── 골든 회귀: golden_schema.json -> HWPX -> validate ────────────────


def test_golden_schema_generates_valid_hwpx(tmp_path):
    data = json.loads(Path("golden_schema.json").read_text(encoding="utf-8"))
    out = _build(data, tmp_path / "golden.hwpx")
    HwpxDocument.open(str(out)).validate()


def test_notion_schema_generates_valid_hwpx(tmp_path):
    data = json.loads(Path("notion_schema.json").read_text(encoding="utf-8"))
    out = _build(data, tmp_path / "notion.hwpx")
    HwpxDocument.open(str(out)).validate()


# ── 박스/답안박스 생성이 표(table)로 나타나는지 ─────────────────────


def test_minimal_data_produces_passage_and_answer_boxes(tmp_path, minimal_data):
    out = _build(minimal_data, tmp_path / "min.hwpx")
    with zipfile.ZipFile(out) as z:
        sec = z.read("Contents/section0.xml").decode("utf-8")
    # 박스는 1x1 표로 렌더됨
    n_tables = len(re.findall(r"<hp:tbl\b", sec))
    assert n_tables == 2  # 지문 박스 + 답안 박스


def test_image_in_passage_creates_pic_element(tmp_path, minimal_data):
    png = _png_bytes()
    minimal_data["activities"][0]["passages"][0]["images"] = [{
        "data": base64.b64encode(png).decode(),
        "format": "png",
        "caption": "테스트 캡션",
    }]
    out = _build(minimal_data, tmp_path / "withpic.hwpx")
    with zipfile.ZipFile(out) as z:
        sec = z.read("Contents/section0.xml").decode("utf-8")
    assert "<hp:pic" in sec
    assert 'binaryItemIDRef="BIN' in sec


# ── 머릿말 적용 ──────────────────────────────────────────────────────


def test_header_text_appears_in_output(tmp_path, minimal_data):
    out = _build(minimal_data, tmp_path / "hdr.hwpx")
    with zipfile.ZipFile(out) as z:
        sec = z.read("Contents/section0.xml").decode("utf-8")
    assert "국어 5-1" in sec
    assert "칠서초 5학년" in sec


# ── 이미지 로더 ──────────────────────────────────────────────────────


def test_load_image_from_path(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(_png_bytes())
    data, fmt = _load_image({"path": str(p)})
    assert data and fmt == "png"


def test_load_image_from_base64():
    png = _png_bytes()
    data, fmt = _load_image({"data": base64.b64encode(png).decode(), "format": "png"})
    assert data == png and fmt == "png"


def test_load_image_returns_none_for_missing_path():
    data, fmt = _load_image({"path": "/nonexistent/x.png"})
    assert data is None and fmt is None


# ── 스타일 토큰이 안정적인지 ─────────────────────────────────────────


def test_style_tokens_present():
    """스키마 호환을 위해 핵심 스타일 키들이 유지되는지 확인."""
    for k in ("title", "goal", "activity", "question", "box_width", "box_border",
              "passage_title_para", "passage_title_char",
              "passage_body_para", "passage_body_char",
              "answer_box_height"):
        assert k in STYLE, f"STYLE['{k}'] 누락"
