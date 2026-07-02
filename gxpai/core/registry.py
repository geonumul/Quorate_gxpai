# -*- coding: utf-8 -*-
"""시설 레지스트리 — 등록/조회.

로드맵: S1.1 · 다중 시설 격리 키
facility_id 는 시설명에서 결정적으로 파생(재실행해도 동일). 모든 데이터의 격리 키.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..ingest import unpack
from .config import raw_dir
from .db import connect


def make_facility_id(name: str) -> str:
    return "f_" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]


def add_facility(src: Path, name: str, profile_id: str, product_type: str | None = None) -> dict:
    """시설 등록 + 도면 복사/지문 + DB 적재. 멱등(재실행 시 갱신)."""
    facility_id = make_facility_id(name)
    drawings = unpack.register(Path(src), facility_id, raw_dir())

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO facility (id, name, product_type, profile_id)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE
                 SET name = EXCLUDED.name, product_type = EXCLUDED.product_type,
                     profile_id = EXCLUDED.profile_id""",
            (facility_id, name, product_type, profile_id),
        )
        for d in drawings:
            drawing_id = f"{facility_id}:{d['filename']}"
            cur.execute(
                """INSERT INTO drawing (id, facility_id, kind, filename, sha256)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE
                     SET kind = EXCLUDED.kind, sha256 = EXCLUDED.sha256""",
                (drawing_id, facility_id, d["kind"], d["filename"], d["sha256"]),
            )
            d["id"] = drawing_id
        conn.commit()

    return {"facility_id": facility_id, "name": name, "profile_id": profile_id,
            "drawings": drawings}


def get_facility(facility_id: str) -> dict | None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name, product_type, profile_id FROM facility WHERE id=%s",
                    (facility_id,))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("SELECT id, kind, filename, sha256 FROM drawing WHERE facility_id=%s ORDER BY filename",
                    (facility_id,))
        drawings = [{"id": r[0], "kind": r[1], "filename": r[2], "sha256": r[3]}
                    for r in cur.fetchall()]
    return {"facility_id": row[0], "name": row[1], "product_type": row[2],
            "profile_id": row[3], "drawings": drawings}
