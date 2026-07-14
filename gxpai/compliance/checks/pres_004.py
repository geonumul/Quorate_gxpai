# -*- coding: utf-8 -*-
"""PRES-004 — **도면 내부 모순**: 화살표 방향과 절대압력(Pa)이 서로 어긋난다.

이 규칙은 법 위반을 찾는 게 아니다. **도면이 스스로 모순되는 곳**을 찾는다.

도면에는 같은 사실을 말하는 **독립된 근거가 둘** 있다.
    ① 차압 화살표 — 꼬리(고압) → 화살촉(저압). 공기가 흐르는 방향.
    ② 방마다 적힌 절대압력 — 예: `25Pa`
둘이 어긋나면 *"공기가 25Pa 방에서 30Pa 방으로 흐른다"* 는 말이 된다.
**공기는 낮은 데로만 흐른다.** 물리적으로 불가능하다.

셋 중 하나다:
    (a) 압력 수치를 잘못 적었다        (b) 화살표를 거꾸로 그렸다
    (c) 우리가 잘못 읽었다(추출 버그)
셋 다 **사람이 확인해야 한다.** 그래서 severity 는 `major` 지만 문구는 단정하지 않는다.

## 이 규칙이 생긴 경위 — 우리 버그를 잡아준 게 이 대조다

참고도면 2층에서 이 대조를 처음 돌렸을 때 화살표 28개 중 **9개**가 모순이었다.
전부 우리 버그였다(블록별 화살촉 방향 가정 오류 5건 + 방 귀속 오류 4건).
고치고 나니 31개 중 **1개**만 남았다 — 그 1개는 도면에 물어봐야 한다.

즉 이 규칙은 **엔진의 자기 점검**이자 **도면 검수**다. 둘 다 값어치가 있어 규칙으로 남긴다.
모순이 갑자기 늘면 **먼저 우리 추출을 의심하라.**

## 왜 '위반'이 아니라 '확인 필요' 인가
법이 "화살표와 숫자를 일치시켜라"라고 정한 조문은 **없다**. 이건 도면 품질 문제다.
다만 실사에서 이런 불일치는 *"차압 관리 기준이 문서로 일관되지 않다"* 로 이어질 수 있다.
   근거: 「의약품 등의 안전에 관한 규칙」 별표1 2.3 환경관리 나 (차압 설정, 유지, 기록 의무)
   → 조문 해석은 **보류. 발주처, 컨설턴트 확인 필요.**
"""
from __future__ import annotations

from ._model import PressureRel, RoomView, load_pressure_rels, load_rooms


def evaluate(rels: list[PressureRel], rooms: list[RoomView], cfg: dict) -> list[dict]:
    """화살표(고압→저압)와 절대압력이 어긋나는 관계를 반환."""
    view = {r.room_no: r for r in rooms if r.room_no}
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for rel in rels:
        hi_no, lo_no = rel.room_high_no, rel.room_low_no
        if rel.approx or not hi_no or not lo_no:
            continue                    # 방을 못 붙인 화살표는 판정하지 않는다
        if hi_no not in view or lo_no not in view:
            continue
        hi, lo = view[hi_no], view[lo_no]
        if hi.pressure_pa is None or lo.pressure_pa is None:
            continue                    # 근거가 하나뿐이면 대조할 게 없다
        if hi.pressure_pa >= lo.pressure_pa:
            continue                    # 일치(또는 동압) — 문제 없다

        key = (hi_no, lo_no)
        if key in seen:
            continue
        seen.add(key)

        out.append({
            "severity": "major",
            "rooms": [hi_no, lo_no],
            "message": (
                f"도면 내부 모순(확인 필요): 화살표는 "
                f"{hi_no}({hi.name}) → {lo_no}({lo.name}) 로 공기가 흐른다고 하는데, "
                f"적힌 압력은 {hi.pressure_pa:g}Pa < {lo.pressure_pa:g}Pa 다. "
                f"공기는 낮은 쪽으로만 흐른다 — 화살표 방향이나 압력 수치 중 하나가 틀렸다"
            ),
            "evidence": {
                "room_tail": hi_no, "pa_tail": hi.pressure_pa,
                "room_head": lo_no, "pa_head": lo.pressure_pa,
                "delta_pa": lo.pressure_pa - hi.pressure_pa,
                "arrow_head_deg": rel.head_deg,
                "arrow_layer": rel.layer,
                "근거": "화살표(꼬리=고압) vs 절대압력 라벨 — 도면 내 두 근거의 충돌",
                "판단": "보류. 발주처 확인 필요 (도면 오기인지 우리 추출 오류인지)",
            },
        })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []
    return evaluate(load_pressure_rels(cur, run_id), load_rooms(cur, run_id), cfg)
