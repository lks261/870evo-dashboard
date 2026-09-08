"""
오늘자 data/history.json에 컴퓨존 데이터가 이미 있는지 확인한다.
- 있으면: 아무것도 안 하고 종료 (exit code 0) → 재시도 워크플로우가 스킵됨
- 없으면: scrape_compuzone.py를 실행해서 다시 수집 시도

본 실행(오전 9시)이 실패했을 때, 몇 시간 뒤 다른 GitHub Actions 서버(=다른 IP)에서
한 번 더 시도해보기 위한 용도. 컴퓨존이 특정 IP 대역만 간헐적으로 차단하는 것으로
보이기 때문에, 시간을 두고 재시도하면 성공할 확률이 있다.
"""

import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, HISTORY_PATH

KST = timezone(timedelta(hours=9))


def today_has_compuzone() -> bool:
    today = datetime.now(KST).strftime("%Y-%m-%d")
    history = load_json(HISTORY_PATH, {"entries": []})
    today_entry = next((e for e in history["entries"] if e["date"] == today), None)
    if not today_entry:
        return False
    return any(it.get("site") == "컴퓨존" for it in today_entry.get("items", []))


if __name__ == "__main__":
    if today_has_compuzone():
        print("오늘자 컴퓨존 데이터가 이미 있습니다. 재시도를 건너뜁니다.")
        sys.exit(0)
    else:
        print("오늘자 컴퓨존 데이터가 없습니다. 재시도를 진행합니다.")
        import scrape_compuzone
        scrape_compuzone.main()
