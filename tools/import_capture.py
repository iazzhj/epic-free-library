"""
녹화 결과(upload_<팩 id>.zip)를 사이트에 반영합니다.

사용법: python tools/import_capture.py <upload_xxx.zip>

- zip 안의 media/ 파일을 저장소 media/ 로 복사합니다.
- capture_result.json 의 loop·duration·video·poster·visible 값을 data/effects/<id>.json 에 병합합니다.
"""
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ids import resolve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = ("loop", "duration", "video", "poster", "visible", "pattern")


def main(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        result = json.loads(z.read("capture_result.json").decode("utf-8"))
        if "camera_plan.json" in z.namelist():
            plan_path = os.path.join(ROOT, "data", "camera_plan.json")
            plan = {}
            if os.path.exists(plan_path):
                with open(plan_path, encoding="utf-8") as f:
                    plan = json.load(f)
            for pid, items in json.loads(z.read("camera_plan.json").decode("utf-8")).items():
                plan.setdefault(pid, {}).update(items)  # 카메라 계획은 언리얼 쪽 팩 id 그대로 보관
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
                f.write("\n")
        for info in z.infolist():
            name = info.filename
            if not name.startswith("media/") or name.endswith("/") or ".." in name:
                continue
            if not name.lower().endswith((".webm", ".mp4", ".jpg", ".jpeg", ".png")):
                continue
            dest = os.path.join(ROOT, *name.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(z.read(info))

    for raw_id, effects in result.items():
        pack_id = resolve(raw_id)
        if pack_id != raw_id:
            print(f"  id 맞춤: {raw_id} -> {pack_id}")
        path = os.path.join(ROOT, "data", "effects", pack_id + ".json")
        if not os.path.exists(path):
            print(f"{pack_id}: 이펙트 목록이 없어 건너뜀 (import_export.py 먼저 실행)")
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        matched = 0
        for e in data["effects"]:
            r = effects.get(e.get("key", e["name"]))
            if not r:
                continue
            matched += 1
            for k in FIELDS:
                if k in r:
                    e[k] = r[k]
            if e.get("duration") == 0:
                e["duration"] = 0.1  # 예전 변환본의 0초 표기 보정
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"{pack_id}: {matched}/{len(effects)}개 반영")


if __name__ == "__main__":
    main(sys.argv[1])
