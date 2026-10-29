"""
Epic 무료 에셋 라이브러리 — 이펙트 목록 추출 스크립트
대상: Unreal Engine 5.8 에디터 (Python Editor Script Plugin 필요)

하는 일
  /Game 아래 Paragon 팩 폴더에서 파티클 이펙트(Cascade ParticleSystem, Niagara System)를 찾아
  이름·경로·루프 여부·길이를 JSON 파일 하나로 저장합니다.
  에셋을 수정하거나 저장하지 않습니다. 읽기만 합니다.

실행
  에디터 상단 메뉴 [도구] → [Python 스크립트 실행] → 이 파일 선택
  결과: <프로젝트>/Saved/EpicFreeLibrary/effects_export.json
"""

import json
import os
import re

import unreal

# ---------------------------------------------------------------- 설정
# 비워 두면 /Game 바로 아래의 Paragon* 폴더를 모두 처리합니다.
# 특정 팩만 하려면 폴더 이름을 넣으세요. 예: ["ParagonGreystone"]
PACK_FILTER = []

# 폴더 이름과 라이브러리 사이트 id가 자동으로 맞지 않을 때 직접 지정합니다.
# 예: {"ParagonGRIMexe": "paragon-grim-exe"}
ID_OVERRIDE = {}

# 루프·길이 정보를 읽기 위해 이펙트 에셋을 메모리에 불러올지 여부.
# 팩이 많아 느리면 False로 바꾸세요. (이름·경로는 그대로 추출됩니다)
READ_TIMING = True

EFFECT_CLASSES = {"ParticleSystem", "NiagaraSystem"}
# ----------------------------------------------------------------


def class_name(ad):
    """AssetData의 클래스 이름 (UE5.1 이후 asset_class_path 사용)."""
    try:
        return str(ad.asset_class_path.asset_name)
    except Exception:
        return str(ad.get_editor_property("asset_class"))


def site_id(folder):
    if folder in ID_OVERRIDE:
        return ID_OVERRIDE[folder]
    name = folder[len("Paragon"):] if folder.startswith("Paragon") else folder
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return "paragon-" + slug


def pack_folders(registry):
    try:
        subs = [str(p) for p in registry.get_sub_paths("/Game", False)]
    except Exception:
        subs = [p.rstrip("/") for p in unreal.EditorAssetLibrary.list_assets("/Game", False, True)]
    folders = sorted({p.rstrip("/").split("/")[-1] for p in subs})
    folders = [f for f in folders if f.startswith("Paragon")]
    if PACK_FILTER:
        folders = [f for f in folders if f in PACK_FILTER]
    return folders


def cascade_timing(asset):
    """Cascade 이펙트의 루프 여부와 길이(초). 읽을 수 없으면 (None, None)."""
    try:
        emitters = asset.get_editor_property("emitters")
    except Exception:
        return None, None
    looping, longest = False, 0.0
    try:
        for em in emitters:
            if em is None:
                continue
            lod = em.get_editor_property("lod_levels")[0]
            req = lod.get_editor_property("required_module")
            loops = int(req.get_editor_property("emitter_loops"))
            dur = float(req.get_editor_property("emitter_duration"))
            delay = float(req.get_editor_property("emitter_delay"))
            if loops == 0:
                looping = True
            longest = max(longest, delay + dur * max(loops, 1))
    except Exception:
        return None, None
    return looping, round(longest, 2)


def relative_path(package_path, folder):
    """'/Game/ParagonGreystone/FX/Particles/Abilities/ClearAPath' → 'Greystone/Abilities/ClearAPath'"""
    root = "/Game/" + folder
    rel = package_path[len(root):].strip("/") if package_path.startswith(root) else package_path
    for prefix in ("FX/Particles/", "FX/"):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
            break
    if rel.endswith("/FX"):
        rel = rel[:-3]
    hero = folder[len("Paragon"):] if folder.startswith("Paragon") else folder
    if rel == hero or rel.startswith(hero + "/"):
        return rel
    return hero + ("/" + rel if rel else "")


def main():
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    folders = pack_folders(registry)
    if not folders:
        unreal.log_warning("[EFL] /Game 아래에서 Paragon 폴더를 찾지 못했습니다. 팩이 이 프로젝트에 추가되었는지 확인하세요.")
        return

    packs = []
    with unreal.ScopedSlowTask(len(folders), "이펙트 목록 추출 중") as task:
        task.make_dialog(True)
        for folder in folders:
            if task.should_cancel():
                break
            task.enter_progress_frame(1, folder)
            assets = registry.get_assets_by_path("/Game/" + folder, True)
            effects = []
            for ad in assets:
                cls = class_name(ad)
                if cls not in EFFECT_CLASSES:
                    continue
                loop, duration = None, None
                if READ_TIMING and cls == "ParticleSystem":
                    try:
                        loop, duration = cascade_timing(ad.get_asset())
                    except Exception:
                        pass
                effects.append({
                    "name": str(ad.asset_name),
                    "path": relative_path(str(ad.package_path), folder),
                    "loop": loop,
                    "duration": duration,
                    "system": "Cascade" if cls == "ParticleSystem" else "Niagara",
                    "object": str(ad.package_name) + "." + str(ad.asset_name),
                })
            effects.sort(key=lambda e: (e["path"], e["name"]))
            packs.append({"folder": folder, "id": site_id(folder), "count": len(effects), "effects": effects})
            unreal.log("[EFL] {0} → {1}: 이펙트 {2}개".format(folder, site_id(folder), len(effects)))

    out_dir = os.path.join(unreal.Paths.project_saved_dir(), "EpicFreeLibrary")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "effects_export.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "engine": unreal.SystemLibrary.get_engine_version(),
            "packs": packs,
        }, f, ensure_ascii=False, indent=2)

    total = sum(p["count"] for p in packs)
    unreal.log("[EFL] 완료: 팩 {0}개, 이펙트 {1}개".format(len(packs), total))
    unreal.log("[EFL] 저장 위치: " + os.path.abspath(out_file))


main()
