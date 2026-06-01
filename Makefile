# 학습지 생성 파이프라인 단축 명령
.PHONY: test golden notion clean

# 회귀 테스트 (스키마·변환기·이미지 빌더·생성기 41개)
test:
	python3 -m pytest tests/ -q

# golden_schema.json -> worksheet_styled.hwpx (스타일 골든 재현)
golden:
	python3 generate_from_template.py golden_schema.json worksheet_styled.hwpx

# notion_page.md -> notion_schema.json -> worksheet_from_notion.hwpx
notion:
	python3 notion_to_schema.py notion_page.md notion_schema.json
	python3 generate_from_template.py notion_schema.json worksheet_from_notion.hwpx

clean:
	rm -f worksheet*.hwpx test_pic.hwpx notion_schema*.json
	rm -rf __pycache__ tests/__pycache__ .pytest_cache
