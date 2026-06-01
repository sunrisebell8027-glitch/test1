"""HWPX <hp:pic> 이미지 요소 빌더.

python-hwpx(2.9.1)에는 사각형·타원 등 도형 빌더는 있지만, '그림(pic)'
요소 빌더가 없다. 이 모듈은 OWPML 사양에 맞춘 <hp:pic> 요소를 직접
구성해 단락에 삽입한다. 자동 폭 맞춤(박스 폭 내 비율 유지 축소)을 함께 제공.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET

from PIL import Image

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
_IDENTITY = {"e1": "1", "e2": "0", "e3": "0", "e4": "0", "e5": "1", "e6": "0"}


def mm_to_hwpu(mm: float) -> int:
    """1mm ≈ 283.46 HWPUnit (1 HWPUnit = 1/7200 inch)."""
    return int(round(mm * 7200 / 25.4))


def px_to_hwpu(px: int, dpi: int = 96) -> int:
    return int(round(px * 7200 / dpi))


def fit_to_width(orig_w: int, orig_h: int, max_w: int) -> tuple[int, int]:
    """원본 너비를 max_w 이하로 비율 유지 축소(이미 작으면 그대로)."""
    if orig_w <= max_w:
        return orig_w, orig_h
    return max_w, int(round(orig_h * max_w / orig_w))


def _sub(parent: ET.Element, tag: str, attrs: dict | None = None) -> ET.Element:
    el = ET.SubElement(parent, tag, attrs or {})
    return el


def create_picture_element(
    cur_w: int,
    cur_h: int,
    *,
    org_w: int | None = None,
    org_h: int | None = None,
    bin_id_ref: str,
    inst_id: str,
    treat_as_char: bool = True,
) -> ET.Element:
    """완전한 <hp:pic> 요소(자식 포함)를 반환. 단위는 HWPUnit."""
    if org_w is None:
        org_w = cur_w
    if org_h is None:
        org_h = cur_h

    # 실제 작동하는 SimplePicture.hwpx 구조를 그대로 따른다:
    #   offset / orgSz / curSz / flip / rotationInfo / renderingInfo
    #   imgRect / imgClip / inMargin / imgDim / hc:img / effects
    #   sz / pos / outMargin
    # ※ lineShape, 최상위 shadow는 hp:pic 자식이 아니며, 추가하면 한글이
    #   그림을 그리지 못하고 깨진 아이콘만 표시한다.
    pic = ET.Element(
        f"{_HP}pic",
        {
            "id": inst_id, "zOrder": "0", "numberingType": "PICTURE",
            "lock": "0", "dropcapstyle": "None", "href": "",
            "groupLevel": "0", "instid": inst_id, "reverse": "0",
        },
    )

    # AbstractShapeComponentType 자식
    _sub(pic, f"{_HP}offset", {"x": "0", "y": "0"})
    _sub(pic, f"{_HP}orgSz", {"width": str(org_w), "height": str(org_h)})
    _sub(pic, f"{_HP}curSz", {"width": str(cur_w), "height": str(cur_h)})
    _sub(pic, f"{_HP}flip", {"horizontal": "0", "vertical": "0"})
    _sub(pic, f"{_HP}rotationInfo", {
        "angle": "0", "centerX": str(cur_w // 2), "centerY": str(cur_h // 2),
        "rotateimage": "1",
    })
    ri = _sub(pic, f"{_HP}renderingInfo")
    _sub(ri, f"{_HC}transMatrix", _IDENTITY)
    _sub(ri, f"{_HC}scaMatrix", _IDENTITY)
    _sub(ri, f"{_HC}rotMatrix", _IDENTITY)

    # PIC-specific 자식
    # imgRect : 표시 사각형의 4꼭짓점(curSz 기준)
    # imgClip : 원본 이미지에서 잘라낼 영역(없음 = (0,0,orgSz)). (0,0,0,0)이면
    #           한글이 "보여줄 영역 0×0"으로 해석해 이미지가 거의 안 그려진다.
    # imgDim  : 원본 이미지 영역 크기(HWPU; 픽셀×75 정도)
    rect = _sub(pic, f"{_HP}imgRect")
    _sub(rect, f"{_HC}pt0", {"x": "0", "y": "0"})
    _sub(rect, f"{_HC}pt1", {"x": str(cur_w), "y": "0"})
    _sub(rect, f"{_HC}pt2", {"x": str(cur_w), "y": str(cur_h)})
    _sub(rect, f"{_HC}pt3", {"x": "0", "y": str(cur_h)})
    _sub(pic, f"{_HP}imgClip", {"left": "0", "right": str(org_w), "top": "0", "bottom": str(org_h)})
    _sub(pic, f"{_HP}inMargin", {"left": "0", "right": "0", "top": "0", "bottom": "0"})
    _sub(pic, f"{_HP}imgDim", {"dimwidth": str(org_w), "dimheight": str(org_h)})
    _sub(pic, f"{_HC}img", {
        "binaryItemIDRef": bin_id_ref,
        "bright": "0", "contrast": "0", "effect": "REAL_PIC", "alpha": "0",
    })
    _sub(pic, f"{_HP}effects")

    # 4) AbstractShapeObjectType 자식 마지막 (sz, pos, outMargin)
    _sub(pic, f"{_HP}sz", {
        "width": str(cur_w), "height": str(cur_h),
        "widthRelTo": "ABSOLUTE", "heightRelTo": "ABSOLUTE", "protect": "0",
    })
    _sub(pic, f"{_HP}pos", {
        "treatAsChar": "1" if treat_as_char else "0",
        "affectLSpacing": "0",
        "flowWithText": "1", "allowOverlap": "0", "holdAnchorAndSO": "0",
        "vertRelTo": "PARA", "horzRelTo": "COLUMN",
        "vertAlign": "TOP", "horzAlign": "LEFT",
        "vertOffset": "0", "horzOffset": "0",
    })
    _sub(pic, f"{_HP}outMargin", {"left": "0", "right": "0", "top": "0", "bottom": "0"})
    return pic


def add_picture_to_paragraph(
    document,
    paragraph,
    image_bytes: bytes,
    image_format: str,
    *,
    max_width_mm: float = 110.0,
    treat_as_char: bool = True,
):
    """단락에 그림을 삽입. 폭은 max_width_mm 이하로 자동 축소(비율 유지)."""
    # 1) 원본 픽셀 크기 -> HWPUnit
    img = Image.open(io.BytesIO(image_bytes))
    px_w, px_h = img.size
    org_w_hwpu = px_to_hwpu(px_w)
    org_h_hwpu = px_to_hwpu(px_h)

    # 2) 박스 폭 한도 내로 축소(비율 유지)
    max_w_hwpu = mm_to_hwpu(max_width_mm)
    cur_w, cur_h = fit_to_width(org_w_hwpu, org_h_hwpu, max_w_hwpu)

    # 3) 바이너리 등록. add_image()는 매니페스트 아이디(예: "BIN0001")를 돌려준다.
    #    실제 작동 샘플(SimplePicture.hwpx)에서 <hc:img binaryItemIDRef>는
    #    매니페스트 <opf:item id>를 가리킨다(헤더의 binItem id가 아님).
    manifest_id = document.add_image(image_bytes, image_format)

    # 워킹 샘플(SimplePicture.hwpx)에 맞춰 두 가지 후처리:
    #  a) 매니페스트 opf:item 에 isEmbeded="1" 부여(누락 시 한글이 그림을 못 그림)
    #  b) add_image()가 추가한 헤더 <hh:binItem> 항목 제거(워킹 샘플엔 없음)
    fmt = image_format.lower().lstrip(".")
    bin_filename = f"{manifest_id}.{fmt}"
    try:
        pkg = document._package
        manifest_el = pkg._manifest_element()
        opf_ns = "http://www.idpf.org/2007/opf/"
        for it in manifest_el.findall(f"{{{opf_ns}}}item"):
            if it.get("id") == manifest_id:
                it.set("isEmbeded", "1")
                break
        pkg._persist_manifest()
    except Exception:
        pass
    try:
        headers = document._root.headers
        if headers:
            for bi in list(headers[0].list_bin_items()):
                if bi.get("BinData") == bin_filename:
                    headers[0].remove_bin_item(bi.get("id"))
                    break
    except Exception:
        pass

    # 4) inst-id는 고유한 큰 정수. 다른 객체 id와 안 겹치게.
    import random
    inst_id = str(random.randint(100_000_000, 999_999_999))

    # 5) <hp:pic> 요소를 만들어 단락에 인라인 객체로 부착
    pic_el = create_picture_element(
        cur_w, cur_h,
        org_w=org_w_hwpu, org_h=org_h_hwpu,
        bin_id_ref=manifest_id, inst_id=inst_id,
        treat_as_char=treat_as_char,
    )
    paragraph._insert_shape_element(pic_el)
    return manifest_id, (cur_w, cur_h)
