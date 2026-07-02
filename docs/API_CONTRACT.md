# API Contract (선제 문서화 — Stage 5)

Web/전자서명/대시보드는 타 팀 스코프. 우리는 JSON 스키마를 선제 문서화해 협업 주도권을 갖는다.
FastAPI는 cli.py가 부르는 core 함수를 1:1로 래핑만 하므로 아래 매핑은 CLI 계약(B.3)과 동형이다.

| CLI | HTTP (예정) |
|---|---|
| `facility add`        | `POST /api/v1/facilities` |
| `inventory <fid>`     | `GET  /api/v1/facilities/{fid}/inventory` |
| `profile wizard <fid>`| `POST /api/v1/facilities/{fid}/profile:wizard` |
| `ingest <fid>`        | `POST /api/v1/facilities/{fid}/runs` |
| `graph build <fid>`   | `POST /api/v1/facilities/{fid}/graph` |
| `validate <fid>`      | `POST /api/v1/facilities/{fid}/validations` |
| `report <fid>`        | `GET  /api/v1/facilities/{fid}/report` |
| `generate`            | `POST /api/v1/generations` |
| `export dxf <run_id>` | `GET  /api/v1/runs/{run_id}/export/dxf` |

> 스키마 본문(요청/응답 JSON)은 core 함수 시그니처 확정 시 이 문서에 채운다.
