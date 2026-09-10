# 삼성 부품 가격 대시보드

다나와/컴퓨존에서 **SSD(870 EVO)**와 **서버용 DDR4 RAM** 가격을 매일 자동으로
수집해서, 탭으로 구분된 웹페이지로 공개하는 저장소입니다. 서버·VM 없이 GitHub
무료 기능만으로 동작합니다.

## 구조

```
.github/workflows/scrape.yml          ← 매일 자동 실행 스케줄 (한국시간 오전 9시)
.github/workflows/retry_compuzone.yml ← 컴퓨존 실패 시 낮 12시에 재시도
scripts/common.py                     ← 데이터셋(ssd/ram)별로 결과를 병합 저장하는 공용 유틸
scripts/scrape_870evo.py              ← 다나와 SSD 크롤링 (정품/병행수입)
scripts/scrape_compuzone.py           ← 컴퓨존 SSD 크롤링 (공식인증 정품 라인업)
scripts/scrape_ram.py                 ← 다나와 서버용 DDR4 RAM 크롤링 (RDIMM/UDIMM)
scripts/retry_compuzone_if_missing.py ← 컴퓨존 재시도용 헬퍼
data/ssd/latest.json, history.json    ← SSD 최신/누적 데이터
data/ram/latest.json, history.json    ← RAM 최신/누적 데이터
index.html                            ← 공개될 대시보드 (SSD/RAM 탭)
```

품목군(SSD/RAM)마다 데이터 파일이 완전히 분리되어 있어서, 대시보드 상단
탭을 누르면 해당 데이터셋만 불러와 보여줍니다.

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

각 항목은 `dimm_type`(RDIMM/UDIMM)과 `clock`(17000/19200/21300/25600, PC4-XXXXX
표기 기준)을 따로 갖습니다. 수집 대상은 아래 조합입니다:

- RDIMM(Registered): 17000 / 19200 / 21300 / 25600
- UDIMM(Unbuffered): 19200 / 21300 / 25600 (17000 없음)
- 각 클럭마다 용량: 8GB / 16GB / 32GB / 64GB

### RAM 크롤링에 대한 특이사항

SSD(870 EVO)는 한 상품에 용량별 옵션이 "가격비교 그룹"으로 묶여서 나오지만,
서버용 RAM은 용량마다 사실상 별개 상품이라 그런 묶음이 없습니다. 그래서
"용량 + 클럭 + DIMM타입" 조합별로 각각 다나와에 검색해서, 그 중 삼성전자
상품의 최저가를 채택하는 방식으로 동작합니다 (조합 28개 x 검색 1회씩).

판매자마다 상품명 표기가 SSD보다 훨씬 제각각이라(예: "PC4-2133P(PC4-17000R)"
vs "2133MHz" vs "17000R" 등), 오검출 가능성이 SSD보다 높습니다. 처음 며칠은
대시보드에서 특정 조합만 비어있거나 가격이 튀지 않는지 한 번씩 확인해보는 걸
권장합니다. 이상하면 `scripts/scrape_ram.py`의 `block_matches()` 함수의
판별 조건을 조정해야 합니다.

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
5. 이후로는 매일 자동으로 실행되어 `data/ssd/`, `data/ram/` 안의 파일이 갱신되고,
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
