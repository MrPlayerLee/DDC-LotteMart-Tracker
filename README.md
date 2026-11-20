# DDC-LotteMart-Tracker

경기도 동두천 롯데마트의 상품 가격·재고를 공식 모바일 도와센터에서 **읽기 전용**으로 확인하는 프로젝트입니다.

## 현재 상태

- 기본 지점: 롯데마트 **동두천점** / 경기
- 기본 검색어: 조니워커 (레드라벨·블랙라벨·그린라벨 집중 관찰)
- 즉시 검색: Work 클라우드에서 `tracker.py --query` 실행 (GitHub Issue 불필요)
- 결과: data/status.json (최신 시도), data/latest.json (마지막 성공 조회)
- **공식 사이트가 차단/타임아웃되면 조회 실패를 명시합니다.** 품절이나 세일 종료로 간주하지 않습니다.

## 설정 및 실행

watchlist.json에서 지점·검색어·관심 상품을 바꿀 수 있습니다.

Python 3.11 이상에서:

    python -m pip install -r requirements.txt
    python tracker.py
    python tracker.py --query '생수'
    python -m unittest discover -s tests -v

공식 검색이 0건이고 검색어가 관심 상품의 이름 또는 별칭과 일치하면, 설정된 매장 등록명(`search_name`)으로 다시 조회합니다.

## 결과 해석

- status: ok / error. error이면 data/latest.json을 현재 재고로 취급하지 마세요.
- stock_status: in_stock / out_of_stock / unknown.
- discount_status: discounted / not_discounted / unknown.
- `discount_rate_pct`: 공식 할인율을 우선 사용하며, 판매가와 정상가가 함께 제공되면 계산합니다. 확인할 수 없으면 `null`입니다.
- 가격 단위는 원(KRW), 용량은 인식될 때 mL로 정규화합니다.
- 특정 제품이 검색되지 않아도 품절이라는 뜻은 아닙니다.
- 실재고는 구매 시점에 달라질 수 있습니다.

## 구현 및 주의

2026년 3월 공개된 롯데마트 모바일 도와센터의 AJAX 엔드포인트 분석을 참고해 독립 구현했습니다. 공식·지원 API가 아니라 공개 웹사이트의 내부 조회 경로이므로 **현재 접근 가능성과 응답 형식이 보장되지 않습니다**. 2026-11-19에 Work 클라우드에서 동두천점의 공식 가격과 재고를 확인했습니다. 같은 날 GitHub 기본 Ubuntu, macOS 15, Ubuntu ARM 러너에서는 매장 목록 HTTPS 연결이 시간 초과됐습니다. 정확한 차단 원인은 확인되지 않았습니다.

참고: https://github.com/hmmhmmhm/daiso-mcp/blob/main/docs/lottemart-mobile-scraping-replay-plan.md

외부 서비스 제한을 회피하는 직접 IP 우회, 로그인 쿠키 수집, 대량 조회는 사용하지 않습니다.
