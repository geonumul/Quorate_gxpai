# -*- coding: utf-8 -*-
"""DXF 텍스트 읽기 공통 도구.

리스크 문서 반영:
- R-A1: AutoCAD 포맷 코드(%%C, %%D, MTEXT 인라인 코드)를 사람이 읽는 글자로 정규화.
- R-A2: TEXT 뿐 아니라 MTEXT 도 순회 (방 라벨이 MTEXT인 설계사 대비).
- S-10: 꺼진(off)·동결(frozen) 레이어의 텍스트는 제외 (구버전 잔재 '유령 방' 차단).
모든 추출기는 반드시 이 모듈의 iter_label_texts 를 통해 텍스트를 읽는다.
"""
from __future__ import annotations

from ezdxf.tools.text import plain_text


def normalize_dxf_text(entity) -> str:
    """엔티티의 표시 텍스트를 포맷 코드가 제거된 순수 문자열로 반환 (R-A1)."""
    if entity.dxftype() == "MTEXT":
        return entity.plain_text().strip()
    return plain_text(entity.dxf.text).strip()


def text_position(entity):
    """텍스트의 실제 삽입 위치 (R-F1: 정렬 텍스트는 insert 가 아니라 align_point).

    TEXT가 가운데/오른쪽/중앙 정렬이면 dxf.insert 는 쓰레기 값이고 dxf.align_point 가
    진짜 위치다. MTEXT의 insert 는 부착점이라 그대로 신뢰한다.
    """
    if entity.dxftype() == "MTEXT":
        return entity.dxf.insert
    halign = entity.dxf.get("halign", 0)
    valign = entity.dxf.get("valign", 0)
    if (halign or valign) and entity.dxf.hasattr("align_point"):
        return entity.dxf.align_point
    return entity.dxf.insert


def _layer_visible(doc, layer_name: str) -> bool:
    """레이어가 켜져 있고 동결되지 않았는지 (S-10)."""
    try:
        layer = doc.layers.get(layer_name)
    except Exception:
        return True  # 레이어 정의가 없으면 보수적으로 통과
    return not (layer.is_off() or layer.is_frozen())


def iter_label_texts_any_layer(doc, entity_types=("TEXT", "MTEXT")):
    """모든 레이어의 보이는 TEXT/MTEXT를 (x, y, text, layer) 로 순회.

    ★**블록 안까지 재귀한다.** 예전엔 `doc.modelspace()` 만 훑었다.

      설계개요(공사명·연면적·용도)는 대개 **표제란 블록 안**에 있다.
      그런데 이 함수를 쓰는 overview 추출기가 모델스페이스만 봐서,
      표제란이 블록이면 **설계개요 0건**이 나온다 — 예외 하나 없이.

      blockwalk 모듈이 스스로 적어 뒀다: 우리는 이 함정을 **다섯 번** 밟았다
      (방 라벨 · 벽 · 문 · 화살표 · 차압계). 여기가 여섯 번째였다.

    ⚠재귀하면 블록 안 구성 요소가 딸려온다 → **TEXT/MTEXT 만** 집는다.
    ⚠좌표는 matrix44 로 변환한다. 직접 계산하면 **거울반사**를 놓친다.
    """
    from .blockwalk import walk, world_point

    types = tuple(entity_types)
    for e, mat, lay in walk(doc):
        if e.dxftype() not in types:
            continue
        t = normalize_dxf_text(e)
        if not t:
            continue
        x, y = world_point(text_position(e), mat)
        yield (x, y, t, lay)


def _effective_layer(entity, parent_layer: str | None) -> str:
    """블록 안 엔티티의 **실효 레이어**.

    CAD 규칙: 블록 정의 안에서 레이어가 '0' 인 엔티티는 **INSERT 의 레이어를 상속**한다.
    자기 레이어가 따로 있으면 그것을 쓴다.
    """
    lay = entity.dxf.layer
    if lay == "0" and parent_layer:
        return parent_layer
    return lay


def iter_label_texts(doc, layers, entity_types=("TEXT", "MTEXT"), max_depth: int = 6,
                     exclude_blocks: str | None = None):
    """지정 레이어의 보이는 TEXT/MTEXT를 (x, y, text, height) 로 순회 (R-A1/A2/S-10).

    ★**블록(INSERT) 안까지 재귀로 들어간다. 좌표는 세계좌표로 변환한다.**

    왜 필요한가 — 실제로 당했다:
      새 참고도면은 방 라벨이 전부 **블록 안**에 있다
      (`2층평면도(260320)` → TEXT: Grade 49 · RoomName 56 · ROOMNUMBER 51).
      모델스페이스만 훑던 예전 코드는 **아무것도 못 봤다** — 추출기 전체가 0건을 냈다.
      CAD 도면은 블록 중첩이 기본이다(이 도면은 3단). 모델스페이스만 보는 건 반쪽짜리다.

    ★그런데 재귀를 켜자 **딸려오지 말아야 할 것**이 딸려왔다(exclude_blocks 로 막는다):
      기준 시설 평면도의 블록 `SC2(기둥)` · `SC3[기둥]` 안에는
      `SC2` `H-350X350X12X19` 같은 **철골 기둥 규격**이 들어 있고, 하필 그 텍스트가
      방 이름 레이어(`TMP_TXT`)에 얹혀 있다. 그래서
        · 방 4107 의 이름이 통째로 `SC2 H-350X350X12X19` 가 됐고
        · 방 3205 는 `SC2 H-350X350X12X19 갱의실(여)A` 로 **이름 앞에 규격이 붙었다**
      LBL-001(이름 불일치)이 3건 → 4건으로 늘어 기준값이 깨진 것으로 들통났다.
      **숫자 하나가 어긋난 것을 그냥 넘겼으면 방 이름이 조용히 오염된 채로 갔다.**

    레이어 필터는 **실효 레이어**로 한다(블록 안 '0' 은 INSERT 의 레이어를 상속).

    exclude_blocks: 블록 이름 정규식. 걸리면 그 블록 안으로 **들어가지 않는다**.
                    (기둥·치수·범례처럼 방 라벨이 아닌 것이 사는 블록)
    """
    import re

    from ezdxf.math import Matrix44

    if isinstance(layers, str):          # 프로파일이 "RM" 처럼 문자열이면 문자로 쪼개짐 방지
        layers = [layers]
    layers = set(layers)
    types = tuple(entity_types)
    # ★정규식만 받았다 → `*U12`(AutoCAD 익명 블록) 이 오면 컴파일이 터진다.
    #   이제 공용 판정기가 정규식·부분문자열을 둘 다 받고 터지지 않는다.
    from .blockwalk import block_skipper
    skip_block = block_skipper(exclude_blocks)

    def walk(container, mat: Matrix44 | None, parent_layer: str | None, depth: int):
        for e in container:
            t = e.dxftype()
            if t == "INSERT":
                if depth >= max_depth:
                    continue            # 순환 참조·과도한 중첩 방어
                if skip_block(e.dxf.name):
                    continue            # 기둥·치수 등 방 라벨이 아닌 블록
                blk = None
                try:
                    blk = doc.blocks.get(e.dxf.name)
                except Exception:
                    blk = None
                if blk is None:
                    continue
                # INSERT 가 얹힌 레이어가 꺼져 있으면 그 안의 것도 안 보인다
                if not _layer_visible(doc, e.dxf.layer):
                    continue
                m = e.matrix44()          # 스케일·회전·이동을 ezdxf 가 계산해 준다
                if mat is not None:
                    m = m @ mat
                yield from walk(blk, m, _effective_layer(e, parent_layer), depth + 1)
                continue

            if t not in types:
                continue
            lay = _effective_layer(e, parent_layer)
            if lay not in layers:
                continue
            if not _layer_visible(doc, lay):
                continue
            txt = normalize_dxf_text(e)
            if not txt:
                continue
            pos = text_position(e)        # R-F1: 정렬 보정된 실제 위치
            if mat is not None:
                pos = mat.transform(pos)
            height = getattr(e.dxf, "height", None) or getattr(e.dxf, "char_height", None)
            yield (pos.x, pos.y, txt, height)

    yield from walk(doc.modelspace(), None, None, 0)
