"""이미지 빌더 회귀 테스트: pic XML 구조와 박스 폭 자동 축소 확인.

한컴 정품 SimplePicture.hwpx 의 크기 모델을 기준으로 한다:
  - imgDim/imgClip = 원본 픽셀 × 75 (HWPU)
  - orgSz/curSz/sz/imgRect = 화면 표시 크기
  - scaMatrix = 단위행렬(orgSz=curSz 이므로)
"""

from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

import pytest
from PIL import Image, ImageDraw

from hwpx_picture import (
    create_picture_element,
    fit_to_width,
    mm_to_hwpu,
    px_to_hwpu,
    add_picture_to_paragraph,
)

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_HC = "{http://www.hancom.co.kr/hwpml/2011/core}"


# ── 단위 변환 ──────────────────────────────────────────────────────


def test_mm_to_hwpu_round_trip():
    assert mm_to_hwpu(25.4) == 7200  # 1 inch
    assert mm_to_hwpu(0) == 0


def test_px_to_hwpu_uses_96_dpi_by_default():
    assert px_to_hwpu(96) == 7200  # 1 inch @ 96 dpi


def test_fit_to_width_preserves_aspect_ratio():
    w, h = fit_to_width(1000, 500, 200)
    assert w == 200
    assert h == 100


def test_fit_to_width_keeps_smaller_images_unchanged():
    assert fit_to_width(100, 50, 200) == (100, 50)


# ── pic XML 구조 ───────────────────────────────────────────────────


def _pic_attrs(pic: ET.Element, tag: str) -> dict:
    el = pic.find(f"{_HP}{tag}")
    return dict(el.attrib) if el is not None else {}


def test_pic_element_has_required_top_level_children():
    pic = create_picture_element(
        34016, 23584,
        intrinsic_w=90000, intrinsic_h=62400,
        bin_id_ref="BIN0001", inst_id="123",
    )
    # 정품 샘플과 동일한 자식 순서
    expected = [
        "hp:offset", "hp:orgSz", "hp:curSz", "hp:flip",
        "hp:rotationInfo", "hp:renderingInfo",
        "hp:imgRect", "hp:imgClip", "hp:inMargin", "hp:imgDim",
        "hc:img", "hp:effects",
        "hp:sz", "hp:pos", "hp:outMargin",
    ]
    children = [c.tag.replace("{http://www.hancom.co.kr/hwpml/2011/paragraph}", "hp:")
                  .replace("{http://www.hancom.co.kr/hwpml/2011/core}", "hc:")
                for c in pic]
    # shapeComment 같은 선택 자식이 끝에 붙을 수 있음. 앞쪽 순서만 검증.
    assert children[:len(expected)] == expected


def test_pic_does_not_include_lineshape_or_top_level_shadow():
    """이 두 요소가 들어가면 한글이 깨진 그림 아이콘만 표시한다."""
    pic = create_picture_element(
        1000, 1000, intrinsic_w=2000, intrinsic_h=2000,
        bin_id_ref="BIN0001", inst_id="1",
    )
    # lineShape, shadow 는 pic 최상위 자식이 아니어야 함
    direct = {c.tag for c in pic}
    assert f"{_HP}lineShape" not in direct
    assert f"{_HP}shadow" not in direct


def test_size_model_matches_hancom_sample():
    """orgSz/curSz/sz = 표시크기, imgDim/imgClip = 원본픽셀."""
    pic = create_picture_element(
        34016, 23584,
        intrinsic_w=90000, intrinsic_h=62400,
        bin_id_ref="BIN0001", inst_id="1",
    )
    assert _pic_attrs(pic, "orgSz") == {"width": "34016", "height": "23584"}
    assert _pic_attrs(pic, "curSz") == {"width": "34016", "height": "23584"}
    assert _pic_attrs(pic, "imgDim") == {"dimwidth": "90000", "dimheight": "62400"}
    assert _pic_attrs(pic, "imgClip") == {
        "left": "0", "right": "90000", "top": "0", "bottom": "62400",
    }
    sz = _pic_attrs(pic, "sz")
    assert sz["width"] == "34016" and sz["height"] == "23584"


def test_imgrect_uses_display_size_not_intrinsic():
    pic = create_picture_element(
        34016, 23584, intrinsic_w=90000, intrinsic_h=62400,
        bin_id_ref="BIN0001", inst_id="1",
    )
    rect = pic.find(f"{_HP}imgRect")
    pt2 = rect.find(f"{_HC}pt2")
    assert pt2.attrib == {"x": "34016", "y": "23584"}


def test_imgclip_is_not_zero():
    """imgClip=(0,0,0,0) 이면 한글이 그림을 거의 안 그린다. 회귀 방지."""
    pic = create_picture_element(
        100, 100, intrinsic_w=200, intrinsic_h=200,
        bin_id_ref="BIN0001", inst_id="1",
    )
    clip = _pic_attrs(pic, "imgClip")
    assert clip["right"] != "0" or clip["bottom"] != "0"


def test_binary_item_id_ref_matches_manifest_id():
    pic = create_picture_element(
        100, 100, intrinsic_w=200, intrinsic_h=200,
        bin_id_ref="BIN0042", inst_id="1",
    )
    img = pic.find(f"{_HC}img")
    assert img.get("binaryItemIDRef") == "BIN0042"


def test_pos_treat_as_char_is_one_by_default():
    pic = create_picture_element(
        100, 100, intrinsic_w=200, intrinsic_h=200,
        bin_id_ref="BIN0001", inst_id="1",
    )
    pos = _pic_attrs(pic, "pos")
    assert pos["treatAsChar"] == "1"


# ── 통합: 실제 문서에 이미지를 삽입하고 매니페스트/헤더 정합성 검증 ──


@pytest.fixture
def png_bytes() -> bytes:
    img = Image.new("RGB", (1200, 832), "#fef9e7")
    ImageDraw.Draw(img).rectangle([4, 4, 1196, 828], outline="#7c2d12", width=4)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_inserted_picture_passes_validate(tmp_path, png_bytes):
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph("")
    add_picture_to_paragraph(doc, p, png_bytes, "png", max_width_mm=120)
    out = tmp_path / "pic.hwpx"
    doc.save_to_path(str(out))
    HwpxDocument.open(str(out)).validate()  # 예외 없으면 통과


def test_manifest_marks_image_as_embedded(tmp_path, png_bytes):
    """isEmbeded='1' 없으면 한글이 임베드 이미지로 인식 못 함."""
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph("")
    add_picture_to_paragraph(doc, p, png_bytes, "png", max_width_mm=80)
    out = tmp_path / "pic.hwpx"
    doc.save_to_path(str(out))
    with zipfile.ZipFile(out) as z:
        hpf = z.read("Contents/content.hpf").decode("utf-8")
    m = re.search(r'<opf:item[^>]*BIN0001\.png[^>]*/>', hpf)
    assert m is not None
    assert 'isEmbeded="1"' in m.group(0)


def test_no_stray_header_bin_item(tmp_path, png_bytes):
    """add_image() 가 추가하는 헤더 binItem 은 워킹 샘플과 달라 제거되어야 함."""
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph("")
    add_picture_to_paragraph(doc, p, png_bytes, "png", max_width_mm=80)
    out = tmp_path / "pic.hwpx"
    doc.save_to_path(str(out))
    with zipfile.ZipFile(out) as z:
        header = z.read("Contents/header.xml").decode("utf-8")
    # BIN0001.png 를 가리키는 binItem 이 헤더에 남아있으면 안 됨
    assert not re.search(r'<hh:binItem[^>]*BIN0001\.png[^>]*/>', header)


def test_image_scaled_to_box_width(png_bytes):
    """1200px 이미지에 max 120mm(34016 HWPU) 적용 시 폭은 max 에 맞고 비율 유지."""
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph("")
    _id, (cw, ch) = add_picture_to_paragraph(doc, p, png_bytes, "png", max_width_mm=120)
    assert cw == mm_to_hwpu(120)
    # 비율: 1200x832 -> 4:2.77 -> 120mm x 83.2mm
    expected_h = round(34016 * 832 / 1200)  # 약 23584
    assert abs(ch - expected_h) <= 1
