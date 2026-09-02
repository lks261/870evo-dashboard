# 삼성 870 EVO 가격 대시보드

다나와에서 삼성 870 EVO **정품 / 병행수입** 용량별 단가를 매일 자동으로 수집해서,
웹페이지로 공개하는 저장소입니다. 서버·VM 없이 GitHub 무료 기능만으로 동작합니다.

## 구조

```
.github/workflows/scrape.yml   ← 매일 자동 실행 스케줄 (한국시간 오전 9시)
scripts/scrape_870evo.py       ← 크롤링 스크립트 (정품/병행수입만 수집)
data/latest.json               ← 가장 최근 수집 결과
data/history.json              ← 날짜별 누적 히스토리 (그래프용)
index.html                     ← 공개될 대시보드 페이지 (GitHub Pages)
```

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
   - (이걸 해야 워크플로우가 data/*.json 결과를 자동 커밋할 수 있습니다)
4. 저장소 **Actions** 탭 → `870 EVO 가격 수집` 워크플로우 선택 →
   **Run workflow** 버튼으로 한 번 수동 실행해서 정상 동작하는지 확인합니다.
5. 이후로는 매일 자동으로 실행되어 `data/latest.json`, `data/history.json`이 갱신되고,
   대시보드 페이지도 그 데이터를 그대로 보여줍니다.

## 영업팀 공유 방법

`https://아이디.github.io/저장소이름/` 링크를 그대로 공유하면 됩니다.
페이지 우측 상단 "🔄 새로고침" 버튼을 누르면 최신 데이터를 다시 불러오고,
"크롤링 시각"과 "마지막 확인" 시각이 함께 표시됩니다.

## 품목 / 사이트를 추가하려면

- 같은 방식(정품/병행수입만 필터링 → JSON 저장)으로 스크립트를 하나 더 만들고,
  `scrape.yml`의 "크롤링 실행" 단계에 그 스크립트 실행 줄을 추가하면 됩니다.
- 대시보드(`index.html`)도 새 JSON 파일을 fetch하도록 섹션을 하나 더 추가하면 됩니다.
- 지금 규모(하루 1회, 몇 개 품목)에서는 GitHub Actions 무료 사용량에 전혀 문제되지 않습니다.

## 주의사항

- 다나와가 페이지 구조를 바꾸면 크롤링이 실패할 수 있습니다. 그럴 땐 Actions 탭에서
  실패 로그를 확인하고, `scripts/scrape_870evo.py`의 셀렉터를 다시 맞춰야 합니다.
- 하루 1회보다 자주 실행하지 마세요 (`scrape.yml`의 cron 값을 함부로 줄이지 않기).
