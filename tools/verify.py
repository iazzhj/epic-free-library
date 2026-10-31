"""사이트 데이터 점검. 반영 후 실행해서 문제가 없을 때만 커밋합니다.

사용법: python tools/verify.py
확인 항목
  - assets.json 의 id 중복, 분류 키
  - effects/index.json 의 에셋이 사이트 목록에 있는지, 개수가 상세 파일과 같은지
  - 이펙트의 video·poster 파일이 실제로 있는지, media 폴더에 연결 안 된 파일이 있는지
  - 저장소 전체 용량 (GitHub Pages 한도 1GB)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def main():
    errors, notes = [], []
    assets = load("data", "assets.json")
    ids = [a["id"] for a in assets["assets"]]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        errors.append("에셋 id 중복: " + ", ".join(sorted(dup)))
    for a in assets["assets"]:
        if a["cat"] not in assets["cats"]:
            errors.append(f"{a['id']}: 알 수 없는 분류 {a['cat']}")

    index = load("data", "effects", "index.json")
    referenced = set()
    for pid, info in index["assets"].items():
        if pid not in ids:
            errors.append(f"이펙트 색인의 {pid} 가 사이트 에셋 목록에 없음 (화면에 안 나옴)")
        path = os.path.join(ROOT, "data", "effects", pid + ".json")
        if not os.path.exists(path):
            errors.append(f"{pid}: 상세 파일 없음")
            continue
        effects = load("data", "effects", pid + ".json")["effects"]
        if info["count"] != len(effects):
            errors.append(f"{pid}: 색인 개수 {info['count']} ≠ 상세 {len(effects)}")
        videos = invisible = pending = 0
        for e in effects:
            for k in ("video", "poster"):
                if e.get(k):
                    referenced.add(e[k])
                    if not os.path.exists(os.path.join(ROOT, *e[k].split("/"))):
                        errors.append(f"{pid}/{e['name']}: {k} 파일 없음 ({e[k]})")
            if e.get("video"):
                videos += 1
            elif e.get("visible") is False:
                invisible += 1
            else:
                pending += 1
        notes.append(f"{pid}: 이펙트 {len(effects)} · 영상 {videos} · 정지 촬영 불가 {invisible} · 영상 대기 {pending}")

    media_root = os.path.join(ROOT, "media")
    orphans = []
    for dirpath, _, files in os.walk(media_root):
        for fn in files:
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, "/")
            if rel not in referenced:
                orphans.append(rel)
    if orphans:
        notes.append(f"연결 안 된 미디어 파일 {len(orphans)}개 (예: {orphans[0]})")

    total = 0
    for dirpath, dirnames, files in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        total += sum(os.path.getsize(os.path.join(dirpath, f)) for f in files)
    notes.append(f"사이트 전체 용량 {total / 1048576:.1f}MB / 1024MB")

    for n in notes:
        print("  " + n)
    for e in errors:
        print("  [오류] " + e)
    print("점검 결과:", "통과" if not errors else f"오류 {len(errors)}건")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
