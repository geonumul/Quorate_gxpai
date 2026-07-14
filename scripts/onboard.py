# -*- coding: utf-8 -*-
"""사무소 온보딩 — DXF 를 훑어 **프로파일 초안**을 낸다.

    python scripts/onboard.py "경로/도면.dxf"

초안은 초안이다. 반드시 사람이 확인해야 한다.
  자동 추정은 틀린다 — 우리는 벽 레이어를 이름으로 짐작했다가 96개 방이
  하나의 40,710㎡ 덩어리가 된 적이 있다.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.ingest.office_profile import analyze

if len(sys.argv) < 2:
    sys.exit("사용법: python scripts/onboard.py <도면.dxf>")
p = Path(sys.argv[1])
doc = ezdxf.readfile(str(p))
a = analyze(doc)

print(f"{p.name}")
print(f"   {a['_요약']}\n")

def show(title, items, fmt):
    print(f"{title}")
    if not items:
        print("     (못 찾음 — 이 도면에 없거나, 우리가 못 보는 것이다)")
    for it in items:
        print("     " + fmt(it))
    print()

n = a["방번호"]
print(f"방번호 — **후보를 전부 보여준다. 골라야 하는 건 사람이다.**")
alts = n.get("후보") or []
for i, alt in enumerate(alts):
    mark = "추천" if alt["pattern"] == n["pattern"] else "     "
    lays = ", ".join(f"{l}({c})" for l, c in alt["layers"])
    print(f"  {mark} [{i}] {alt['pattern']:<6} {alt['regex']}")
    print(f"          레이어: {lays}   총 {alt['count']}개")
if len(alts) > 1:
    print("   [주의] 표기가 **여러 가지 섞여 있다.** 시트가 다르면 표기도 다르다"
          "(내용고형제: 평면도는 `(3301)`, 장비배치도는 `4104`).")
    print("      **어느 시트를 쓸지 정하고 그에 맞는 것을 고를 것.**")
print()
show("방이름", a["방이름"]["layers"], lambda t: f"레이어 {t[0]!r}: {t[1]}")
show("청정등급", a["청정등급"]["layers"], lambda t: f"레이어 {t[0]!r}: {t[1]}")
show("절대압력(Pa)", a["절대압력"]["layers"], lambda t: f"레이어 {t[0]!r}: {t[1]}")
show("벽 (기하로 채점 — 이름으로 짐작하지 않는다)", a["벽"],
     lambda t: f"{t[1]:>9,.0f}점  {t[0]!r:30} {t[2]}")
show("문 (문 스윙 호로 찾는다)", a["문"], lambda t: f"{t[1]:>6.0f}점  {t[0]!r:24} {t[2]}")
show("차압 화살표 (블록 외곽선의 뾰족한 끝을 실측)", a["차압화살표"],
     lambda t: f"{t[1]:>4}개  {t[0]!r:24} {t[2]}")
show("시트 (한 파일에 여러 장인가)", a["시트"], lambda t: f"{t[0]!r:26} {t[2]}")
print(f"이름 힌트: 차압계={a['차압계_이름힌트']}, 인터락={a['인터락_이름힌트']}, 풍량={a['풍량_이름힌트']}")
print(f"숫자만 있는 레이어(풍량 후보): {a['숫자만_있는_레이어']}")


# ── YAML 초안 출력 (--yaml) ──────────────────────────────────────────────
if "--yaml" in sys.argv:
    import io
    top = lambda xs, k=0: [t[0] for t in xs[:2]] if xs else []
    n = a["방번호"]
    y = io.StringIO()
    w = y.write
    w("# 자동 초안 — **반드시 사람이 확인할 것.**\n")
    w(f"#   출처: {p.name}\n")
    w("#   개수만 세면 속는다. ingest 후 **방 개수와 면적이 상식적인지** 눈으로 볼 것.\n")
    w("#   빈 칸([] 또는 '')은 **우리가 못 찾은 것**이다 — 도면에 없거나, 다른 시트에 있다.\n\n")
    w(f"profile_id: {p.stem.replace(' ', '_')}\nprofile_version: '1'\n")
    w(f"description: '{p.name} 자동 초안 (검수 전)'\n\n")
    w("floors: {'3': 3F, '4': 4F}   # ← 실제 층에 맞게 고칠 것\n")
    w("label_entity_types: [TEXT, MTEXT]\n\n")
    w("floorplan:\n")
    w(f"  room_layers: {top(n['layers'])}          # 방번호 {n['count']}개 발견\n")
    w(f"  room_no_regex: '{n['regex']}'   # 패턴={n['pattern'] or '못 찾음'}\n")
    w("  bare_no_regex: ''\n  skip_names: []\n  max_match_dist_mm: 3000\n")
    w("  name_above_max_mm: 1500\n  name_above_penalty: 2.0\n")
    w("  multiline_merge: {max_dx_mm: 900, max_dy_mm: 600}\n\n")
    w("boundaries:\n")
    w("  # 기하로 채점한 상위 후보다. **이름으로 짐작한 게 아니다.**\n")
    for lay, sco, why in a["벽"][:5]:
        w(f"  #   {sco:>9,.0f}점  {lay!r}  ({why})\n")
    w(f"  wall_layers: {top(a['벽'])}   # ← 넣고 **방 개수, 면적을 확인**할 것\n")
    w(f"  door_layers: {top(a['문'])}\n")
    w("  skip_blocks: []\n  seal_doors: true\n  cell_mm: 60\n")
    w("  close_gap_mm: 200\n  adj_gap_mm: 300\n  min_area_m2: 0.5\n  max_area_m2: 400\n\n")
    g = a["청정등급"]
    w(f"grades:\n  layers: {top(g['layers'])}   # 등급 표기 {g['count']}건")
    w("   ← 0건이면 등급 규칙 5개가 판정 불가다. 발주처에 요청할 것\n\n" if not g["count"] else "\n\n")
    pv = a["절대압력"]
    w(f"pressure_value:\n  layers: {top(pv['layers'])}   # `25Pa` 꼴 {pv['count']}건\n")
    w("  max_match_dist_mm: 5000\n  above_penalty: 2.0\n\n")
    w("pressure:\n")
    w(f"  rm_layer: '{(top(n['layers']) or [''])[0]}'\n")
    w("  title_layers: []\n  floor_regex: '(\d)층'\n  name_match_dist_mm: 3000\n")
    w("  multiline_merge: {max_dx_mm: 900, max_dy_mm: 600}\n")
    w(f"  arrow_layers: {[t[0] for t in a['차압화살표'][:3]]}   # 뾰족한 블록으로 실측\n")
    w("  arrow_block_prefix: ''\n  ta_layer: ''\n  ta_unit: UNKNOWN\n\n")
    w(f"gauge:\n  layers: {a['차압계_이름힌트']}\n\n")
    w(f"interlock:\n  layers: {a['인터락_이름힌트']}\n\n")
    w("airflow:\n  layers: []\n  unit: UNKNOWN\n  unit_source: ''\n\n")
    w("pressure_regime:\n  overrides: {}\n\n")
    w("grade_rank: {A: 5, B: 4, C: 3, D: 2, CNC: 1, NC: 0}\n")
    w("equipment: {layers: []}\nhvac: {layers: []}\noverview: {layers: []}\n")
    if a["시트"]:
        w("\n# 이 파일에는 **시트가 여러 장** 있다. 전부 열어볼 것!\n")
        for nm, cnt, why in a["시트"]:
            w(f"#   {nm!r}: {why}\n")
        w("#   → scripts/cut_ref_sheet_aligned.py 로 기준 시트 좌표계로 옮겨 잘라 온다.\n")
    print("\n" + "="*70 + "\n" + y.getvalue())


# ── --try : 벽 후보를 **실제로 돌려서** 고른다 ─────────────────────────────
#
# 자동 채점만 믿으면 안 된다. 내용고형제에서 기하 점수 1위가 `크린판넬` 이었는데,
#   그걸로 돌리면 **96개 방이 하나의 40,710㎡ 덩어리**가 된다(우리가 실제로 당했다).
#   정답은 2위 `하니컴패널` 이었다.
#
#   **유일하게 확실한 검증은 flood-fill 을 돌려 보는 것이다.**
#     - 방이 몇 개나 닫히나
#     - 면적이 상식적인가 (중앙값 5~60㎡ 쯤이 정상. 0.5㎡ 나 5,000㎡ 면 잘못됐다)
if "--try" in sys.argv:
    import copy
    from gxpai.geometry import boundaries as B

    n = a["방번호"]
    num_layers = [t[0] for t in n["layers"][:2]]
    door_layers = [t[0] for t in a["문"][:1]]
    import re as _re
    rx = _re.compile(n["regex"]) if n["regex"] else None
    rooms = []
    from gxpai.ingest.office_profile import scan
    for x, y, s, lay in scan(doc)["texts"]:
        if lay in num_layers and rx and rx.match(s):
            rooms.append({"room_no": rx.match(s).group(1), "plan_x": x, "plan_y": y})
    print(f"\n{'='*70}\n벽 후보를 **실제로 돌려서** 검증한다  (방 라벨 {len(rooms)}개)")
    if not rooms:
        sys.exit("   방 라벨을 못 찾아 검증할 수 없다.")

    # 벽은 **한 레이어가 아니다.** 내용고형제는 `하니컴패널`(클린룸 벽) + `B-WAL`(건축 벽)
    #   + `계단실` + `COL`(기둥) + `창호` 를 다 합쳐야 방이 닫힌다.
    #   단독 후보만 시험하면 "쓸 만한 게 없다"로 끝난다 → **누적 조합**을 시험한다.
    from gxpai.ingest.office_profile import HINTS, _hint

    top = [l for l, _s, _w in a["벽"][:6]]
    hinted = [l for l, _s, _w in a["벽"] if _hint(l, "wall")]

    cands = [([l], f"{l!r} 단독") for l in top[:4]]
    # 누적: 상위 1개 → 1+2 → 1+2+3 …
    for k in range(2, min(len(top), 6) + 1):
        cands.append((top[:k], f"기하 상위 {k}개"))
    # 이름 힌트가 붙은 것만 모아서 (`벽`, `판넬`, `WALL` …)
    if len(hinted) >= 2:
        cands.append((hinted, f"이름에 벽 힌트가 있는 것 전부 ({len(hinted)}개)"))
    # 힌트 + 구조 레이어 (기둥, 계단, 창호는 벽의 일부다)
    struct = [l for l, _s, _w in a["벽"]
              if any(k in l.upper() for k in ("COL", "기둥", "계단", "창", "WIN", "STAIR"))]
    if hinted and struct:
        cands.append((sorted(set(hinted + struct)), "벽 힌트 + 기둥, 계단, 창호"))
    # 최후의 수단: 레이어를 안 가리고 전부 태운다
    cands.append((["*"], "전부 태우기 (최후의 수단 — 가구, 치수선까지 벽이 된다)"))
    print(f"\n  {'벽 레이어':<38} {'방':>9} {'면적중앙값':>10}  판정")
    best = None
    for lays, label in cands:
        prof = {"boundaries": {"wall_layers": lays, "door_layers": door_layers,
                               "cell_mm": 60, "close_gap_mm": 200, "adj_gap_mm": 300,
                               "min_area_m2": 0.5, "max_area_m2": 400}}
        try:
            res = B.build(doc, rooms, prof)
        except Exception as exc:            # noqa: BLE001
            print(f"  {label:<38} {'오류':>9}  {exc}")
            continue
        got = len(res.rooms)
        areas = sorted(r.area_m2 for r in res.rooms)
        med = areas[len(areas) // 2] if areas else 0
        # 개수만 보면 속는다. **면적이 상식적인지** 함께 본다.
        ok = got >= len(rooms) * 0.6 and 3 <= med <= 120
        verdict = "쓸 만하다" if ok else ("방이 너무 적다" if got < len(rooms) * 0.6
                                        else f"면적이 이상하다({med:.1f}㎡)")
        print(f"  {label:<38} {got:>4}/{len(rooms):<4} {med:>8.1f}㎡  {verdict}")
        if ok and (best is None or got > best[0]):
            best = (got, lays, med)
    print()
    if best:
        print(f"  추천: wall_layers: {best[1]}  (방 {best[0]}개, 면적 중앙값 {best[2]:.1f}㎡)")
        print("     [주의] 그래도 **그림으로 한 번 볼 것.** 숫자가 맞아도 방이 잘게 썰려 있을 수 있다.")
    else:
        print("  쓸 만한 후보가 없다. 벽이 블록 안에 있거나, 레이어가 더 필요하다.")
        print("     → 실패한 방 주변 6m 안의 레이어를 세어 볼 것(scripts/diag_room_walls.py).")
