# 노션 → 한글 학습지 생성 파이프라인

선생님이 노션에 학습지 내용을 적으면, 그대로 한글(.hwpx) 학습지가 나오는 자동화입니다.
편집용지·머릿말·박스 스타일은 골든 샘플 한 장을 기준으로 그대로 재사용합니다.

## 빠른 사용법

```bash
# 1) 노션에서 fetch 한 마크다운으로부터 한 줄에 학습지 생성
python3 build.py --md notion_page.md -o worksheet.hwpx

# 2) 회귀 테스트 (51개)
make test

# 3) 한 줄 단축
make build
```

옵션:
- `--max-image-mm 100` : 박스 안 이미지 최대 가로(mm), 기본 120
- `--donor other.hwpx` : 다른 골든 샘플 사용 (기본 `golden_sample.hwpx`)
- `--schema-out s.json` : 중간 스키마 JSON 도 보존
- `--url <노션URL>` : 환경변수 `NOTION_TOKEN` 있으면 공식 API 로 자동 fetch

## 노션 작성 규칙

`notion_to_schema.py` 상단 docstring 참고. 요약:

```
머리말좌: 과목/단원
머리말우: 학교/학년·반·이름
학습목표: ...

## 활동1(HOP). 지시문
### 지문제목
> 본문 한 줄
> 본문 두 번째 줄
> • 용어: 뜻 설명           # 각주
> 출처: 어디서             # 출처
![캡션](이미지URL)          # 박스 안 그림 (박스 폭에 맞춰 자동 축소)

Q1. 첫 질문
Q2. 둘째 질문 #답안          # 빈 답안 박스
Q3. 질문 뒤에 박스 따로
### 함안에 다녀와서
> 박스 본문
```

## 구성 파일

| 파일 | 역할 |
|---|---|
| `build.py` | **CLI**: 마크다운→스키마→HWPX→검증 한 번에 |
| `notion_to_schema.py` | 노션 마크다운 → 스키마(JSON) 변환 |
| `generate_from_template.py` | 스키마 → HWPX (스타일은 골든에서 재사용) |
| `hwpx_picture.py` | `<hp:pic>` OWPML 빌더 (python-hwpx 에 없음) |
| `golden_sample.hwpx` | 스타일/편집용지 원본 |
| `tests/` | pytest 회귀 스위트 (51개) |
| `Makefile` | `make test/build/golden/notion/clean` |

## 처리 흐름

```
노션 페이지 ──(fetch)──> 마크다운 ──(parse)──> 스키마(JSON) ──(render)──> .hwpx
                                                                 │
                                                          validate() OK
```

- 이미지: `![](url)` 의 url 을 그 자리에서 다운로드해 `BinData/BIN####` 으로 임베드
- 박스: 1×1 표로 렌더 (제목 가운데, 본문 양쪽정렬)
- 답안 박스: `#답안` 마커가 붙은 문항 다음에 빈 박스 자동 생성
