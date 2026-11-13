"""
Epic 무료 에셋 라이브러리 — 이펙트 미리보기 녹화 (2단계: 영상 변환·측정)

하는 일
  fx_capture.py 가 렌더링한 PNG 프레임을 읽어
  1. 프레임마다 밝은 픽셀 수를 세어 이펙트가 언제 끝나는지 측정합니다.
     - 녹화 끝까지 보이면 Loop: Yes, 중간에 사라지면 Loop: No + 길이(초)
  2. 화면 상태를 자동으로 점검해 표시를 붙입니다 (flags).
     - empty      빈 화면: 보이는 입자가 없음 (광원·카메라 효과, 궤적 이펙트 등)
     - faint      작게 보임: 가장 클 때도 화면의 아주 작은 부분만 차지
     - clipped    가장자리 잘림: 이펙트가 화면 밖으로 나감
     - fullscreen 화면 전체: 화면 대부분을 덮는 섬광·후처리형 이펙트
  3. 웹용 webm 영상과 대표 이미지(jpg)를 만듭니다.
  4. 결과를 묶어 upload_<팩 id>.zip 으로 저장합니다. 이 zip 을 Claude 에게 보내면 사이트에 반영됩니다.

  fx_capture.py 의 일괄 모드는 이 파일을 불러와 자동으로 실행하므로, 그때는 따로 실행하지 않아도 됩니다.

필요한 것
  ffmpeg (Windows: 명령 프롬프트에서  winget install Gyan.FFmpeg  실행 후 에디터 재시작)

실행 (따로 실행할 때)
  언리얼 에디터: 도구 → Python 스크립트 실행 → 이 파일 선택
  또는 일반 파이썬: python encode_videos.py "<프로젝트>/Saved/EpicFreeLibrary"
"""

import builtins
import json
import os
import shutil
import subprocess
import sys
import threading
import zipfile

# ---------------------------------------------------------------- 설정
FFMPEG = ""          # 비우면 PATH 에서 찾음. 못 찾으면 ffmpeg.exe 전체 경로를 넣으세요
FPS = 30             # fx_capture.py 와 같게
THRESHOLD = 24       # 0~255. 이보다 밝은 픽셀을 '보이는 것'으로 판단
MIN_PIXELS = 4       # 한 프레임에서 밝은 픽셀이 이 수 이상이면 이펙트가 보이는 프레임
TAIL_SECONDS = 0.5   # 녹화 마지막 이 구간에도 보이면 루프로 판단
PAD_SECONDS = 0.3    # 끝나는 이펙트는 사라진 뒤 이만큼 여유를 두고 자름
GAP_SECONDS = 0.3    # 이보다 긴 빈 구간이 있으면 '반복 재생되는 단발 이펙트'로 판단
CRF = 40             # 영상 화질 (낮을수록 고화질·대용량, 32~45 권장)
ANALYZE_W, ANALYZE_H = 320, 180

# 화면 점검 기준 (분석 화면 320x180 = 57,600 픽셀 기준 비율)
FAINT_RATIO = 0.002       # 가장 클 때 밝은 픽셀이 화면의 0.2% 미만이면 '작게 보임'
FULLSCREEN_RATIO = 0.6    # 한 프레임이라도 화면의 60% 이상이 밝으면 '화면 전체'
# 다음 회차에 다시 찍을 기준 (fx_capture.py 일괄 모드가 사용)
RESHOOT_FILL = (0.30, 0.85)   # 이펙트가 화면에서 차지하는 비율이 이 범위를 벗어나면 다시 촬영

FLAG_LABELS = {"empty": "빈 화면", "faint": "작게 보임", "clipped": "가장자리 잘림", "fullscreen": "화면 전체"}


def analyze(counts, fps=FPS):
    """밝은 픽셀 수 목록으로 재생 형태를 판정.
    반환: dict(pattern, loop, duration, start, end, poster) 또는 None(보이는 것 없음)
      pattern: 'loop'   녹화 끝까지 계속 보임
               'burst'  한 번 터지고 끝남
               'repeat' 미리보기에서 주기적으로 다시 터지는 단발 이펙트 (첫 1회만 사용)"""
    n = len(counts)
    vis = [c >= MIN_PIXELS for c in counts]
    gap = max(1, int(GAP_SECONDS * fps))
    segs, s, last = [], None, None
    for i, v in enumerate(vis):
        if not v:
            continue
        if s is None:
            s = i
        elif i - last > gap:
            segs.append((s, last))
            s = i
        last = i
    if s is None:
        return None
    segs.append((s, last))
    first = segs[0]
    start = max(0, first[0] - 2)
    pad = int(PAD_SECONDS * fps)
    if len(segs) == 1 and first[1] >= n - int(TAIL_SECONDS * fps):
        return {"pattern": "loop", "loop": True, "duration": None,
                "start": start, "end": n, "poster": start + int((n - start) * 0.6)}
    seg_len = first[1] - first[0] + 1
    end = min(n, first[1] + 1 + pad)
    if len(segs) > 1:
        end = min(end, segs[1][0])
    return {"pattern": "repeat" if len(segs) > 1 else "burst", "loop": False,
            "duration": max(0.1, round(seg_len / fps, 1)),  # 한두 프레임짜리 섬광도 0초로 표시되지 않게
            "start": start, "end": end, "poster": first[0] + max(2, int(seg_len * 0.15))}


def quality_flags(counts, a, m, w=ANALYZE_W, h=ANALYZE_H):
    """화면 점검 표시 목록과 가장 클 때의 화면 점유율(0~1)."""
    area = float(w * h)
    peak = (max(counts) / area) if counts else 0.0
    if a is None:
        return ["empty"], round(peak, 4)
    flags = []
    if peak < FAINT_RATIO:
        flags.append("faint")
    if peak >= FULLSCREEN_RATIO:
        flags.append("fullscreen")
    elif m and m.get("clipped"):
        flags.append("clipped")   # 화면 전체형은 잘림이 당연하므로 따로 표시하지 않음
    return flags, round(peak, 4)
# ----------------------------------------------------------------

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def saved_dir():
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        return sys.argv[1]
    try:
        import unreal
        return os.path.join(unreal.Paths.project_saved_dir(), "EpicFreeLibrary")
    except ImportError:
        sys.exit("사용법: python encode_videos.py <프로젝트>/Saved/EpicFreeLibrary")


def log(msg):
    try:
        import unreal
        unreal.log("[EFL] " + msg)
    except ImportError:
        print(msg)


def find_ffmpeg():
    exe = FFMPEG or shutil.which("ffmpeg")
    if not exe:
        local = os.environ.get("LOCALAPPDATA", "")
        winget = os.path.join(local, "Microsoft", "WinGet", "Links", "ffmpeg.exe")
        if os.path.exists(winget):
            exe = winget
    if not exe:
        raise RuntimeError("ffmpeg 를 찾지 못했습니다. 설치 후 에디터를 다시 시작하거나 FFMPEG 설정에 경로를 넣으세요.")
    return exe


def frame_files(folder):
    return sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))


def feed(proc, folder, files):
    for name in files:
        with open(os.path.join(folder, name), "rb") as f:
            proc.stdin.write(f.read())
    proc.stdin.close()


_BRIGHT = bytes(1 if i > THRESHOLD else 0 for i in range(256))


def bright_counts(ffmpeg, folder, files):
    """프레임마다 밝은 픽셀 수 (축소한 흑백 영상 기준)."""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "image2pipe", "-c:v", "png", "-i", "-",
           "-vf", "scale={0}:{1}:flags=area,format=gray".format(ANALYZE_W, ANALYZE_H),
           "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=NO_WINDOW)
    t = threading.Thread(target=feed, args=(proc, folder, files))
    t.start()
    size = ANALYZE_W * ANALYZE_H
    counts = []
    heat, used = 0, 0  # 픽셀마다 '밝았던 프레임 수'를 바이트 단위로 누적 (큰 정수 덧셈으로 한 번에)
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        mask = buf.translate(_BRIGHT)
        counts.append(mask.count(1))
        if len(counts) % 2 == 0 and used < 250:  # 2프레임마다 표본, 바이트 넘침 방지
            heat += int.from_bytes(mask, "big")
            used += 1
    t.join()
    proc.wait()
    bright_counts.heat = heat.to_bytes(size, "big") if used else bytes(size)
    return counts


# ---------------------------------------------------------------- 카메라 계획
TARGET_FILL = 0.55   # 이펙트가 화면 가로·세로 중 큰 쪽의 이 비율을 차지하도록 맞춤
MIN_DIST, MAX_DIST = 60.0, 3000.0


def measure(heat, w=ANALYZE_W, h=ANALYZE_H):
    """밝기 누적 지도에서 이펙트가 차지하는 영역(가로·세로 2~98% 구간, 0~1 비율)과 가장자리 잘림 여부."""
    cols = [sum(heat[c::w]) for c in range(w)]
    rows = [sum(heat[r * w:(r + 1) * w]) for r in range(h)]
    total = sum(cols)
    if total == 0:
        return None

    def span(hist):
        lo_cut, hi_cut, acc, lo, hi = total * 0.02, total * 0.98, 0, 0, len(hist) - 1
        for i, v in enumerate(hist):
            acc += v
            if acc >= lo_cut:
                lo = i
                break
        acc = 0
        for i, v in enumerate(hist):
            acc += v
            if acc >= hi_cut:
                hi = i
                break
        return lo / len(hist), (hi + 1) / len(hist)

    x0, x1 = span(cols)
    y0, y1 = span(rows)
    edge = max(sum(cols[:2]), sum(cols[-2:]), sum(rows[:2]), sum(rows[-2:])) / total
    return {"x0": x0, "x1": x1, "y0": y0, "y1": y1, "clipped": edge > 0.01}


def plan_camera(m, cam):
    """측정 결과와 촬영에 쓴 카메라(camera.json)로 다음 촬영의 거리·조준점 계산."""
    import math
    t = cam["target"]
    d0 = float(cam["distance"])
    bl, bt = cam["base_location"], cam["base_target"]
    f = [bt[i] - bl[i] for i in range(3)]                     # 카메라가 바라보는 방향
    fl = math.sqrt(sum(v * v for v in f))
    f = [v / fl for v in f]
    r = [-f[1], f[0], 0.0]                                      # 화면 오른쪽 (언리얼 좌표: Z 위)
    rl = math.sqrt(sum(v * v for v in r)) or 1.0
    r = [v / rl for v in r]
    u = [f[1] * r[2] - f[2] * r[1], f[2] * r[0] - f[0] * r[2], f[0] * r[1] - f[1] * r[0]]
    if u[2] < 0:
        u = [-v for v in u]
    half_w = d0 * math.tan(math.radians(cam.get("fov", 60.0)) / 2)
    half_h = half_w * cam.get("height", 360) / cam.get("width", 640)
    cx, cy = (m["x0"] + m["x1"]) / 2, (m["y0"] + m["y1"]) / 2
    dx, dy = (cx - 0.5) * 2 * half_w, (0.5 - cy) * 2 * half_h
    target = [t[i] + r[i] * dx + u[i] * dy for i in range(3)]
    fill = max(m["x1"] - m["x0"], m["y1"] - m["y0"], 0.01)
    zoom = TARGET_FILL / fill
    if m["clipped"]:
        zoom = min(zoom, 0.7)  # 화면 밖으로 잘렸으면 실제 크기를 알 수 없으니 확실히 물러남
    zoom = max(0.35, min(zoom, 4.0))
    dist = max(MIN_DIST, min(MAX_DIST, d0 / zoom))
    return {"target": [round(v, 1) for v in target], "distance": round(dist, 1),
            "fill": round(fill, 3), "clipped": m["clipped"]}


def needs_reshoot(entry, plan_entry):
    """다음 회차에 카메라를 옮겨 다시 찍을 이펙트인지. 보이지 않거나 화면 전체형은 다시 찍어도 같으므로 제외."""
    if not entry.get("visible") or "fullscreen" in entry.get("flags", []) or not plan_entry:
        return False
    lo, hi = RESHOOT_FILL
    if plan_entry.get("distance") in (MIN_DIST, MAX_DIST):
        return False  # 더 다가가거나 물러날 수 없음
    return plan_entry.get("clipped") or not (lo <= plan_entry.get("fill", 0.55) <= hi)


DEFAULT_CAMERA = {"target": [0.0, 0.0, 60.0], "distance": 923.1, "fov": 60.0, "width": 640, "height": 360,
                  "base_location": [-850.0, 0.0, 420.0], "base_target": [0.0, 0.0, 60.0]}


def encode(ffmpeg, folder, files, out_path):
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS),
           "-c:v", "png", "-i", "-", "-c:v", "libvpx-vp9", "-crf", str(CRF), "-b:v", "0",
           "-pix_fmt", "yuv420p", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", "-an", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            creationflags=NO_WINDOW)
    err = []
    t = threading.Thread(target=lambda: err.append(proc.stderr.read()))
    t.start()
    feed(proc, folder, files)
    t.join()
    if proc.wait() != 0:
        raise RuntimeError((err[0] if err else b"").decode("utf-8", "replace").strip()[-300:])


def poster(ffmpeg, png_path, out_path):
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", png_path, "-q:v", "4", out_path],
                   check=True, creationflags=NO_WINDOW)


def _load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def process_effect(ffmpeg, pack_id, name, folder, out_dir):
    """이펙트 하나: 측정 → 표시(flags) → 영상·대표 이미지. 반환: (결과, 카메라 계획 또는 None)."""
    files = frame_files(folder)
    counts = bright_counts(ffmpeg, folder, files)
    a = analyze(counts)
    m = measure(bright_counts.heat) if a else None
    flags, peak = quality_flags(counts, a, m)
    for ext in (".webm", ".jpg"):  # 이전 회차 결과 제거
        old = os.path.join(out_dir, name + ext)
        if os.path.exists(old):
            os.remove(old)
    if a is None:
        log("{0}: 빈 화면 (보이는 입자 없음 — 광원·카메라 효과일 수 있음)".format(name))
        return {"visible": False, "loop": None, "duration": None, "flags": flags, "peak": peak}, None
    video = os.path.join(out_dir, name + ".webm")
    jpg = os.path.join(out_dir, name + ".jpg")
    encode(ffmpeg, folder, files[a["start"]:a["end"]], video)
    poster(ffmpeg, os.path.join(folder, files[min(a["poster"], len(files) - 1)]), jpg)
    entry = {
        "visible": True, "loop": a["loop"], "duration": a["duration"], "pattern": a["pattern"],
        "video": "media/{0}/{1}.webm".format(pack_id, name),
        "poster": "media/{0}/{1}.jpg".format(pack_id, name),
        "flags": flags, "peak": peak,
    }
    plan = None
    if m:
        cam = dict(DEFAULT_CAMERA, **_load(os.path.join(folder, "camera.json")))
        plan = plan_camera(m, cam)
    label = {"loop": "Loop", "burst": "{0}s", "repeat": "{0}s (반복 단발)"}[a["pattern"]].format(a["duration"])
    note = ", 화면 점유 {0:.0%}{1}".format(plan["fill"], " (잘림)" if plan["clipped"] else "") if plan else ""
    marks = " [{0}]".format(", ".join(FLAG_LABELS[f] for f in flags)) if flags else ""
    log("{0}: {1}, 영상 {2:.1f}초, {3}KB{4}{5}".format(
        name, label, (a["end"] - a["start"]) / FPS, os.path.getsize(video) // 1024, note, marks))
    return entry, plan


def process_pack(base, pack_id, names=None, ffmpeg=None, round_no=1):
    """팩 하나의 프레임을 변환. names 를 주면 그 이펙트만 다시 처리하고 나머지 결과는 그대로 둠.
    결과는 capture_result.json·camera_plan.json 에 누적 저장. 반환: {이름: 결과}
    round_no: 몇 번째 촬영인지 (일괄 모드의 카메라 자동 조절 회차)"""
    ffmpeg = ffmpeg or find_ffmpeg()
    pack_dir = os.path.join(base, "frames", pack_id)
    out_dir = os.path.join(base, "media", pack_id)
    os.makedirs(out_dir, exist_ok=True)
    result_path = os.path.join(base, "capture_result.json")
    plan_path = os.path.join(base, "camera_plan.json")
    result, plans = _load(result_path), _load(plan_path)
    pack_result = result.setdefault(pack_id, {})
    done = {}
    for name in sorted(os.listdir(pack_dir)):
        if names is not None and name not in names:
            continue
        folder = os.path.join(pack_dir, name)
        if not os.path.isdir(folder) or not frame_files(folder):
            continue
        entry, plan = process_effect(ffmpeg, pack_id, name, folder, out_dir)
        entry["round"] = round_no
        pack_result[name] = entry
        if plan:
            plans.setdefault(pack_id, {})[name] = plan
        done[name] = entry
    _save(result_path, result)
    _save(plan_path, plans)
    return done


def build_zip(base, pack_id, export_pack=None):
    """upload_<팩 id>.zip: 이 팩의 결과·카메라 계획·영상(+ 이펙트 목록). 반환: zip 경로"""
    result, plans = _load(os.path.join(base, "capture_result.json")), _load(os.path.join(base, "camera_plan.json"))
    out_dir = os.path.join(base, "media", pack_id)
    pack_result = result.get(pack_id, {})
    linked = {os.path.basename(e[k]) for e in pack_result.values() for k in ("video", "poster") if e.get(k)}
    zip_path = os.path.join(base, "upload_{0}.zip".format(pack_id))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("capture_result.json", json.dumps({pack_id: pack_result}, ensure_ascii=False, indent=2))
        z.writestr("camera_plan.json", json.dumps({pack_id: plans.get(pack_id, {})}, ensure_ascii=False, indent=2))
        if export_pack:
            z.writestr("effects_export.json", json.dumps(export_pack, ensure_ascii=False, indent=2))
        for fname in sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []:
            if fname in linked:  # 결과에 연결된 파일만 (지난 회차 찌꺼기 제외)
                z.write(os.path.join(out_dir, fname), "media/{0}/{1}".format(pack_id, fname))
    return zip_path


def summarize(pack_result):
    """팩 결과 요약: 전체·영상·표시별 개수."""
    s = {"total": len(pack_result), "video": 0}
    for f in FLAG_LABELS:
        s[f] = 0
    for e in pack_result.values():
        if e.get("video"):
            s["video"] += 1
        for f in e.get("flags", []):
            s[f] = s.get(f, 0) + 1
    return s


def main():
    """따로 실행할 때: frames 아래 모든 팩 중 새로 녹화된 팩만 변환하고 zip 생성."""
    base = saved_dir()
    frames_root = os.path.join(base, "frames")
    if not os.path.isdir(frames_root):
        raise RuntimeError("프레임 폴더가 없습니다: " + frames_root)
    ffmpeg = find_ffmpeg()
    export = _load(os.path.join(base, "effects_export.json"))
    packs = {p["id"]: p for p in export.get("packs", [])}
    for pack_id in sorted(os.listdir(frames_root)):
        pack_dir = os.path.join(frames_root, pack_id)
        if not os.path.isdir(pack_dir):
            continue
        # 지난 변환 이후 새로 녹화되지 않은 팩은 건너뜀 (이미 만든 zip 이 최신 프레임보다 새것이면)
        zip_path = os.path.join(base, "upload_{0}.zip".format(pack_id))
        if os.path.exists(zip_path):
            newest = max((e.stat().st_mtime for d in os.scandir(pack_dir) if d.is_dir()
                          for e in os.scandir(d.path) if e.name.lower().endswith(".png")), default=0)
            if newest and newest < os.path.getmtime(zip_path):
                log("{0}: 새로 녹화된 프레임이 없어 건너뜀".format(pack_id))
                continue
        process_pack(base, pack_id, ffmpeg=ffmpeg)
        exp = packs.get(pack_id)
        zip_path = build_zip(base, pack_id, {"engine": export.get("engine"), "packs": [exp]} if exp else None)
        log("완료: {0} ({1}MB) — 이 파일을 Claude 에게 보내 주세요.".format(
            os.path.abspath(zip_path), round(os.path.getsize(zip_path) / 1048576, 1)))


# fx_capture.py 일괄 모드가 이 파일을 모듈로 불러올 때는 자동 실행하지 않음
if not getattr(builtins, "EFL_NO_AUTORUN", False):
    try:
        main()
    except Exception as e:
        try:
            import unreal
            unreal.log_error("[EFL] " + str(e))
        except ImportError:
            raise
