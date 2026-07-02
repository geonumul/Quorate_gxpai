# legacy/v0.1 — 초기 플랫 스크립트 (이식 대상, 실행용 아님)

내용고형제 도면에서 방/차압 정보를 추출한 최초 PoC. **T1.1.2에서 `gxpai/ingest/extractors/`
플러그인으로 이식**되며, 하드코딩 상수(레이어명·거리)는 `profiles/osd_hs_2025.yaml`로 이관 완료.

| 스크립트 | → 이식 위치 |
|---|---|
| `extract_rooms.py`    | `gxpai/ingest/extractors/floorplan.py` |
| `extract_pressure.py` | `gxpai/ingest/extractors/pressure.py` |
| `merge_dataset.py`    | `gxpai/core/run.py` (병합 단계) |

**회귀 기준**: 원래 산출물 `master_rooms.json` (111 rooms, 이름불일치 4건)은 실 방이름을
포함해 커밋하지 않는다(.gitignore). 이식 후 DB `room` 테이블이 이 기준과 111행 일치해야 한다.

원본 실행 방식(참고):
```bash
python extract_rooms.py "<평면도.dxf>" -o rooms.json
python extract_pressure.py "<PRESSURIZATION.dxf>" -o pressure.json
python merge_dataset.py rooms.json pressure.json -o master_rooms.json
```
