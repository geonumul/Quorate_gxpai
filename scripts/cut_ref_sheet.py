# -*- coding: utf-8 -*-
"""새 참고도면 DXF 에서 **시트 한 장만 잘라** 별도 DXF 로 만든다. (야간작업 B1)

왜 필요한가
  참고도면(2).dxf 에는 **6장이 나란히** 들어 있다
  (천정기구, return풍도, 차압흐름도, 차압계, 온습도계, 인터락).
  그대로 ingest 하면 방 라벨이 **6배로 중복**된다(평면도 블록이 6번 배치돼 있으므로).
  엔진의 데이터 모델은 '도면 1개 = 파일 1개'다. → 시트를 잘라 파일로 만든다.

방법
  시트 원점 = 평면도 블록(`2층평면도(260320)`)의 INSERT 위치.
  그 x 범위(원점 ~ 원점+SHEET_W) 안의 모델스페이스 엔티티만 새 문서로 옮긴다.
  블록 정의는 ezdxf Importer 가 딸려서 가져온다(중첩 블록 포함).

  python scripts/cut_ref_sheet.py 2   # 3번째 시트(차압 흐름도)
"""
from __future__ import annotations

import sys
from pathlib import Path

import ezdxf
from ezdxf.addons import Importer

sys.stdout.reconfigure(encoding="utf-8")

SRC = Path(r"D:\14. Dev Project\Quorate\참고도면_원본_CAD\dxf\참고도면(2).dxf")
PLAN_BLOCK = "2층평면도(260320)"
# 시트 간격보다 **작게** 잡아야 한다. 125,000 으로 뒀더니 옆 시트(차압계, x=371,500)가
#   딸려와 방번호가 102개(51×2)로 두 배가 됐다. 실제 시트 간격은 106,026mm.
SHEET_W = 100_000.0
NAMES = ["천정기구배치", "return풍도", "차압흐름도", "차압계배치", "온습도계배치", "인터락배치"]

idx = int(sys.argv[1]) if len(sys.argv) > 1 else 2
out_dir = Path("raw/_ref2f")
out_dir.mkdir(parents=True, exist_ok=True)

doc = ezdxf.readfile(str(SRC))
msp = doc.modelspace()

sheets = sorted((e for e in msp.query("INSERT") if e.dxf.name == PLAN_BLOCK),
                key=lambda e: e.dxf.insert.x)
print(f"시트 {len(sheets)}장 발견")
if not (0 <= idx < len(sheets)):
    sys.exit(f"시트 번호 범위 밖: {idx}")

x0 = sheets[idx].dxf.insert.x
x1 = x0 + SHEET_W
print(f"[{idx}] {NAMES[idx]}  x {x0:,.0f} ~ {x1:,.0f}")


def in_sheet(e) -> bool:
    """엔티티가 이 시트 안에 있는가. 대표점 하나라도 들어오면 포함."""
    t = e.dxftype()
    try:
        if t == "INSERT":
            p = e.dxf.insert
            return x0 <= p.x <= x1
        if t in ("TEXT", "ATTRIB"):
            p = e.dxf.insert
            return x0 <= p.x <= x1
        if t == "MTEXT":
            return x0 <= e.dxf.insert.x <= x1
        if t == "LINE":
            return x0 <= e.dxf.start.x <= x1 or x0 <= e.dxf.end.x <= x1
        if t == "LWPOLYLINE":
            return any(x0 <= p[0] <= x1 for p in e.get_points())
        if t in ("CIRCLE", "ARC"):
            return x0 <= e.dxf.center.x <= x1
        if t == "HATCH":
            return x0 <= e.dxf.elevation.x <= x1 if hasattr(e.dxf, "elevation") else False
    except Exception:
        return False
    return False


keep = [e for e in msp if in_sheet(e)]
print(f"시트 안 엔티티 {len(keep):,}개 (전체 {len(msp):,})")

new = ezdxf.new(dxfversion=doc.dxfversion, setup=True)
imp = Importer(doc, new)
imp.import_entities(keep, new.modelspace())
imp.finalize()

out = out_dir / f"{NAMES[idx]}.dxf"
new.saveas(str(out))
print(f"\n→ {out}  ({out.stat().st_size:,} bytes)")

# 검증: 잘라낸 파일에서 방번호가 몇 개나 읽히는지
sys.path.insert(0, ".")
from gxpai.ingest.dxftext import iter_label_texts  # noqa: E402

chk = ezdxf.readfile(str(out))
nums = [t for _x, _y, t, _h in iter_label_texts(chk, ["ROOMNUMBER"])]
grades = [t for _x, _y, t, _h in iter_label_texts(chk, ["Grade"])]
pas = [t for _x, _y, t, _h in iter_label_texts(chk, ["차압"])]
print(f"검증: 방번호 {len(nums)}, 등급 {len(grades)}, 차압 {len(pas)}")
