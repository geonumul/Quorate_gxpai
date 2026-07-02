# GXPAI Engine

GMP(의약품 제조·품질관리) 시설 도면을 자동으로 구조화·검증·생성하는 엔진.
DXF 도면 → 정규화 저장소 → 지식 그래프(온톨로지) → 규칙 기반 violations 검증 → 레퍼런스 기반 배치 생성.

**다중 시설 확장을 전제로 설계**: 데이터가 1건이어도 N건 구조로 만든다. 신규 시설은
코드 수정 없이 프로파일 YAML 추가만으로 처리된다.

## 파이프라인 (Stage)
| Stage | 이름 | 내용 |
|---|---|---|
| 1 | Ingestion | N개 시설 DXF → 정규화 저장소 (프로파일 기반 추출) |
| 2 | Compliance | 온톨로지 + violations 규칙 엔진 + HTML 리포트 **(필수 납품)** |
| 3 | Generation | 레퍼런스 기반 CSP 배치 + DXF 출력 |
| 4 | Intelligence | LLM 파서, RAG, 수정이력 학습 루프 |
| 5 | Service | API 서버 (CLI 계약을 그대로 래핑) |

## 아키텍처
```
zip → [ingest] → PostgreSQL(정형) ─┐
                                    ├→ [ontology] → Neo4j(그래프) → [compliance] → violations → [render] → HTML/SVG 리포트
      profiles/*.yaml (시설 파라미터)┘                                                            → [generate] → CSP → DXF
```
- **정형 데이터**: PostgreSQL (pgvector) · **그래프**: Neo4j · **파생물**: `artifacts/{facility_id}/{run_id}/`
- **규칙·프로파일은 데이터** (`rules/`, `profiles/`) — 코드 배포 없이 확장
- 상세: [docs/GUIDELINE.md](docs/GUIDELINE.md)

## 빠른 시작 (개발)
```bash
# 1) 인프라 기동 (PostgreSQL + Neo4j)
cp .env.example .env
docker compose up -d

# 2) 엔진 설치
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -e ".[dev]"

# 3) CLI 확인
gxpai --version
gxpai --help

# 4) 품질 게이트
ruff check .
pytest
```

## CLI (전체 기능 진입점)
```bash
gxpai facility add <zip> --name "..." --profile osd_hs_2025
gxpai inventory <facility_id>
gxpai profile wizard <facility_id>
gxpai run all <facility_id>          # ingest → graph → validate → report
```

## 저장소 규약
- **고객 원본 도면은 절대 커밋 금지** (`.gitignore`: `raw/`, `artifacts/`, `*.dxf/*.dwg/*.zip`). fixture는 합성 DXF만.
- **원본 불변**: 입력 DXF는 수정하지 않는다. 모든 산출물은 재생성 가능한 파생물.
- **재현성**: 산출물에 `pipeline_version`·`profile_version`·`source_hash` 스탬프.
- DB 스키마 변경은 `db/migrations/NNN_*.sql` 로만.

## 상태
초기 골격(skeleton). 진행 상황은 [docs/PROGRESS.md](docs/PROGRESS.md).
