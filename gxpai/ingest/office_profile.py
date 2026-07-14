# -*- coding: utf-8 -*-
"""사무소 온보딩 — DXF 를 훑어 **프로파일 초안**을 만든다.

## 왜 필요한가

설계사무소마다 레이어·블록 이름이 **완전히 다르다.** 지금까지 본 것만 해도:

    내용고형제 (C&H ENG)   벽 `하니컴패널`·`B-WAL` / 문 `DOOR`·`DOR` / 방번호 `(3301)`
    참고도면 (무균)         벽 `ARCH-기존`·`008_P__Wall 50T` / 문 `DOOR` / 방번호 `F2I01`
    MAS UNIT               벽 `D-WALC` / 문 `D-DOOR` / 텍스트 `D-TXTS`·`D-TXTM`

**코드를 고치지 않고 프로파일(YAML)만 갈아 끼워서** 새 사무소를 받을 수 있어야 한다.
이 모듈은 그 프로파일의 **초안**을 도면에서 자동으로 뽑는다.

## ★초안은 초안이다 — 사람이 확인해야 한다

자동 추정은 **틀린다.** 우리가 이미 여러 번 당했다:
  · 벽 레이어를 이름으로 짐작(`크린판넬`) → 96개 방이 하나의 40,710㎡ 덩어리가 됐다
  · "블록 안이 전부 레이어 0" 이라 단정 → 사실이 아니었다
  · "51/51 성공" → 면적을 안 봤더니 무균 전실이 0.8㎡ 였다

그래서 이 모듈은 **점수와 근거를 같이 내놓고**, 확신이 낮으면 `확인필요` 로 표시한다.
**숫자만 보고 넘어가지 말고, 방 개수와 면적이 상식적인지 반드시 눈으로 볼 것.**

## 무엇을 찾는가

    방번호   숫자·코드 꼴 텍스트 (패턴을 자동으로 알아낸다: (3301) · 3301 · F2I01)
    방이름   한글 텍스트, 방번호 근처
    벽       길고 축에 나란한 선분이 많은 레이어 (+ 이름 힌트)
    문       반지름 600~1200mm 호(문 스윙)가 있는 레이어 (+ 이름 힌트)
    등급     (A)·(B)·(C)·(D)·CNC·NC / GRADE / CLASS
    절대압력  `25Pa` 꼴
    차압화살표 블록 외곽선에 **뾰족한 끝**이 있는 INSERT (arrowgeom 으로 실측)
    차압계    이름 힌트 (차압계 · GAUGE · DPG)
    인터락    이름 힌트 (interlock · 인터락 · 연동)
    풍량      이름 힌트 (풍량 · CMH · AIRFLOW · SA)
    시트      같은 큰 블록이 여러 번 배치되면 **한 파일에 시트가 여러 장**이다

★**블록 안까지 재귀로 들어간다.** 안 그러면 아무것도 못 본다(우리가 세 번 당했다).
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

# 방번호 패턴 후보 — 어느 것이 맞는지 **세어서** 고른다
NUM_PATTERNS = [
    ("paren", re.compile(r"^\((\d{3,5}(?:-\d+)?)\)$"), r"^\((\d{3,5}(?:-\d+)?)\)$"),
    ("bare", re.compile(r"^(\d{3,5}(?:-\d+)?)$"), r"^(\d{3,5}(?:-\d+)?)$"),
    ("code", re.compile(r"^([A-Z]\d[A-Z]\d{2})$"), r"^([A-Z]\d[A-Z]\d{2})$"),   # F2I01
    ("code2", re.compile(r"^([A-Z]{1,3}-?\d{2,4})$"), r"^([A-Z]{1,3}-?\d{2,4})$"),
]
GRADE_RE = re.compile(r"^[（(]?\s*(A|B|C|D|CNC|NC)\s*[）)]?$")
PA_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*Pa$", re.I)
HANGUL = re.compile(r"[가-힣]")

# 레이어 이름 힌트 (있으면 점수를 더 준다. **이름만으로 정하지는 않는다**)
HINTS = {
    "wall": ("WALL", "WAL", "벽", "판넬", "패널", "칸막이", "PANEL", "PARTITION", "ARCH"),
    "door": ("DOOR", "DOR", "문", "출입", "DR"),
    "grade": ("GRADE", "등급", "청정", "CLASS", "ZONE"),
    "pressure_value": ("차압", "PRESS", "PA", "DP"),
    "arrow": ("AIR FLOW", "AIRFLOW", "기류", "FLOW", "차압"),
    "gauge": ("차압계", "GAUGE", "DPG", "MANOMETER", "압력계"),
    "interlock": ("INTERLOCK", "인터락", "인터록", "연동"),
    "airflow": ("풍량", "CMH", "AIRFLOW", "SA", "급기"),
    "equipment": ("장비", "EQUIP", "EQ", "MACHINE"),
}


def _hint(layer: str, key: str) -> bool:
    u = layer.upper().replace(" ", "")
    return any(h.upper().replace(" ", "") in u for h in HINTS[key])


def scan(doc, max_depth: int = 5) -> dict:
    """DXF 를 **블록 재귀로** 훑어 원자료를 모은다."""
    from ezdxf.math import Matrix44

    texts: list[tuple[float, float, str, str]] = []      # x, y, text, layer
    segs: dict[str, list[float]] = defaultdict(list)     # layer → 선분 길이들
    axis: Counter = Counter()                            # layer → 축에 나란한 선분 수
    arcs: dict[str, list[float]] = defaultdict(list)     # layer → 호 반지름들
    inserts: Counter = Counter()                         # block name → 개수
    ins_layer: dict[str, Counter] = defaultdict(Counter)  # block → layer 분포
    ins_pos: dict[str, list[tuple[float, float]]] = defaultdict(list)
    blk_size: Counter = Counter()                        # block name → 엔티티 수

    def walk(cont, mat, plr, depth):
        for e in cont:
            try:
                lay = e.dxf.layer
            except AttributeError:
                continue
            if lay == "0" and plr:
                lay = plr                                # CAD 규칙: 블록 안 '0' 은 상속
            t = e.dxftype()

            def tp(x, y):
                if mat is None:
                    return (x, y)
                p = mat.transform((x, y, 0.0))
                return (p.x, p.y)

            if t == "INSERT":
                nm = e.dxf.name
                inserts[nm] += 1
                ins_layer[nm][lay] += 1
                p = e.dxf.insert
                ins_pos[nm].append(tp(p.x, p.y))
                if depth >= max_depth:
                    continue
                blk = doc.blocks.get(nm)
                if blk is None:
                    continue
                blk_size[nm] = blk_size.get(nm) or sum(1 for _ in blk)
                m = e.matrix44()
                if mat is not None:
                    m = m @ mat
                walk(blk, m, lay, depth + 1)
                continue

            if t in ("TEXT", "MTEXT"):
                s = (e.plain_text() if t == "MTEXT" else e.dxf.text).strip()
                if s:
                    try:
                        p = e.dxf.insert
                        x, y = tp(p.x, p.y)
                    except Exception:      # noqa: BLE001
                        continue
                    texts.append((x, y, s, lay))
            elif t == "LINE":
                a = tp(e.dxf.start.x, e.dxf.start.y)
                b = tp(e.dxf.end.x, e.dxf.end.y)
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if L >= 1:
                    segs[lay].append(L)
                    if abs(b[0] - a[0]) < 1 or abs(b[1] - a[1]) < 1:
                        axis[lay] += 1
            elif t == "LWPOLYLINE":
                pts = [tp(p[0], p[1]) for p in e.get_points("xy")]
                if e.closed and len(pts) > 2:
                    pts.append(pts[0])
                for i in range(len(pts) - 1):
                    a, b = pts[i], pts[i + 1]
                    L = math.hypot(b[0] - a[0], b[1] - a[1])
                    if L >= 1:
                        segs[lay].append(L)
                        if abs(b[0] - a[0]) < 1 or abs(b[1] - a[1]) < 1:
                            axis[lay] += 1
            elif t == "ARC":
                arcs[lay].append(float(e.dxf.radius))

    walk(doc.modelspace(), None, None, 0)
    return {"texts": texts, "segs": segs, "axis": axis, "arcs": arcs,
            "inserts": inserts, "ins_layer": ins_layer, "ins_pos": ins_pos,
            "blk_size": blk_size}


def _pick_number_pattern(texts) -> tuple[str, str, Counter]:
    """방번호 표기 방식을 **세어서** 고른다. 짐작하지 않는다.

    ★**총 개수로 고르면 틀린다.** 참고도면에서 실제로 틀렸다:
        code (`F2I01`)  ROOMNUMBER 레이어에 **51개** — 정답
        bare (`3200`)   Roomheight(천장고) 35 + ARCH-기존 26 = **61개** — 이겼다(오답)

      천장고·치수 같은 **딴 숫자들이 합쳐져** 방번호를 이겨 버린 것이다.

      방번호는 **한 레이어에 몰려 있다.** 여기저기 흩어진 숫자는 방번호가 아니다.
      → **한 레이어 최대 개수**로 고른다.
    """
    # ★★그래도 부족했다. 내용고형제에서:
    #     paren (`(3301)`)  TEX 레이어에 111개 — **정답**
    #     bare  (`3200`)    TXT 레이어에 115개 — 이겼다(장비 태그·치수 숫자였다)
    #
    #   더 좋은 신호가 있다: **방번호 옆에는 방 이름(한글)이 있다.**
    #   장비 태그나 치수 숫자 옆에는 방 이름이 없다.
    #   → 근처(3m)에 한글 텍스트가 있는 숫자만 센다.
    names = [(x, y) for x, y, s, _l in texts if HANGUL.search(s) and len(s) <= 24]

    def has_name_near(x, y, r=3000.0) -> bool:
        return any(abs(nx - x) <= r and abs(ny - y) <= r for nx, ny in names)

    by_pat: dict[str, Counter] = defaultdict(Counter)      # 이름이 옆에 있는 것만
    raw: dict[str, Counter] = defaultdict(Counter)         # 전부 (참고용)
    for x, y, s, lay in texts:
        for name, rx, _src in NUM_PATTERNS:
            if not rx.match(s):
                continue
            raw[name][lay] += 1
            if has_name_near(x, y):
                by_pat[name][lay] += 1
    use = by_pat if by_pat else raw
    if not use:
        return ("", "", Counter(), [])
    # 점수 = 그 패턴이 **한 레이어에** 몰린 최대 개수 (방번호는 한 레이어에 모여 있다)
    best = max(use, key=lambda n: use[n].most_common(1)[0][1])
    src = next(s for n, _r, s in NUM_PATTERNS if n == best)

    # ★★후보를 **전부** 내놓는다. 자동 판별에는 한계가 있다 — 아는 척하면 안 된다.
    #
    #   내용고형제에서 방번호 표기가 **두 가지 섞여 있었다**:
    #       `(3301)` TMP_TXT 96개   ← 평면도 시트 (정답)
    #       `4104`   TXT     115개  ← **다른 시트**(장비배치도)
    #   개수로는 뒤엣것이 이긴다. **시트가 다르면 표기도 다르다.**
    #   기계가 못 고른다 → **사람이 고른다.** 그게 정직하다.
    alts = []
    for nm, cnt in sorted(use.items(), key=lambda kv: -kv[1].most_common(1)[0][1]):
        rx_src = next(s for n, _r, s in NUM_PATTERNS if n == nm)
        alts.append({"pattern": nm, "regex": rx_src,
                     "layers": cnt.most_common(3), "count": sum(cnt.values())})
    return (best, src, use[best], alts)


def _score_walls(sc) -> list[tuple[str, float, str]]:
    """벽 후보 레이어. **이름으로 짐작하지 않고 기하로 센다.**

    벽 = 길고(≥500mm) 축에 나란한 선분이 많다. 이름 힌트는 가산점일 뿐이다.
    (`크린판넬` 로 짐작했다가 96개 방이 하나로 뭉친 적이 있다)
    """
    out = []
    for lay, lens in sc["segs"].items():
        n = len(lens)
        if n < 20:
            continue
        long_n = sum(1 for L in lens if L >= 500)
        if long_n < 10:
            continue
        total_m = sum(lens) / 1000.0
        axis_r = sc["axis"].get(lay, 0) / n
        score = total_m * axis_r * (long_n / n)
        why = f"선분 {n:,} · 축나란 {axis_r*100:.0f}% · 총길이 {total_m:,.0f}m"
        if _hint(lay, "wall"):
            score *= 1.5
            why += " · 이름 힌트"
        out.append((lay, score, why))
    return sorted(out, key=lambda t: -t[1])[:8]


def _score_doors(sc) -> list[tuple[str, float, str]]:
    """문 후보. **문 스윙 호(반지름 600~1200mm)** 로 찾는다."""
    out = []
    for lay, radii in sc["arcs"].items():
        swing = [r for r in radii if 600 <= r <= 1300]
        if len(swing) < 3:
            continue
        score = float(len(swing))
        why = f"문 스윙 호 {len(swing)}개 (반지름 {min(swing):.0f}~{max(swing):.0f}mm)"
        if _hint(lay, "door"):
            score *= 2
            why += " · 이름 힌트"
        out.append((lay, score, why))
    return sorted(out, key=lambda t: -t[1])[:5]


def _score_arrows(doc, sc) -> list[tuple[str, int, str]]:
    """차압 화살표 후보. 블록 외곽선에 **뾰족한 끝**이 있는지 **실측**한다.

    ★회전각으로 방향을 추측하지 않는다 — 블록마다 화살촉 방향이 정반대일 수 있다.
      (실제로 그 가정 때문에 화살표 28개 중 9개를 거꾸로 읽었다)
    """
    from .arrowgeom import block_tip_local

    by_layer: Counter = Counter()
    why: dict[str, set] = defaultdict(set)
    for nm, cnt in sc["inserts"].items():
        blk = doc.blocks.get(nm)
        if blk is None:
            continue
        if block_tip_local(blk) is None:
            continue                        # 뾰족한 끝이 없다 = 화살표가 아니다
        for lay, n in sc["ins_layer"][nm].items():
            by_layer[lay] += n
            why[lay].add(nm)
    out = []
    for lay, n in by_layer.most_common(8):
        if n < 3:
            continue
        blocks = ", ".join(sorted(why[lay])[:3])
        out.append((lay, n, f"뾰족한 블록 {n}개 ({blocks})"))
    return out


def _score_sheets(sc) -> list[tuple[str, int, str]]:
    """한 파일에 **시트가 여러 장**인가. 같은 큰 블록이 여러 번 배치되면 그렇다.

    ★참고도면은 시트가 6장인데 우리는 **1장만** 보고 있었다.
      차압계·인터락·풍량을 통째로 놓칠 뻔했다.
    """
    out = []
    for nm, cnt in sc["inserts"].items():
        if cnt < 2 or sc["blk_size"].get(nm, 0) < 50:
            continue
        xs = sorted(p[0] for p in sc["ins_pos"][nm])
        if len(xs) < 2:
            continue
        gaps = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        gap = sorted(gaps)[len(gaps) // 2]
        if gap < 1000:                      # 겹쳐 놓은 것은 시트가 아니다
            continue
        out.append((nm, cnt, f"{cnt}회 배치 · 간격 ~{gap:,.0f}mm · 엔티티 {sc['blk_size'][nm]:,}"))
    return sorted(out, key=lambda t: -t[1])[:3]


def analyze(doc) -> dict:
    """도면 하나를 훑어 **프로파일 초안 + 근거**를 낸다."""
    sc = scan(doc)
    texts = sc["texts"]

    pat_name, pat_src, num_layers, num_alts = _pick_number_pattern(texts)
    name_layers = Counter(lay for _x, _y, s, lay in texts
                          if HANGUL.search(s) and len(s) <= 24)
    grade_layers = Counter(lay for _x, _y, s, lay in texts if GRADE_RE.match(s))
    pa_layers = Counter(lay for _x, _y, s, lay in texts if PA_RE.match(s))
    num_only = Counter(lay for _x, _y, s, lay in texts
                       if re.fullmatch(r"\d{2,6}", s))

    def by_hint(key):
        return [(l, n) for l, n in
                Counter(lay for _x, _y, _s, lay in texts).most_common()
                if _hint(l, key)][:3]

    return {
        "방번호": {"pattern": pat_name, "regex": pat_src,
                 "layers": num_layers.most_common(3), "count": sum(num_layers.values()),
                 # ★후보를 전부 준다. 시트가 다르면 표기도 다르다 — 사람이 골라야 한다.
                 "후보": num_alts},
        "방이름": {"layers": name_layers.most_common(3), "count": sum(name_layers.values())},
        "청정등급": {"layers": grade_layers.most_common(3), "count": sum(grade_layers.values())},
        "절대압력": {"layers": pa_layers.most_common(3), "count": sum(pa_layers.values())},
        "벽": _score_walls(sc),
        "문": _score_doors(sc),
        "차압화살표": _score_arrows(doc, sc),
        "시트": _score_sheets(sc),
        "차압계_이름힌트": [l for l in sc["segs"] | sc["arcs"] if _hint(l, "gauge")][:3],
        "인터락_이름힌트": [l for l in sc["segs"] | sc["arcs"] if _hint(l, "interlock")][:3],
        "풍량_이름힌트": [(l, n) for l, n in num_only.most_common(5) if _hint(l, "airflow")][:3],
        "숫자만_있는_레이어": num_only.most_common(5),
        "_요약": {"레이어": len({l for _x, _y, _s, l in texts}) ,
                "텍스트": len(texts), "블록종류": len(sc["inserts"])},
    }
