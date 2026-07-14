# -*- coding: utf-8 -*-
"""문(DOOR)을 캔다. 두 문제를 동시에 풀 수 있는지 본다.

  ① 기준 시설 flood-fill 이 45/96 에서 막혀 있다 — 벽에 **문 구멍**이 뚫려 있어
     방이 서로 새어나간다. 문 위치를 알면 그 구멍을 막을 수 있다.
  ② ADJ-001 은 지금 '벽을 맞댄 방'을 인접이라 본다. 그런데 조문(동선 D→C→B)은
     **문으로 이어진 방**을 말한다. 벽만 맞댄 두 방은 사람이 오갈 수 없다.
"""
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir

for fac, pat in (("f_1ae3a266", "평면"), ("f_c783b865", "평면")):
    f = next(p for p in (raw_dir() / fac).iterdir() if pat in p.name)
    doc = ezdxf.readfile(str(f))
    print(f"\n{fac}  {f.name}")

    # 문처럼 보이는 레이어
    lays = Counter()
    for e in doc.modelspace():
        lays[e.dxf.layer] += 1
    doorish = {k: v for k, v in lays.items()
               if any(w in k.upper() for w in ("DOOR", "문", "출입", "DR"))}
    print(f"   문 관련 레이어(모델스페이스): {doorish or '없음'}")

    # 블록 이름
    blks = Counter()
    def walk(c, d=0):
        for e in c:
            if e.dxftype() == "INSERT":
                blks[e.dxf.name] += 1
                b = doc.blocks.get(e.dxf.name)
                if b is not None and d < 3:
                    walk(b, d + 1)
    walk(doc.modelspace())
    doorblk = {k: v for k, v in blks.items()
               if any(w in k.upper() for w in ("DOOR", "문", "출입", "DR", "SD", "HD"))}
    print(f"   문처럼 보이는 블록: {dict(sorted(doorblk.items(), key=lambda x: -x[1])[:12]) or '없음'}")
    print(f"   전체 블록 종류 {len(blks)}개 / INSERT {sum(blks.values())}개")
