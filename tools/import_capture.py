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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = ("loop", "duration", "video", "poster", "visible")


def main(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        result = json.loads(z.read("capture_result.json").decode("utf-8"))
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

    for pack_id, effects in result.items():
        path = os.path.join(ROOT, "data", "effects", pack_id + ".json")
        if not os.path.exists(path):
            print(f"{pack_id}: 이펙트 목록이 없어 건너뜀 (import_export.py 먼저 실행)")
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        matched = 0
        for e in data["effects"]:
            r = effects.get(e["name"])
            if not r:
                continue
            matched += 1
            for k in FIELDS:
                if k in r:
                    e[k] = r[k]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"{pack_id}: {matched}/{len(effects)}개 반영")


if __name__ == "__main__":
    main(sys.argv[1])
