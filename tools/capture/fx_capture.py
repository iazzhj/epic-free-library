"""
Epic 무료 에셋 라이브러리 — 이펙트 미리보기 녹화 (1단계: 언리얼 에디터 안에서 실행)
대상: Unreal Engine 5.8 / Cascade 이펙트

하는 일
  1. 검정 배경 촬영 레벨(/Game/EFL/FXCapture)을 만들거나 다시 불러옵니다.
  2. effects_export.json 에 있는 이펙트마다 레벨 시퀀스를 만듭니다.
  3. 무비 렌더 큐로 이펙트마다 PNG 프레임을 렌더링합니다.
     → <프로젝트>/Saved/EpicFreeLibrary/frames/<팩 id>/<이펙트 이름>/0000.png ...

  Paragon 원본 에셋은 수정하지 않습니다. 새로 만드는 것은 /Game/EFL 폴더 안의 레벨과 시퀀스뿐입니다.

실행 전
  - 먼저 extract_effects.py 를 실행해 effects_export.json 이 있어야 합니다.
  - 편집 → 플러그인에서 'Movie Render Queue' 가 켜져 있어야 합니다.
  - 저장하지 않은 레벨 작업이 있다면 먼저 저장하세요. 이 스크립트는 촬영 레벨을 엽니다.

실행
  도구 → Python 스크립트 실행 → 이 파일 선택
  렌더링이 끝날 때까지 에디터를 닫지 마세요. 진행 상황은 출력 로그의 [EFL] 줄에 나옵니다.
"""

import json
import os

import unreal

# ---------------------------------------------------------------- 설정
PACK_FILTER = ["paragon-greystone"]  # 처리할 팩 id. 비우면 effects_export.json 의 전체 팩
TEST_LIMIT = 0          # 시험 실행용: 팩마다 앞에서 몇 개만 렌더링할지. 0 이면 전부
# 시험 실행 때 이 이름들을 우선 렌더링 (화면에 잘 보이는 이펙트). 비우면 목록 앞에서부터
TEST_NAMES = ["P_Greystone_SwordSpinning_01", "P_Greystone_LeapAOE_GroundSmash", "P_Greystone_Primary_Impact"]
SECONDS = 6             # 이펙트마다 녹화할 길이(초). 루프 판정은 이 길이 기준
FPS = 30
WIDTH, HEIGHT = 640, 360

CAMERA_LOCATION = unreal.Vector(-850.0, 0.0, 420.0)  # 이펙트(원점)를 비스듬히 내려다보는 위치
CAMERA_TARGET = unreal.Vector(0.0, 0.0, 60.0)
CAMERA_FOV = 60.0
EXPOSURE_BIAS = 0.0     # 영상이 너무 어두우면 +1~+2, 너무 밝으면 -1

MAP_PATH = "/Game/EFL/FXCapture"
SEQ_ROOT = "/Game/EFL/Sequences"
# ----------------------------------------------------------------

SAVED = os.path.join(unreal.Paths.project_saved_dir(), "EpicFreeLibrary")
EXPORT_FILE = os.path.join(SAVED, "effects_export.json")
FRAMES_ROOT = os.path.join(SAVED, "frames")
# encode_videos.py 가 만드는 이펙트별 카메라 계획. 있으면 이펙트마다 거리·조준점을 바꿔 촬영
PLAN_FILE = os.path.join(SAVED, "camera_plan.json")
PLAN = {}


def load_plan():
    global PLAN
    if os.path.exists(PLAN_FILE):
        with open(PLAN_FILE, encoding="utf-8") as f:
            PLAN = json.load(f)
        n = sum(len(v) for v in PLAN.values())
        unreal.log("[EFL] 카메라 계획 불러옴: 이펙트 {0}개 (camera_plan.json)".format(n))
    else:
        PLAN = {}
        unreal.log("[EFL] 카메라 계획 없음: 모든 이펙트를 기본 거리로 촬영")


def camera_for(pack_id, name):
    """이펙트별 카메라 위치·회전. 방향은 기본 카메라와 같고 거리와 조준점만 바뀜."""
    base_t = CAMERA_TARGET
    base_d = (CAMERA_LOCATION - base_t)
    dist0 = base_d.length()
    direction = base_d * (1.0 / dist0)  # 조준점 → 카메라 방향
    p = PLAN.get(pack_id, {}).get(name)
    if p:
        t = unreal.Vector(*p["target"])
        d = float(p["distance"])
    else:
        t, d = base_t, dist0
    loc = t + direction * d
    rot = unreal.MathLibrary.find_look_at_rotation(loc, t)
    return loc, rot, {"target": [t.x, t.y, t.z], "distance": d, "planned": bool(p)}

def effect_keys(effects):
    """팩 안에서 이펙트를 구분하는 키. 이름이 겹치면 '이름__상위폴더'.
    저장소의 tools/import_export.py 와 같은 규칙 (사이트 데이터와 맞아야 함)."""
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


level_sub = actor_sub = asset_tools = None


def log(msg):
    unreal.log("[EFL] " + msg)


def init():
    global level_sub, actor_sub, asset_tools
    level_sub = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    if not hasattr(unreal, "MoviePipelineQueueSubsystem"):
        raise RuntimeError("Movie Render Queue 플러그인이 꺼져 있습니다. 편집 → 플러그인에서 켜고 에디터를 재시작하세요.")


# ---------------------------------------------------------------- 촬영 레벨
def find_actor(cls, label):
    for a in actor_sub.get_all_level_actors():
        if isinstance(a, cls) and a.get_actor_label() == label:
            return a
    return None


def ensure_actor(cls, label, location=unreal.Vector(0, 0, 0), rotation=unreal.Rotator(0, 0, 0)):
    a = find_actor(cls, label)
    if a is None:
        a = actor_sub.spawn_actor_from_class(cls, location, rotation)
        a.set_actor_label(label)
    else:
        a.set_actor_location_and_rotation(location, rotation, False, False)
    return a


def setup_map():
    if unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        level_sub.load_level(MAP_PATH)
        log("촬영 레벨 불러옴: " + MAP_PATH)
    else:
        level_sub.new_level(MAP_PATH)
        log("촬영 레벨 생성: " + MAP_PATH)

    # 게임 모드를 기본값으로 바꿔 삼인칭 캐릭터가 화면에 나오지 않게 함
    world = unreal.EditorLevelLibrary.get_editor_world()
    try:
        world.get_world_settings().set_editor_property("default_game_mode", unreal.GameModeBase)
    except Exception as e:
        unreal.log_warning("[EFL] 게임 모드 설정 실패(무시하고 진행): " + str(e))

    # 렌더링 중 생기는 기본 폰은 카메라 뒤 먼 곳에 생성
    ensure_actor(unreal.PlayerStart, "EFL_PlayerStart", unreal.Vector(0, 0, -50000))

    # 조명: 배경은 검정 그대로, 조명을 받는 입자만 보이도록 방향광 하나
    ensure_actor(unreal.DirectionalLight, "EFL_Light", unreal.Vector(0, 0, 500), unreal.Rotator(0, -45, -30))

    # 노출 고정·모션 블러 끄기 (자동 노출이 검정 배경에서 화면을 밝혀 버리는 것을 막음)
    ppv = ensure_actor(unreal.PostProcessVolume, "EFL_PostProcess")
    ppv.set_editor_property("unbound", True)
    s = ppv.get_editor_property("settings")
    s.set_editor_property("override_auto_exposure_method", True)
    s.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    s.set_editor_property("override_auto_exposure_apply_physical_camera_exposure", True)
    s.set_editor_property("auto_exposure_apply_physical_camera_exposure", False)
    s.set_editor_property("override_auto_exposure_bias", True)
    s.set_editor_property("auto_exposure_bias", EXPOSURE_BIAS)
    s.set_editor_property("override_motion_blur_amount", True)
    s.set_editor_property("motion_blur_amount", 0.0)
    ppv.set_editor_property("settings", s)

    # 카메라: 초점 흐림을 끄고 원점을 바라보게
    rot = unreal.MathLibrary.find_look_at_rotation(CAMERA_LOCATION, CAMERA_TARGET)
    cam = ensure_actor(unreal.CineCameraActor, "EFL_Camera", CAMERA_LOCATION, rot)
    cc = cam.get_cine_camera_component()
    fs = cc.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.DISABLE)
    cc.set_editor_property("focus_settings", fs)
    cc.set_field_of_view(CAMERA_FOV)

    level_sub.save_current_level()
    return cam


# ---------------------------------------------------------------- 시퀀스
def binding_id(seq, binding):
    try:
        return unreal.MovieSceneSequenceExtensions.get_portable_binding_id(seq, seq, binding)
    except Exception:
        return seq.get_binding_id(binding)


def make_sequence(pack_id, effect, cam):
    name = "SEQ_" + effect["key"]
    folder = SEQ_ROOT + "/" + pack_id
    path = folder + "/" + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    seq = asset_tools.create_asset(name, folder, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
    frames = SECONDS * FPS
    seq.set_display_rate(unreal.FrameRate(FPS, 1))
    seq.set_playback_start(0)
    seq.set_playback_end(frames)

    # 이펙트: 임시 이미터 액터를 만들어 시퀀스 전용(스폰어블)으로 복사한 뒤 레벨에서는 지움
    ps = unreal.load_asset(effect["object"])
    if ps is None:
        raise RuntimeError("이펙트 에셋을 불러오지 못했습니다: " + effect["object"])
    tmp = actor_sub.spawn_actor_from_class(unreal.Emitter, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    tmp.set_template(ps)
    comp = tmp.get_component_by_class(unreal.ParticleSystemComponent)
    if comp:
        comp.set_editor_property("template", ps)
        comp.set_editor_property("auto_activate", True)
    fx_binding = seq.add_spawnable_from_instance(tmp)
    actor_sub.destroy_actor(tmp)

    # 시퀀스에 복사된 이미터에 이펙트가 실제로 들어갔는지 확인
    tcomp = None
    try:
        tpl = fx_binding.get_object_template()
        # 템플릿 액터는 등록 전 상태라 get_component_by_class 가 비어 있을 수 있어 속성으로 직접 가져옴
        try:
            tcomp = tpl.get_editor_property("particle_system_component")
        except Exception:
            tcomp = tpl.get_component_by_class(unreal.ParticleSystemComponent)
        if tcomp is None:
            raise RuntimeError("시퀀스 이미터에 파티클 컴포넌트가 없음")
        before = tcomp.get_editor_property("template")
        if before is None:
            tcomp.set_editor_property("template", ps)
        tcomp.set_editor_property("auto_activate", True)
        log("  이미터 확인: {0} (템플릿 {1})".format(
            effect["name"], "다시 지정함" if before is None else "정상"))
    except Exception as e:
        unreal.log_warning("[EFL]   이미터 확인 실패 ({0}): {1}".format(effect["name"], e))
    spawn_tracks = fx_binding.find_tracks_by_type(unreal.MovieSceneSpawnTrack)
    track = spawn_tracks[0] if spawn_tracks else fx_binding.add_track(unreal.MovieSceneSpawnTrack)
    sections = track.get_sections()
    sec = sections[0] if sections else track.add_section()
    sec.set_range(0, frames)
    try:
        sec.get_all_channels()[0].set_default(True)
    except Exception:
        pass

    # 파티클 토글 트랙: 0프레임에 '활성화' 키. 시퀀서·렌더 큐에서 Cascade 이펙트를 확실히 켜는 표준 방법
    try:
        ptrack = fx_binding.add_track(unreal.MovieSceneParticleTrack)
        psec = ptrack.add_section()
        psec.set_range(0, frames)
        ch = psec.get_all_channels()[0]
        key_enum = getattr(unreal, "ParticleKey", None) or getattr(unreal, "EParticleKey", None)
        ch.add_key(unreal.FrameNumber(0), key_enum.ACTIVATE if key_enum else 0)
    except Exception as e:
        unreal.log_warning("[EFL]   파티클 토글 트랙 추가 실패 ({0}): {1}".format(effect["name"], e))

    # 카메라 컷
    cam_binding = seq.add_possessable(cam)
    try:
        cut_track = seq.add_track(unreal.MovieSceneCameraCutTrack)
    except Exception:
        cut_track = seq.add_master_track(unreal.MovieSceneCameraCutTrack)
    cut = cut_track.add_section()
    cut.set_range(0, frames)
    cut.set_camera_binding_id(binding_id(seq, cam_binding))

    # 이펙트별 카메라 위치: 카메라에 고정값 트랜스폼 트랙을 넣어 이 시퀀스에서만 옮김
    loc, rot, info = camera_for(pack_id, effect["key"])
    if info["planned"]:
        try:
            tt = cam_binding.add_track(unreal.MovieScene3DTransformTrack)
            ts = tt.add_section()
            ts.set_range(0, frames)
            values = {"Location.X": loc.x, "Location.Y": loc.y, "Location.Z": loc.z,
                      "Rotation.X": rot.roll, "Rotation.Y": rot.pitch, "Rotation.Z": rot.yaw,
                      "Scale.X": 1.0, "Scale.Y": 1.0, "Scale.Z": 1.0}
            order = list(values.values())
            for i, ch in enumerate(ts.get_all_channels()):
                key = str(ch.channel_name) if hasattr(ch, "channel_name") else str(ch.get_name())
                ch.set_default(values.get(key, order[i] if i < len(order) else 1.0))
        except Exception as e:
            unreal.log_warning("[EFL]   카메라 위치 지정 실패, 기본 위치로 촬영 ({0}): {1}".format(effect["name"], e))
            info = camera_for("", "")[2]

    unreal.EditorAssetLibrary.save_loaded_asset(seq)
    return path, info


# ---------------------------------------------------------------- 렌더 큐
_executor = None  # 렌더링이 끝날 때까지 참조 유지


def queue_jobs(items):
    mrq = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    queue = mrq.get_queue()
    queue.delete_all_jobs()
    map_obj = MAP_PATH + "." + MAP_PATH.split("/")[-1]
    for pack_id, effect, seq_path, cam_info in items:
        job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
        job.job_name = pack_id + "/" + effect["key"]
        job.map = unreal.SoftObjectPath(map_obj)
        job.sequence = unreal.SoftObjectPath(seq_path + "." + seq_path.split("/")[-1])
        cfg = job.get_configuration()
        cfg.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
        png = cfg.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
        try:
            # 투명도 채널을 빼야 일반 사진 뷰어에서 검정 배경이 그대로 보임
            png.set_editor_property("write_alpha", False)
        except Exception:
            pass
        out = cfg.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
        out_dir = os.path.join(FRAMES_ROOT, pack_id, effect["key"])
        os.makedirs(out_dir, exist_ok=True)
        # 어떤 카메라로 찍었는지 기록 → encode_videos.py 가 다음 계획을 계산할 때 사용
        cam_info = dict(cam_info, fov=CAMERA_FOV, width=WIDTH, height=HEIGHT,
                        base_location=[CAMERA_LOCATION.x, CAMERA_LOCATION.y, CAMERA_LOCATION.z],
                        base_target=[CAMERA_TARGET.x, CAMERA_TARGET.y, CAMERA_TARGET.z])
        with open(os.path.join(out_dir, "camera.json"), "w", encoding="utf-8") as f:
            json.dump(cam_info, f)
        out.set_editor_property("output_directory", unreal.DirectoryPath(out_dir))
        out.set_editor_property("output_resolution", unreal.IntPoint(WIDTH, HEIGHT))
        out.set_editor_property("file_name_format", "{frame_number}")
        out.set_editor_property("zero_pad_frame_numbers", 4)
        out.set_editor_property("override_existing_output", True)
    return mrq


def on_finished(executor, success):
    log("렌더링 종료 (성공: {0}). 이제 encode_videos.py 를 실행하세요.".format(success))
    log("프레임 위치: " + os.path.abspath(FRAMES_ROOT))


def main():
    global _executor
    log("녹화 스크립트 시작")
    init()
    log("1/4 준비 확인 완료 (설정 파일: {0})".format(os.path.abspath(EXPORT_FILE)))
    if not os.path.exists(EXPORT_FILE):
        unreal.log_error("[EFL] effects_export.json 이 없습니다. extract_effects.py 를 먼저 실행하세요.")
        return
    with open(EXPORT_FILE, encoding="utf-8") as f:
        export = json.load(f)
    os.makedirs(FRAMES_ROOT, exist_ok=True)
    load_plan()

    log("2/4 촬영 레벨 준비 중")
    cam = setup_map()
    log("3/4 이펙트 시퀀스 만드는 중")
    items = []
    packs = [p for p in export["packs"] if not PACK_FILTER or p["id"] in PACK_FILTER]
    def pick(effects):
        if not TEST_LIMIT:
            return effects
        named = [e for e in effects if e["name"] in TEST_NAMES]
        rest = [e for e in effects if e["name"] not in TEST_NAMES]
        return (named + rest)[:TEST_LIMIT]
    todo = []
    for p in packs:
        keyed = [dict(e, key=k) for e, k in zip(p["effects"], effect_keys(p["effects"]))]
        todo += [(p["id"], e) for e in pick(keyed) if e.get("system") == "Cascade"]
    with unreal.ScopedSlowTask(len(todo), "이펙트 시퀀스 만드는 중") as task:
        task.make_dialog(True)
        for pack_id, effect in todo:
            if task.should_cancel():
                return
            task.enter_progress_frame(1, effect["name"])
            try:
                seq_path, cam_info = make_sequence(pack_id, effect, cam)
                items.append((pack_id, effect, seq_path, cam_info))
            except Exception as e:
                unreal.log_error("[EFL] 시퀀스 생성 실패 {0}: {1}".format(effect["name"], e))
    level_sub.save_current_level()
    if not items:
        unreal.log_error("[EFL] 렌더링할 시퀀스가 없습니다.")
        return
    log("4/4 시퀀스 {0}개 준비. 렌더링을 시작합니다 (이펙트당 {1}초, {2}fps).".format(len(items), SECONDS, FPS))
    mrq = queue_jobs(items)
    _executor = mrq.render_queue_with_executor(unreal.MoviePipelinePIEExecutor)
    if _executor:
        _executor.on_executor_finished_delegate.add_callable_unique(on_finished)
    else:
        unreal.log_error("[EFL] 렌더링을 시작하지 못했습니다. 창 → 시네마틱스 → 무비 렌더 큐 창에서 작업이 보이는지 확인하세요.")


try:
    main()
except Exception:
    import traceback
    for line in traceback.format_exc().splitlines():
        unreal.log_error("[EFL] " + line)
