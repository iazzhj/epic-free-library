"""팩 id(언리얼 폴더 이름에서 자동 생성)를 사이트의 에셋 id로 맞춰 주는 도우미.

예) ParagonGRIMexe → paragon-grimexe  →  사이트 id paragon-grim-exe
    ParagonIggy    → paragon-iggy     →  사이트 id paragon-iggy-scorch
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("paragon", "", 1))


def site_ids():
    with open(os.path.join(ROOT, "data", "assets.json"), encoding="utf-8") as f:
        return [a["id"] for a in json.load(f)["assets"]]


def resolve(pack_id, ids=None):
    """사이트에 같은 id가 있으면 그대로, 없으면 글자만 비교해 가장 잘 맞는 id. 못 찾으면 원래 id."""
    ids = ids or site_ids()
    if pack_id in ids:
        return pack_id
    key = _norm(pack_id)
    exact = [i for i in ids if i.startswith("paragon-") and _norm(i) == key]
    if exact:
        return exact[0]
    prefix = [i for i in ids if i.startswith("paragon-") and key and (_norm(i).startswith(key) or key.startswith(_norm(i)))]
    if len(prefix) == 1:
        return prefix[0]
    return pack_id
