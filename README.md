# Epic 무료 에셋 라이브러리

에픽게임즈가 무료로 공개한 언리얼 엔진 리소스(Paragon 캐릭터·환경, 애니메이션, 샘플 프로젝트, Fab 기간 한정 무료 에셋)를 모아 Fab 원본 페이지로 연결하는 라이브러리입니다.

- 페이지: https://iazzhj.github.io/epic-free-library/
- 에셋 파일은 이 저장소에 포함하지 않습니다. 모든 항목은 Fab 원본 링크로 연결됩니다.

## 파일 구조

| 경로 | 역할 |
|---|---|
| `index.html`, `style.css`, `app.js` | 화면 |
| `data/assets.json` | 에셋 목록, 분류, 갱신 기록, 바로가기 |
| `data/effects/index.json` | 이펙트가 등록된 에셋 색인 (검색용 이름 목록 포함) |
| `data/effects/<에셋 id>.json` | 에셋별 이펙트 상세 |
| `media/` (예정) | 이펙트 미리보기 영상 |
| `tools/` (예정) | 언리얼 에디터용 추출·녹화 스크립트 |

## 데이터 형식

### data/assets.json 의 assets 항목

```json
{
  "id": "paragon-greystone",
  "name": "Paragon: Greystone",
  "cat": "char",
  "types": ["모델", "애니메이션", "VFX"],
  "fab": "122fd7bf-6f12-4304-a930-cccbbacdaebc",
  "docs": "https://... (선택)",
  "desc": "설명 (선택)",
  "until": "2026-11-03T15:00:00Z (기간 한정일 때)",
  "by": "제작자 (선택)",
  "official": false,
  "added": "2026-10-29"
}
```

`cat` 값: `char` 캐릭터, `env` 환경, `anim` 애니메이션, `sample` 샘플 프로젝트, `limited` 기간 한정 무료, `comm` 커뮤니티 파생.

### data/effects/index.json

```json
{ "updated": "2026-10-29", "assets": { "paragon-greystone": { "count": 49, "names": ["P_Greystone_..."] } } }
```

### data/effects/<에셋 id>.json

```json
{
  "asset": "paragon-greystone",
  "effects": [
    { "name": "P_...", "loop": true, "path": "Greystone/Abilities/...", "duration": 6.1,
      "desc": "한국어 설명", "video": "media/paragon-greystone/P_....webm" }
  ]
}
```

`video` 가 상대 경로이면 `assets.json` 의 `mediaBase` 를 앞에 붙입니다. 영상을 외부 저장소(예: Cloudflare R2)로 옮길 때는 `mediaBase` 만 바꾸면 됩니다.
