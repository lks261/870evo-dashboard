"""
여러 사이트 크롤러(scrape_870evo.py, scrape_compuzone.py, scrape_ram.py 등)가
공용으로 쓰는 유틸리티.

품목군(dataset)별로 파일을 완전히 분리한다:
    data/ssd/latest.json, data/ssd/history.json   ← SSD (다나와+컴퓨존)
    data/ram/latest.json, data/ram/history.json   ← 서버용 RAM (다나와)

같은 dataset 안에서는 site 필드를 기준으로 "내 사이트 항목만 교체"하는
병합(merge) 로직을 쓴다. 한 스크립트가 무작정 덮어쓰면 다른 사이트가
이미 써놓은 결과가 지워지기 때문.
"""

import json
import os
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(REPO_DIR, "data")

CAPACITY_ORDER = {
    "120GB": 120, "128GB": 128, "240GB": 240, "250GB": 250, "256GB": 256,
    "480GB": 480, "500GB": 500, "512GB": 512,
    "1TB": 1024, "2TB": 2048, "4TB": 4096, "8TB": 8192, "16TB": 16384,
}


def dataset_paths(dataset: str):
    """dataset 예: 'ssd', 'ram' → 그 폴더 안의 latest.json / history.json 경로"""
    d = os.path.join(DATA_DIR, dataset)
    return os.path.join(d, "latest.json"), os.path.join(d, "history.json")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def capacity_sort_key(capacity: str) -> int:
    return CAPACITY_ORDER.get(capacity, 0)


def merge_and_save(dataset: str, site: str, items: list[dict]):
    """dataset(예: 'ssd'/'ram') 안에서, 이 사이트(site)가 새로 수집한 items를
    기존 latest.json / history.json에 다른 사이트 데이터는 보존한 채로 병합해서 저장한다."""
    latest_path, history_path = dataset_paths(dataset)
    now_kst = datetime.now(KST)
    today = now_kst.strftime("%Y-%m-%d")

    # site 필드가 아예 없는 레거시 항목(과거 버전 스크립트가 남긴 찌꺼기)은
    # 여기서 걸러낸다. site가 없으면 "교체 대상"으로 매칭이 안 돼서 영원히
    # 파일에 남아있는 문제가 있었음.
    def has_valid_site(it):
        return bool(it.get("site"))

    # 1) latest.json: 같은 site의 기존 항목만 걷어내고 새 결과로 교체
    latest = load_json(latest_path, {"items": []})
    kept = [it for it in latest.get("items", []) if has_valid_site(it) and it.get("site") != site]
    latest["items"] = kept + items
    latest["updated_at"] = now_kst.isoformat()
    latest["updated_at_display"] = now_kst.strftime("%Y-%m-%d %H:%M")
    save_json(latest_path, latest)

    # 2) history.json: 오늘자 entry 안에서도 같은 방식으로 site별 병합
    history = load_json(history_path, {"entries": []})
    today_entry = next((e for e in history["entries"] if e["date"] == today), None)
    if today_entry is None:
        today_entry = {"date": today, "items": []}
        history["entries"].append(today_entry)
    today_entry["items"] = [
        it for it in today_entry["items"] if has_valid_site(it) and it.get("site") != site
    ] + items
    history["entries"].sort(key=lambda e: e["date"])
    save_json(history_path, history)

    return latest, history
