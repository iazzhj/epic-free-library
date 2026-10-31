"""
effects_export.json(언리얼에서 추출한 결과)을 사이트 데이터로 변환합니다.

사용법: python tools/import_export.py <effects_export.json 경로>

- data/effects/<id>.json 을 팩마다 새로 쓰되, 기존 파일의 desc·video·poster·loop·duration 값은 보존합니다.
- data/effects/index.json 의 count·names 를 갱신합니다.
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ids import resolve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX_DIR = os.path.join(ROOT, "data", "effects")
KEEP = ("desc", "video", "poster", "loop", "duration", "visible", "pattern")


def clean_path(obj_path, folder):
    """'/Game/ParagonGreystone/FX/Particles/Greystone/Abilities/ClearAPath/FX/P_x.P_x' → 'Greystone/Abilities/ClearAPath'"""
    pkg = obj_path.split(".")[0]
    parts = pkg.split("/")[:-1]  # 에셋 이름 제거
    root = ["", "Game", folder]
    if parts[:3] == root:
        parts = parts[3:]
    for prefix in (["FX", "Particles"], ["FX"]):
        if parts[:len(prefix)] == prefix:
            parts = parts[len(prefix):]
            break
    parts = [x for x in parts if x.upper() != "FX"]  # 중간에 끼어 있는 FX 폴더도 제목에서 뺌
    return "/".join(parts)


def effect_keys(effects):
    """팩 안에서 이펙트를 구분하는 키. 이름이 겹치면 '이름__상위폴더'.
    fx_capture.py 의 effect_keys 와 같은 규칙 (녹화 폴더 이름과 맞아야 함)."""
    counts = {}
    for e in effects:
        counts[e["name"]] = counts.get(e["name"], 0) + 1
    keys, used = [], set()
    for e in effects:
        key = e["name"]
        if counts[key] > 1:
            parts = e["object"].split(".")[0].split("/")[:-1]
            tag = next((x for x in reversed(parts) if x.upper() not in ("FX", "TEMPFX")), "dup")
            key = "{0}__{1}".format(e["name"], tag)
        base, n = key, 2
        while key in used:
            key, n = "{0}_{1}".format(base, n), n + 1
        used.add(key)
        keys.append(key)
    return keys


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def main(src):
    export = load(src, None)
    index_path = os.path.join(FX_DIR, "index.json")
    index = load(index_path, {"assets": {}})
    for pack in export["packs"]:
        pid = resolve(pack["id"])
        if pid != pack["id"]:
            print(f"  id 맞춤: {pack['id']} -> {pid}")
        out_path = os.path.join(FX_DIR, pid + ".json")
        old = {e.get("key", e["name"]): e for e in load(out_path, {"effects": []})["effects"]}
        effects = []
        for e, key in zip(pack["effects"], effect_keys(pack["effects"])):
            item = {
                "name": e["name"],
                "key": key,
                "path": clean_path(e["object"], pack["folder"]),
                "loop": e.get("loop"),
                "duration": e.get("duration"),
                "system": e.get("system"),
            }
            prev = old.get(key, {})
            for k in KEEP:
                if prev.get(k) is not None and item.get(k) is None:
                    item[k] = prev[k]
            effects.append(item)
        effects.sort(key=lambda x: (x["path"].lower(), x["name"].lower()))
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"asset": pid, "source": pack["folder"], "engine": export.get("engine"), "effects": effects},
                      f, ensure_ascii=False, indent=2)
            f.write("\n")
        index["assets"][pid] = {"count": len(effects), "names": [e["name"] for e in effects]}
        print(f"{pack['folder']} -> {pid}: {len(effects)}")
    index["updated"] = date.today().isoformat()
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv[1])
