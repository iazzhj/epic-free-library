"""
Epic 무료 에셋 라이브러리 — 이펙트 미리보기 녹화 (2단계: 영상 변환·측정)

하는 일
  fx_capture.py 가 렌더링한 PNG 프레임을 읽어
  1. 프레임마다 밝은 픽셀 수를 세어 이펙트가 언제 끝나는지 측정합니다.
     - 녹화 끝까지 보이면 Loop: Yes, 중간에 사라지면 Loop: No + 길이(초)
  2. 웹용 webm 영상과 대표 이미지(jpg)를 만듭니다.
  3. 결과를 묶어 upload_<팩 id>.zip 으로 저장합니다. 이 zip 을 Claude 에게 보내면 사이트에 반영됩니다.

필요한 것
  ffmpeg (Windows: 명령 프롬프트에서  winget install Gyan.FFmpeg  실행 후 에디터 재시작)

실행
  언리얼 에디터: 도구 → Python 스크립트 실행 → 이 파일 선택
  또는 일반 파이썬: python encode_videos.py "<프로젝트>/Saved/EpicFreeLibrary"
"""

import json
import os
import shutil
import subprocess
import sys
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
            "duration": round(seg_len / fps, 1),
            "start": start, "end": end, "poster": first[0] + max(2, int(seg_len * 0.15))}
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
    import threading
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=NO_WINDOW)
    t = threading.Thread(target=feed, args=(proc, folder, files))
    t.start()
    size = ANALYZE_W * ANALYZE_H
    counts = []
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        counts.append(buf.translate(_BRIGHT).count(1))
    t.join()
    proc.wait()
    return counts


def encode(ffmpeg, folder, files, out_path):
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS),
           "-c:v", "png", "-i", "-", "-c:v", "libvpx-vp9", "-crf", str(CRF), "-b:v", "0",
           "-pix_fmt", "yuv420p", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", "-an", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            creationflags=NO_WINDOW)
    feed(proc, folder, files)
    err = proc.stderr.read().decode("utf-8", "replace")
    if proc.wait() != 0:
        raise RuntimeError(err.strip()[-300:])


def poster(ffmpeg, png_path, out_path):
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", png_path, "-q:v", "4", out_path],
                   check=True, creationflags=NO_WINDOW)


def main():
    base = saved_dir()
    frames_root = os.path.join(base, "frames")
    media_root = os.path.join(base, "media")
    if not os.path.isdir(frames_root):
        raise RuntimeError("프레임 폴더가 없습니다: " + frames_root)
    ffmpeg = find_ffmpeg()
    result_path = os.path.join(base, "capture_result.json")
    result = {}
    if os.path.exists(result_path):
        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)

    for pack_id in sorted(os.listdir(frames_root)):
        pack_dir = os.path.join(frames_root, pack_id)
        if not os.path.isdir(pack_dir):
            continue
        out_dir = os.path.join(media_root, pack_id)
        os.makedirs(out_dir, exist_ok=True)
        pack_result = result.setdefault(pack_id, {})
        for name in sorted(os.listdir(pack_dir)):
            folder = os.path.join(pack_dir, name)
            files = frame_files(folder) if os.path.isdir(folder) else []
            if not files:
                continue
            counts = bright_counts(ffmpeg, folder, files)
            a = analyze(counts)
            if a is None:
                pack_result[name] = {"visible": False, "loop": None, "duration": None}
                log("{0}: 화면에 보이는 입자 없음 (광원·카메라 효과일 수 있음)".format(name))
                continue
            video = os.path.join(out_dir, name + ".webm")
            jpg = os.path.join(out_dir, name + ".jpg")
            encode(ffmpeg, folder, files[a["start"]:a["end"]], video)
            poster(ffmpeg, os.path.join(folder, files[min(a["poster"], len(files) - 1)]), jpg)
            pack_result[name] = {
                "visible": True, "loop": a["loop"], "duration": a["duration"], "pattern": a["pattern"],
                "video": "media/{0}/{1}.webm".format(pack_id, name),
                "poster": "media/{0}/{1}.jpg".format(pack_id, name),
            }
            label = {"loop": "Loop", "burst": "{0}s", "repeat": "{0}s (반복 단발)"}[a["pattern"]].format(a["duration"])
            log("{0}: {1}, 영상 {2:.1f}초, {3}KB".format(
                name, label, (a["end"] - a["start"]) / FPS, os.path.getsize(video) // 1024))

        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        zip_path = os.path.join(base, "upload_{0}.zip".format(pack_id))
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
            z.write(result_path, "capture_result.json")
            for fname in sorted(os.listdir(out_dir)):
                z.write(os.path.join(out_dir, fname), "media/{0}/{1}".format(pack_id, fname))
        log("완료: {0} ({1}MB) — 이 파일을 Claude 에게 보내 주세요.".format(
            os.path.abspath(zip_path), round(os.path.getsize(zip_path) / 1048576, 1)))


try:
    main()
except Exception as e:
    try:
        import unreal
        unreal.log_error("[EFL] " + str(e))
    except ImportError:
        raise
