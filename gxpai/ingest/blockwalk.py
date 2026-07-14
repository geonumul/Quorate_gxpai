# -*- coding: utf-8 -*-
"""블록 재귀 공용 도구 — **같은 함정을 여섯 번째로 밟지 않기 위해.**

## 우리가 이 함정을 밟은 횟수

    ① 방 라벨이 "없다"  → 블록 안에 있었다        (dxftext.iter_label_texts 로 고침)
    ② 벽이 "안 그려져 있다" → 블록 안에 있었다     (boundaries._iter_wall_segments 로 고침)
    ③ 문이 "없다"      → 블록 안에 있었다         (door_barriers.iter_door_arcs 로 고침)

그런데 **차압 화살표 · 차압계 · 인터락 · 급기 풍량 · 설계개요**는 아직도
`doc.modelspace()` 만 훑고 있었다(전수 감사에서 나왔다).

같은 도면에서 방 라벨이 3단 블록 중첩 안에 있는데(참고도면), 화살표만 모델스페이스에
있으리란 보장이 없다. 시트 블록 안에 들어 있으면 **화살표 0개** → pressure_relation 이 비고
→ **PRES 규칙 전부가 조용히 "위반 없음"처럼 보인다.**

## 이 모듈이 하는 일

블록 안까지 재귀로 들어가며 엔티티를 **세계좌표와 함께** 내놓는다.
좌표 변환은 `matrix44()` 로 한다 — 직접 계산하면 **거울반사(xscale<0)** 를 놓친다
(차압 화살표에서 실제로 당했다).

    · 블록 안 엔티티의 레이어가 `'0'` 이면 **INSERT 의 레이어를 상속**한다 (CAD 규칙)
    · 꺼진·동결 레이어는 건너뛴다 (S-10: 구버전 잔재 '유령' 차단)
    · 버린 엔티티 수를 **센다** — 조용히 버리지 않는다
"""
from __future__ import annotations

import re


def layer_visible(doc, layer_name: str) -> bool:
    """레이어가 켜져 있고 동결되지 않았는지 (S-10)."""
    try:
        lay = doc.layers.get(layer_name)
    except Exception:                      # noqa: BLE001
        return True                        # 레이어 정의가 없으면 보수적으로 통과
    return not (lay.is_off() or lay.is_frozen())


def block_skipper(spec):
    """블록 이름 **제외 규칙** → 판정 함수. 프로파일 문법 불일치를 여기서 흡수한다.

    ★같은 개념인데 **문법이 두 가지**였다. 프로파일 작성자가 반드시 틀린다:

        label_exclude_blocks: "기둥"          ← **정규식 문자열** (dxftext 가 컴파일)
        boundaries.skip_blocks: ["B2026…"]   ← **부분문자열 리스트** (blockwalk 가 `in` 비교)

    `skip_blocks: ["기둥.*"]` 라고 쓰면 정규식으로 안 돌고 **조용히 아무것도 안 걸린다.**
    반대로 `label_exclude_blocks` 에 `*U12` 같은 이름을 넣으면 **정규식 컴파일이 터진다.**

    → 이제 **양쪽 다 받는다.** 문자열이든 리스트든, 정규식이든 부분문자열이든.

    ⚠AutoCAD **익명 블록**은 이름이 `*U12` · `*D5` 꼴이다. 그대로 컴파일하면
      `re.error: nothing to repeat` 로 터진다. → 컴파일 실패하면 **리터럴로 강등**한다.
    """
    if not spec:
        return lambda _name: False
    pats = [spec] if isinstance(spec, str) else [str(s) for s in spec]
    compiled: list = []
    for p in pats:
        try:
            compiled.append(re.compile(p))
        except re.error:
            compiled.append(None)          # `*U12` 같은 이름 — 리터럴로만 본다
    def skip(name: str) -> bool:
        if not name:
            return False
        for p, rx in zip(pats, compiled):
            if p in name:                  # 리터럴 부분문자열 (구 skip_blocks 문법)
                return True
            if rx is not None and rx.search(name):   # 정규식 (구 exclude_blocks 문법)
                return True
        return False
    return skip


def walk(doc, max_depth: int = 5, skip_blocks=None, yield_inserts: bool = False):
    """블록 안까지 재귀. `(entity, matrix44_or_None, 실효_레이어)` 를 내놓는다.

    matrix44 가 None 이면 모델스페이스 직속(변환 불필요)이다.

    yield_inserts: INSERT 자체도 내놓는다. **차압 화살표·차압계처럼 INSERT 가 곧 데이터**인
        경우에 쓴다. 이때도 **재귀는 계속**하므로, 블록 안에 중첩된 INSERT 도 잡힌다.

    ★★재귀를 켜면 **블록 안의 구성 요소까지 딸려온다.**
      차압흐름도에서 화살표 INSERT 39개를 재귀하면 그 블록 안의 선분 507개가 나온다.
      → **반드시 우리가 쓰는 엔티티 타입만 골라 써야 한다.** 안 그러면 화살표가 507개가 된다.
      (블록 재귀를 켜면서 기둥 블록의 철골 규격이 방 이름으로 딸려온 적이 있다)
    """
    skip = block_skipper(skip_blocks)

    def rec(container, mat, parent_layer, depth):
        for e in container:
            try:
                lay = e.dxf.layer
            except AttributeError:
                continue
            if lay == "0" and parent_layer:
                lay = parent_layer         # CAD 규칙: 블록 안 '0' 은 INSERT 레이어 상속

            if e.dxftype() == "INSERT":
                if yield_inserts and layer_visible(doc, e.dxf.layer):
                    yield (e, mat, lay)    # INSERT 자체가 데이터인 경우
                if depth >= max_depth:
                    continue
                if skip(e.dxf.name):
                    continue
                if not layer_visible(doc, e.dxf.layer):
                    continue               # INSERT 가 꺼져 있으면 그 안도 안 보인다
                blk = doc.blocks.get(e.dxf.name)
                if blk is None:
                    continue               # XREF 는 빈 블록을 돌려준다
                m = e.matrix44()
                if mat is not None:
                    m = m @ mat
                yield from rec(blk, m, lay, depth + 1)
                continue

            if not layer_visible(doc, lay):
                continue
            yield (e, mat, lay)

    yield from rec(doc.modelspace(), None, None, 0)


def world_point(p, mat):
    """블록 로컬 점 → 세계좌표. matrix44 가 회전·축척·**거울반사**를 다 처리한다."""
    if mat is None:
        return (p.x, p.y)
    q = mat.transform((p.x, p.y, 0.0))
    return (q.x, q.y)


def world_angle(deg: float, mat) -> float:
    """블록 로컬 각도 → 세계 각도(도)."""
    import math

    if mat is None:
        return deg % 360.0
    th = math.radians(deg)
    o = mat.transform((0.0, 0.0, 0.0))
    p = mat.transform((math.cos(th), math.sin(th), 0.0))
    return math.degrees(math.atan2(p.y - o.y, p.x - o.x)) % 360.0
