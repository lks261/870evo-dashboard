# 삼성 부품 가격 대시보드

다나와/컴퓨존에서 **SSD(870 EVO)**와 **서버용 DDR4 RAM** 가격을 정기적으로,
Fusion Worldwide "The Greensheet"에서 **시장동향**을 매달 자동으로 수집해서,
탭으로 구분된 웹페이지로 공개하는 저장소입니다. 서버·VM 없이 GitHub 무료
기능만으로 동작합니다.

## 구조

```
.github/workflows/scrape.yml              ← 월·목 09:17 (한국시간, SSD+RAM)
.github/workflows/retry_compuzone.yml     ← 컴퓨존 실패 시 낮 12시에 재시도
.github/workflows/scrape_market_news.yml  ← 매달 1일 자동 실행 (시장동향)
scripts/common.py                         ← 데이터셋별로 결과를 병합 저장하는 공용 유틸
scripts/scrape_870evo.py                  ← 다나와 SSD 크롤링 (정품/병행수입)
scripts/scrape_compuzone.py               ← 컴퓨존 SSD 크롤링 (공식인증 정품 라인업)
scripts/scrape_ram.py                     ← 다나와 서버용 DDR4 RAM 크롤링 (RDIMM/EDIMM)
scripts/scrape_market_news.py             ← Greensheet 시장동향 크롤링 (메모리/스토리지/주요이슈)
scripts/retry_compuzone_if_missing.py     ← 컴퓨존 재시도용 헬퍼
data/ssd/latest.json, history.json        ← SSD 최신/누적 데이터
data/ram/latest.json, history.json        ← RAM 최신/누적 데이터
data/market_news/latest.json, history.json ← 시장동향 최신/누적 데이터
index.html                                ← 공개될 대시보드 (SSD/RAM/시장동향/입출고 탭)
```

품목군(SSD/RAM/시장동향)마다 데이터 파일이 완전히 분리되어 있어서, 대시보드 상단
탭을 누르면 해당 데이터셋만 불러와 보여줍니다.

## 시장동향 데이터에 대한 특이사항

Fusion Worldwide의 월간 리포트 "The Greensheet"에서 **메모리(DRAM/RDIMM)**,
**스토리지(SSD/NAND)**, **주요 이슈** 세 섹션만 골라 뽑습니다. 리포트 URL이
매달 바뀌어서(`the-greensheet-2026년-9월` → 다음 달 `-10월`), 날짜로 계산해
접속하지 않고 리소스 목록 페이지에서 최신 글 링크를 매번 찾는 방식을 씁니다.

각 항목은 원문을 그대로 옮기지 않고 **핵심 문장(첫 문장) 또는 90자 이내로
축약**해서 저장합니다. 자세한 내용이 필요하면 대시보드의 "출처" 링크로
원문을 직접 확인하도록 안내합니다. 월간 리포트라 크롤링 주기도 **매달 1일
1회**로만 실행합니다 (다나와/컴퓨존처럼 매일 도는 게 아님).

**주의**: 실제 사이트 접속 테스트 없이 페이지 구조를 추정해서 만든 스크립트라,
처음 실행했을 때 "경고: '메모리' 섹션을 못 찾았습니다" 같은 메시지가 뜨면
`scripts/scrape_market_news.py`의 `find_section_bullets()` 탐색 방식을
실제 페이지 구조에 맞게 조정해야 할 수 있습니다.

## 입출고 탭 (분기 보고서의 "입출고 현황" 대체)

재고관리 프로그램에서 뽑은 CSV/엑셀을 이 탭에서 직접 올리면, 서버/보안장비 입출고
표·막대·파이 차트가 자동으로 만들어집니다(PNG 저장 버튼으로 PPT에도 붙일 수 있음).
다른 탭과 달리 **자동 크롤링이 아니라 사용자가 파일을 올리는 방식**이라 Actions와
무관하고, 파일은 서버로 올라가지 않고 브라우저 안에서만 처리됩니다.
누적/기간조회는 "히스토리 JSON 저장 → 다음 분기에 불러오기" 방식입니다.

## SSD 데이터 형식

각 항목은 `site`(다나와/컴퓨존)와 `source_type`(정품/병행수입)을 따로 갖고 있어서,
대시보드에서 "정품(다나와)", "병행수입(다나와)", "정품(컴퓨존)"처럼 조합해서 보여줍니다.

### 컴퓨존 크롤링에 대한 특이사항

컴퓨존은 검색결과 페이지가 자바스크립트로 그려지는 구조라, 다나와처럼 검색 페이지를
바로 크롤링하기 어렵습니다. 대신 "[삼성전자] 공식인증 870 EVO SATA" 이 라인업의
대표 상품(1TB, ProductNo=755257) 상세페이지 하단에 250GB~8TB 전체 옵션이 가격과
함께 노출되는 걸 확인해서, 그 페이지 하나만 가져와 옵션 목록을 파싱합니다.

**주의**: 나중에 컴퓨존이 이 상품을 단종하거나 페이지 구조를 바꾸면
`scripts/scrape_compuzone.py`의 `REP_PRODUCT_NO` 값을 다시 확인해서 갱신해야 합니다.

또한 컴퓨존은 GitHub Actions 서버(해외 IP) 접속이 간헐적으로 차단되는 것으로
보입니다. 본 실행(오전 9시)이 실패하면 `retry_compuzone.yml`이 낮 12시에
다른 서버(=다른 IP)로 한 번 더 시도합니다.

## RAM 데이터 형식

각 항목은 `dimm_type`과 PC4 규격을 기록하는 `clock`을 갖습니다.

| 타입 | PC4 규격 | 용량 |
| --- | --- | --- |
| RDIMM | 17000 / 19200 / 21300 / 25600 | 8GB / 16GB / 32GB / 64GB |
| EDIMM (ECC Unbuffered) | 19200 / 21300 / 23400 / 25600 | 8GB / 16GB / 32GB |

### RAM 크롤링에 대한 특이사항

RAM은 타입과 PC4 규격으로 검색한 뒤 다나와 가격비교 상품의 용량별 총 판매가를
읽습니다. 검색에서 빠진 항목은 서버용 RAM 카테고리에서 확인합니다.
수집하지 못한 조합은
실행 로그에 표시됩니다. 유효한 가격이 0건인 소스는 이전 데이터를 유지하고
워크플로우에서 실패로 표시됩니다.

네트워크 연결 없이 파서와 저장 동작을 확인하려면 저장소 루트에서
`python -m unittest discover -s tests`를 실행하세요.

## 처음 설정하는 방법

1. 이 폴더 전체를 새로 만든 GitHub 저장소에 업로드(푸시)합니다.
   - 저장소는 **Public**으로 만드세요. (Private이면 GitHub Actions 무료 사용량이 제한되고,
     GitHub Pages도 유료 플랜에서만 무료로 공개 가능합니다)
2. 저장소 **Settings → Pages** 로 이동
   - Source: `Deploy from a branch`
   - Branch: `main` / `/ (root)` 선택 → Save
   - 잠시 후 `https://아이디.github.io/저장소이름/` 주소가 생성됩니다.
3. 저장소 **Settings → Actions → General** 로 이동
   - "Workflow permissions"을 **Read and write permissions**으로 변경 → Save
   - (이걸 해야 워크플로우가 data/ 결과를 자동 커밋할 수 있습니다)
4. 저장소 **Actions** 탭 → `870 EVO 가격 수집` 워크플로우 선택 →
   **Run workflow** 버튼으로 한 번 수동 실행해서 SSD(다나와/컴퓨존)+RAM 모두
   정상 동작하는지 확인합니다.
5. 이후로는 월요일과 목요일 09:17(한국시간)에 실행이 예약되어 `data/ssd/`, `data/ram/` 안의 파일이 갱신되고,
   대시보드 페이지도 그 데이터를 그대로 보여줍니다.

## 영업팀 공유 방법

`https://아이디.github.io/저장소이름/` 링크를 그대로 공유하면 됩니다.
상단 탭에서 SSD / 서버 RAM을 눌러 전환할 수 있고, 페이지를 열 때마다
최신 데이터를 자동으로 불러옵니다.

## 품목 / 사이트를 추가하려면

- 새 데이터셋(예: `hdd`)을 추가하려면: `merge_and_save("hdd", 사이트명, items)` 형태로
  호출하는 스크립트를 만들고, `scrape.yml`에 실행 단계를 추가한 다음, `index.html`에
  새 탭 버튼 + `tabpanel-hdd` 마크업 + 렌더 함수를 하나 더 추가하면 됩니다.
- 지금 규모(하루 1회, 두 품목)에서는 GitHub Actions 무료 사용량에 전혀 문제되지 않습니다.

## 주의사항

- 다나와/컴퓨존이 페이지 구조를 바꾸면 크롤링이 실패할 수 있습니다. 그럴 땐 Actions
  탭에서 실패 로그를 확인하고, 해당 스크립트의 판별 로직을 다시 맞춰야 합니다.
- 하루 1회보다 자주 실행하지 마세요 (`scrape.yml`의 cron 값을 함부로 줄이지 않기).
