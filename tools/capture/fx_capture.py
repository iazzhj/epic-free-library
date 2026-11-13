"""
Epic 무료 에셋 라이브러리 — 이펙트 미리보기 녹화 (언리얼 에디터 안에서 실행)
대상: Unreal Engine 5.8 / Cascade 이펙트

일괄 모드 (BATCH = True, 기본) — 한 번 실행하면 끝까지 자동으로 진행합니다.
  1. 프로젝트에 들어 있는 Paragon 팩의 이펙트 목록을 추출합니다 (extract_effects.py).
  2. 검정 배경 촬영 레벨(/Game/EFL/FXCapture)에서 모든 이펙트를 렌더링합니다.
  3. 영상으로 변환하고 화면을 점검합니다 (encode_videos.py).
     빈 화면·작게 보임·가장자리 잘림·화면 전체 이펙트에 표시를 붙입니다.
  4. 너무 작거나 잘린 이펙트는 카메라 거리를 고쳐 다시 찍습니다 (최대 MAX_ROUNDS 회).
  5. 팩마다 upload_<팩 id>.zip 과 요약 보고서 batch_report.txt 를 만듭니다.
     → <프로젝트>/Saved/EpicFreeLibrary/

  중간에 에디터가 꺼져도 다시 실행하면 끝난 이펙트는 건너뛰고 이어서 진행합니다 (RESUME).
  Paragon 원본 에셋은 수정하지 않습니다. 새로 만드는 것은 /Game/EFL 폴더 안의 레벨과 시퀀스뿐입니다.

실행 전
  - extract_effects.py, fx_capture.py, encode_videos.py 세 파일을 같은 폴더에 두세요.
  - 편집 → 플러그인에서 'Movie Render Queue' 가 켜져 있어야 합니다.
  - ffmpeg 가 설치되어 있어야 합니다 (encode_videos.py 설명 참고).
  - 저장하지 않은 레벨 작업이 있다면 먼저 저장하세요. 이 스크립트는 촬영 레벨을 엽니다.

실행
  도구 → Python 스크립트 실행 → 이 파일 선택
  끝날 때까지 에디터를 닫지 마세요. 진행 상황은 출력 로그의 [EFL] 줄에 나옵니다.
  절전 모드가 켜지면 렌더링이 멈추므로, 밤새 돌릴 때는 Windows 절전을 '안 함'으로 바꿔 두세요.
"""

import builtins
import importlib.util
import json
import os
import time

import unreal

# ---------------------------------------------------------------- 설정
BATCH = True            # True: 추출→녹화→변환→재촬영→zip 까지 자동. False: 녹화만 (예전 방식)
PACK_FILTER = []        # 처리할 팩 id. 비우면 프로젝트에 있는 모든 Paragon 팩
SKIP_PACKS = ["paragon-greystone", "paragon-lt-belica", "paragon-feng-mao"]  # 이미 사이트에 등록한 팩
MAX_ROUNDS = 3          # 카메라 자동 조절 촬영 최대 횟수 (1이면 재촬영 없음)
AUTO_EXTRACT = True     # 시작할 때 이펙트 목록을 새로 추출
RESUME = True           # 이전 실행에서 끝난 이펙트는 건너뜀
SCRIPT_DIR = ""         # 세 스크립트가 있는 폴더. 비우면 이 파일이 있는 폴더 (찾지 못하면 여기에 경로 입력)
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
        for old in os.listdir(out_dir):  # 지난 회차 프레임이 섞이지 않게 비움
            if old.lower().endswith(".png"):
                os.remove(os.path.join(out_dir, old))
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
    if BATCH:
        if not success:
            unreal.log_warning("[EFL] 일부 렌더링이 실패했습니다. 렌더링된 이펙트만 이어서 처리합니다.")
        STATE["rendered"] = True  # 실제 처리는 다음 에디터 틱에서 (렌더러가 정리를 마친 뒤)
        return
    log("렌더링 종료 (성공: {0}). 이제 encode_videos.py 를 실행하세요.".format(success))
    log("프레임 위치: " + os.path.abspath(FRAMES_ROOT))


# ---------------------------------------------------------------- 일괄 모드
STATE = {"round": 0, "rendered": False, "todo": [], "tick": None, "packs": [], "export": None,
         "cam": None, "encoder": None, "ffmpeg": None, "start": 0.0, "reshot": 0}


def script_dir():
    if SCRIPT_DIR:
        return SCRIPT_DIR
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        raise RuntimeError("스크립트 폴더를 알 수 없습니다. fx_capture.py 맨 위 설정의 SCRIPT_DIR 에 "
                           "세 스크립트가 있는 폴더 경로를 넣으세요.")


def load_sibling(file_name):
    """같은 폴더의 스크립트를 자동 실행 없이 모듈로 불러옴."""
    here = script_dir()
    # 같은 폴더 → 상위 폴더 순으로 찾음 (저장소 구성: tools/extract_effects.py, tools/capture/*.py)
    candidates = [os.path.join(here, file_name), os.path.join(os.path.dirname(here), file_name)]
    path = next((c for c in candidates if os.path.exists(c)), None)
    if path is None:
        raise RuntimeError("{0} 이(가) 없습니다: {1} (세 스크립트를 같은 폴더에 두세요)".format(file_name, candidates[0]))
    builtins.EFL_NO_AUTORUN = True
    try:
        spec = importlib.util.spec_from_file_location("efl_" + file_name[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        builtins.EFL_NO_AUTORUN = False
    return mod


def read_json(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def select_packs(export):
    return [p for p in export.get("packs", [])
            if (not PACK_FILTER or p["id"] in PACK_FILTER) and p["id"] not in SKIP_PACKS]


def pick(effects):
    if not TEST_LIMIT:
        return effects
    named = [e for e in effects if e["name"] in TEST_NAMES]
    rest = [e for e in effects if e["name"] not in TEST_NAMES]
    return (named + rest)[:TEST_LIMIT]


def all_todo(packs):
    """렌더링할 (팩 id, 이펙트) 목록. RESUME 이면 지난 실행에서 끝난 이펙트는 뺌."""
    done = read_json(os.path.join(SAVED, "capture_result.json")) if RESUME else {}
    todo, skipped = [], 0
    for p in packs:
        keyed = [dict(e, key=k) for e, k in zip(p["effects"], effect_keys(p["effects"]))]
        for e in pick(keyed):
            if e.get("system") != "Cascade":
                continue
            if done.get(p["id"], {}).get(e["key"], {}).get("final"):
                skipped += 1
                continue
            todo.append((p["id"], e))
    if skipped:
        log("이전 실행에서 끝난 이펙트 {0}개는 건너뜁니다 (RESUME).".format(skipped))
    return todo


def start_round(todo):
    """시퀀스를 만들고 렌더링 시작. 렌더링이 끝나면 on_finished → after_round."""
    global _executor
    STATE["round"] += 1
    STATE["todo"] = todo
    r = STATE["round"]
    mrq = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    mrq.get_queue().delete_all_jobs()  # 지난 회차 작업이 시퀀스를 붙잡지 않게 먼저 비움
    load_plan()
    items = []
    with unreal.ScopedSlowTask(len(todo), "{0}회차 시퀀스 만드는 중".format(r)) as task:
        task.make_dialog(True)
        for pack_id, effect in todo:
            if task.should_cancel():
                stop("사용자가 취소했습니다.")
                return
            task.enter_progress_frame(1, effect["name"])
            try:
                seq_path, cam_info = make_sequence(pack_id, effect, STATE["cam"])
                items.append((pack_id, effect, seq_path, cam_info))
            except Exception as e:
                unreal.log_error("[EFL] 시퀀스 생성 실패 {0}: {1}".format(effect["name"], e))
    level_sub.save_current_level()
    if not items:
        unreal.log_error("[EFL] 렌더링할 시퀀스가 없습니다.")
        finish()
        return
    minutes = len(items) * (SECONDS + 4) / 60.0  # 이펙트당 녹화 시간 + 준비 시간 대략
    log("{0}회차 렌더링 시작: 이펙트 {1}개, 예상 약 {2:.0f}분".format(r, len(items), minutes))
    queue_jobs(items)
    _executor = mrq.render_queue_with_executor(unreal.MoviePipelinePIEExecutor)
    if _executor:
        _executor.on_executor_finished_delegate.add_callable_unique(on_finished)
    else:
        stop("렌더링을 시작하지 못했습니다. 창 → 시네마틱스 → 무비 렌더 큐 창에서 작업이 보이는지 확인하세요.")


def after_round():
    """변환·점검 후 다시 찍을 이펙트를 골라 다음 회차를 시작하거나 마무리."""
    r, enc = STATE["round"], STATE["encoder"]
    by_pack = {}
    for pack_id, effect in STATE["todo"]:
        by_pack.setdefault(pack_id, []).append(effect)
    log("{0}회차 변환·점검 중 (팩 {1}개)".format(r, len(by_pack)))
    processed = set()
    for pack_id, effects in by_pack.items():
        done = enc.process_pack(SAVED, pack_id, {e["key"] for e in effects}, STATE["ffmpeg"], r)
        processed |= {(pack_id, k) for k in done}

    result_path = os.path.join(SAVED, "capture_result.json")
    result, plans = read_json(result_path), read_json(PLAN_FILE)
    nxt, failed = [], 0
    for pack_id, effect in STATE["todo"]:
        entry = result.get(pack_id, {}).get(effect["key"])
        if entry is None or (pack_id, effect["key"]) not in processed:
            failed += 1
            continue  # 렌더링 실패(프레임 없음): 다음 실행에서 다시 시도 (final 아님)
        if r < MAX_ROUNDS and enc.needs_reshoot(entry, plans.get(pack_id, {}).get(effect["key"])):
            nxt.append((pack_id, effect))
        else:
            entry["final"] = True
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    if failed:
        unreal.log_warning("[EFL] 프레임이 없어 처리하지 못한 이펙트 {0}개 (다시 실행하면 이것만 재시도)".format(failed))
    if nxt:
        STATE["reshot"] += len(nxt)
        log("카메라를 고쳐 다시 찍을 이펙트 {0}개 → {1}회차".format(len(nxt), r + 1))
        start_round(nxt)
    else:
        finish()


def on_tick(delta):
    if not STATE["rendered"]:
        return
    STATE["rendered"] = False
    try:
        after_round()
    except Exception:
        import traceback
        for line in traceback.format_exc().splitlines():
            unreal.log_error("[EFL] " + line)
        stop("변환 중 오류로 멈췄습니다. 다시 실행하면 끝난 이펙트는 건너뛰고 이어서 진행합니다.")


def stop(msg):
    if STATE["tick"] is not None:
        unreal.unregister_slate_post_tick_callback(STATE["tick"])
        STATE["tick"] = None
    unreal.log_error("[EFL] " + msg)


def finish():
    """팩마다 zip 과 요약 보고서를 만들고 종료."""
    enc = STATE["encoder"]
    result = read_json(os.path.join(SAVED, "capture_result.json"))
    export = STATE["export"]
    lines = ["Epic 무료 에셋 라이브러리 — 일괄 녹화 보고서",
             "날짜: {0}".format(time.strftime("%Y-%m-%d %H:%M")),
             "걸린 시간: {0:.0f}분, 카메라 조절 재촬영: {1}회".format((time.time() - STATE["start"]) / 60, STATE["reshot"]),
             "",
             "{0:<28}{1:>6}{2:>6}{3:>8}{4:>8}{5:>8}{6:>8}{7:>9}".format(
                 "팩", "이펙트", "영상", "빈화면", "작게", "잘림", "화면전체", "Niagara")]
    zips = []
    for p in STATE["packs"]:
        pr = result.get(p["id"], {})
        if not pr:
            continue
        s = enc.summarize(pr)
        niagara = sum(1 for e in p["effects"] if e.get("system") != "Cascade")
        lines.append("{0:<28}{1:>6}{2:>6}{3:>8}{4:>8}{5:>8}{6:>8}{7:>9}".format(
            p["id"], len(p["effects"]), s["video"], s["empty"], s["faint"], s["clipped"], s["fullscreen"], niagara))
        z = enc.build_zip(SAVED, p["id"], {"engine": export.get("engine"), "packs": [p]})
        zips.append("{0} ({1}MB)".format(os.path.basename(z), round(os.path.getsize(z) / 1048576, 1)))
    lines += ["", "만들어진 파일 (Claude 에게 보낼 파일):"] + ["  " + z for z in zips]
    lines += ["", "표시 설명: 빈화면=보이는 입자 없음, 작게=화면의 0.2% 미만, 잘림=화면 밖으로 나감, "
              "화면전체=화면 60% 이상을 덮음, Niagara=이 스크립트가 녹화하지 않는 형식"]
    report = os.path.join(SAVED, "batch_report.txt")
    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    if STATE["tick"] is not None:
        unreal.unregister_slate_post_tick_callback(STATE["tick"])
        STATE["tick"] = None
    for line in lines:
        log(line)
    log("일괄 녹화 완료. 보고서: " + os.path.abspath(report))


def batch_main():
    log("일괄 녹화 시작")
    init()
    STATE["start"] = time.time()
    STATE["round"], STATE["reshot"] = 0, 0
    STATE["encoder"] = load_sibling("encode_videos.py")
    STATE["ffmpeg"] = STATE["encoder"].find_ffmpeg()  # 렌더링 전에 ffmpeg 부터 확인
    if AUTO_EXTRACT:
        log("1/3 이펙트 목록 추출 중")
        load_sibling("extract_effects.py").main()
    export = read_json(EXPORT_FILE)
    if not export:
        unreal.log_error("[EFL] effects_export.json 이 없습니다. 프로젝트에 Paragon 팩이 있는지 확인하세요.")
        return
    STATE["export"] = export
    STATE["packs"] = select_packs(export)
    if not STATE["packs"]:
        unreal.log_error("[EFL] 처리할 팩이 없습니다. PACK_FILTER·SKIP_PACKS 설정을 확인하세요.")
        return
    log("대상 팩 {0}개: {1}".format(len(STATE["packs"]), ", ".join(p["id"] for p in STATE["packs"])))
    os.makedirs(FRAMES_ROOT, exist_ok=True)
    log("2/3 촬영 레벨 준비 중")
    STATE["cam"] = setup_map()
    todo = all_todo(STATE["packs"])
    if STATE["tick"] is None:
        STATE["tick"] = unreal.register_slate_post_tick_callback(on_tick)
    log("3/3 녹화 시작 (최대 {0}회차까지 카메라 자동 조절)".format(MAX_ROUNDS))
    if todo:
        start_round(todo)
    else:
        log("새로 녹화할 이펙트가 없습니다. zip 과 보고서만 다시 만듭니다.")
        finish()


def main():
    global _executor
    if BATCH:
        batch_main()
        return
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
    packs = select_packs(export)
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
