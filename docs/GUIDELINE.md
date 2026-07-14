# GXPAI 도면 자동화 엔진 — 프로덕션 가이드라인 v2.0
### (다중 시설 확장, 완전 제품화 로드맵, 포트폴리오 마감 기준 포함)

> v1과의 차이: "가볍게"를 버린다. 기업 납품 기준으로 처음부터
> **다중 시설 데이터 파이프라인 + 영속 저장소 + 재현성**을 갖춘다.
> 데이터가 1건이어도 N건 구조로 만든다. 1건은 N=1일 뿐이다.

---

# PART A. 제품 비전과 단계 정의

## A.1 최종 제품 (발주처 계획서와 정렬)
발주처 구축계획서의 12개 모듈 중, 이 프로젝트(= 내 담당 엔진)는 다음의 **원천 기술 코어**다:

| 계획서 모듈 | 이 엔진에서의 대응 | 단계 |
|---|---|---|
| ① LLM 파서 엔진 | Stage 4: 질의서/URS → PlanSpec JSON | 제품화 |
| ② CAD 엔진 (CSP) | Stage 3: OR-Tools 배치 + 제약 라이브러리 | 코어 |
| ③ DXF 생성기 | Stage 3: ezdxf 출력 (도면 세트 점진 확장) | 코어→제품화 |
| ④ violations 체크 | Stage 2: 규칙 엔진 (본 프로젝트 필수 납품물) | **코어** |
| ⑤ AI 학습 파이프라인 | Stage 4: 도면 온톨로지 → RAG (Fine-tuning 제외) | 제품화 |
| ⑫ DB 설계 | Stage 1: PostgreSQL + 그래프 저장소 | **코어** |

**단계 정의** (아래 전체 로드맵의 뼈대):
- **Stage 1 — Ingestion Platform** (지금~) : N개 시설 DXF → 정규화 저장소. *데이터가 자산이 되는 층*
- **Stage 2 — Compliance Engine** (필수 납품) : 온톨로지 + violations + 리포트
- **Stage 3 — Generation Engine** (핵심 차별화) : 레퍼런스 기반 CSP 배치 + DXF 출력
- **Stage 4 — Intelligence Layer** (제품화) : LLM 파서, RAG, 수정이력 학습 루프
- **Stage 5 — Service Layer** (2단계 사업, 스코프 밖이지만 인터페이스는 지금 설계) : API 서버, UI

**이번 계약의 납품선 = Stage 2 완성 + Stage 3 best-effort.**
그러나 코드 구조는 Stage 5까지 수용 가능해야 한다 (아래 B.2 아키텍처).

## A.2 절대 원칙 (전 단계 공통)
1. **모든 것은 시설(facility) 단위로 격리, 병렬**된다. 전역 상태 금지
2. **원본 불변(immutable raw)**: 입력 DXF는 절대 수정하지 않는다. 모든 산출물은 파생물이며 재생성 가능
3. **재현성**: 동일 입력 + 동일 코드 버전 = 동일 출력. 모든 산출물에 `pipeline_version`, `profile_version`, `source_hash` 스탬프
4. **규칙, 프로파일은 데이터**: 코드 배포 없이 YAML 추가만으로 신규 시설/규칙 대응
5. **검증 없는 완료 없음**: 태스크마다 Acceptance를 실제 실행. 실패한 채 "완료" 선언 금지
6. **고객 도면 절대 커밋 금지**: `data/`, `output/` git-ignore. 테스트 fixture는 익명화 합성 도면만
7. **모르면 QUESTIONS.md**: 단위, 규칙, 규정 근거는 추측하지 않고 기록 후 진행

---

# PART B. 프로덕션 아키텍처

## B.1 저장소 선택 (확정)
"가볍게 networkx+JSON"이 아니라 처음부터 영속 저장소를 쓴다. 단, 운영 부담을 낮추는 조합:

| 데이터 | 저장소 | 이유 |
|---|---|---|
| 시설/도면/방/설비 정형 데이터 | **PostgreSQL** (로컬은 docker-compose, 개발 편의용 SQLite 폴백 금지 — 방언 차이로 이중비용) | 계획서 스택과 동일. 다중 시설 쿼리, 이력 관리 |
| 온톨로지 그래프 | **Neo4j** (docker) | 관계 질의(압력 경로, 인접 체인)가 본질. 카톡방 AlexAI 검증 스택. Cypher가 규칙 표현에 유리 |
| 임베딩 (Stage 4) | **pgvector** (PostgreSQL 확장) | 계획서 명세. DB 하나로 통합 |
| 파생 파일 (SVG/DXF/리포트) | 파일시스템 `artifacts/{facility_id}/{run_id}/` | 버전 폴더로 재현성 |
| 원본 도면 | `raw/{facility_id}/` 읽기전용 | sha256 매니페스트 동봉 |

`docker-compose.yml` 하나로 postgres+neo4j 기동. **에이전트 규칙: DB 스키마 변경은
반드시 마이그레이션 파일(`db/migrations/NNN_*.sql`)로. 손 ALTER 금지.**

## B.2 코드 아키텍처 — 파이프라인 프레임워크
```
gxpai-engine/
├── docs/GUIDELINE.md              # 이 문서
├── docker-compose.yml             # postgres + neo4j
├── pyproject.toml                 # 패키지화 (pip install -e .)
├── gxpai/
│   ├── core/
│   │   ├── registry.py            # 시설 레지스트리 (등록/조회/상태)
│   │   ├── run.py                 # Run 개념: 파이프라인 1회 실행 단위, run_id 발급
│   │   ├── config.py              # 설정 로딩 (env + yaml)
│   │   └── db.py                  # 커넥션/세션 관리
│   ├── ingest/                    # Stage 1
│   │   ├── unpack.py              # zip 해제 (cp949), 매니페스트 생성
│   │   ├── inventory.py           # DXF 레이어/텍스트/블록 인벤토리
│   │   ├── profile_wizard.py      # 인벤토리 → 프로파일 초안 자동 생성
│   │   └── extractors/            # 도면종류별 추출기 (플러그인 구조)
│   │       ├── base.py            # BaseExtractor: extract(dxf, profile) -> records
│   │       ├── floorplan.py
│   │       ├── pressure.py
│   │       ├── hvac.py
│   │       ├── grades.py
│   │       └── overview.py
│   ├── geometry/                  # Stage 1-2 경계
│   │   ├── boundaries.py          # 방 폴리곤 (3전략 폴백 체인)
│   │   └── adjacency.py
│   ├── ontology/                  # Stage 2
│   │   ├── schema.py              # 노드/엣지 타입 (버전 관리)
│   │   ├── builder.py             # DB → Neo4j 적재
│   │   └── queries.py             # 표준 질의 함수 (엔진은 이것만 사용)
│   ├── compliance/                # Stage 2
│   │   ├── engine.py
│   │   └── checks/                # 규칙ID = 파일명
│   ├── generate/                  # Stage 3
│   │   ├── spec.py                # PlanSpec 스키마
│   │   ├── csp.py                 # OR-Tools 배치
│   │   ├── priors.py              # 레퍼런스 온톨로지 → 인접/면적 사전분포
│   │   └── loop.py                # 생성→검증→재시도 루프
│   ├── render/
│   │   ├── svg.py
│   │   └── report.py
│   ├── export/
│   │   └── dxf.py
│   └── cli.py                     # 단일 진입점: `gxpai <command>`
├── profiles/                      # 시설군별 레이어 프로파일
│   ├── _schema.yaml               # 프로파일 자체의 스키마 (검증용)
│   └── osd_hs_2025.yaml           # 현 데이터 (시설군+설계사+연도로 명명)
├── rules/
│   ├── gmp_osd_v1.yaml
│   └── refs/                      # 규칙별 GMP 근거 조항 메모
├── db/migrations/
├── tests/
│   ├── fixtures/synthetic/        # 합성 미니 DXF (방 5~10개, 자체 생성 스크립트 포함)
│   └── ...
├── raw/        (git-ignore)
├── artifacts/  (git-ignore)
└── docs/
    ├── ONBOARDING_NEW_FACILITY.md # 신규 zip 수령 시 절차서
    ├── RULE_AUTHORING.md
    └── PORTFOLIO.md               # 포트폴리오 산출물 트래킹
```

## B.3 CLI 계약 (모든 기능은 CLI로 노출 — Stage 5 API의 전신)
```bash
gxpai facility add <zip> --name "내용고형제" --profile osd_hs_2025   # 등록+해제+매니페스트
gxpai inventory <facility_id> [--dxf <name>]                        # 프로파일링 근거 출력
gxpai profile wizard <facility_id>                                  # 프로파일 초안 자동 생성
gxpai ingest <facility_id>                                          # 전체 추출 → DB 적재 (run_id 발급)
gxpai graph build <facility_id>                                     # 온톨로지 → Neo4j
gxpai validate <facility_id> --rules gmp_osd_v1                     # violations
gxpai report <facility_id>                                          # HTML 리포트
gxpai generate --spec spec.yaml --refs <fid1,fid2>                  # 레퍼런스 기반 배치
gxpai export dxf <run_id>
gxpai run all <facility_id>                                         # ingest→graph→validate→report
```
**Acceptance(아키텍처 레벨)**: 두 번째 시설 zip이 왔을 때 코드 수정 0줄,
`profile wizard` + YAML 수정 + `run all`만으로 리포트가 나와야 한다. 이것이 이 설계의 존재 이유.

## B.4 DB 핵심 스키마 (마이그레이션 001)
```sql
facility(id, name, product_type, profile_id, created_at)
drawing(id, facility_id, kind, filename, sha256, dxf_version, ingested_at)
run(id, facility_id, pipeline_version, profile_version, started_at, status)
room(id, facility_id, run_id, room_no, name, floor, sheet,
     plan_x, plan_y, boundary GEOMETRY NULL, area_m2, grade,
     source_drawing_id, confidence REAL, review_status)   -- confidence/review는 Stage 4 학습루프 대비
room_adjacency(run_id, room_a, room_b, method)            -- method: polygon|nearest
pressure_relation(run_id, room_high, room_low, evidence_x, evidence_y, rotation)
equipment(run_id, facility_id, name, room_id, x, y, method)
ahu(run_id, facility_id, ahu_id, x, y, floor)
violation(run_id, rule_id, severity, rooms JSONB, message, evidence JSONB, status) -- status: open|accepted|false_positive
question(id, facility_id, topic, body, status, answer)     -- QUESTIONS를 DB로 승격
```
`violation.status`와 `room.review_status`가 중요하다: 컨설턴트 피드백(수정/승인)이
데이터로 쌓여 Stage 4 학습 루프의 원료가 된다. **지금 컬럼만 만들어 두는 것이 미래를 사는 것.**

## B.5 품질 게이트 (CI — GitHub Actions)
- push마다: ruff(lint) + pytest(합성 fixture) + 프로파일/규칙 YAML 스키마 검증
- 태그마다: 합성 시설 1개 전체 파이프라인 E2E (docker service 포함)
- 커버리지 목표: extract/compliance 모듈 80%+

---

# PART C. 실행 로드맵 (Stage별 상세 태스크)

각 태스크: **목표 / 방법 / 함정, 폴백 / Acceptance(실행 확인)**. `docs/PROGRESS.md`에 체크 상태 유지.

## Stage 1 — Ingestion Platform (1.5주)

### S1.1 골격 (2일)
- [ ] **T1.1.1** pyproject 패키지화 + docker-compose(postgres16+neo4j5) + 마이그레이션 001 + `gxpai` CLI 골격
  - Acceptance: `docker compose up -d && gxpai facility add <현재zip>` → DB에 facility/drawing 행 + sha256 매니페스트
- [ ] **T1.1.2** v0.1 코드(extract_rooms/pressure/merge)를 `ingest/extractors/` 플러그인으로 이식.
  BaseExtractor 인터페이스: `extract(doc: ezdxf.Document, profile: dict) -> list[Record]`
  - 함정: 기존 스크립트의 하드코딩(레이어명, 거리 상수) 전부 프로파일로 이동. grep으로 잔존 상수 검사
  - Acceptance: `gxpai ingest <fid>` 후 DB room 테이블 = 기존 master_rooms.json과 111행 일치 (비교 스크립트 작성)
- [ ] **T1.1.3** `profile wizard`: inventory 결과에서 방번호 패턴 후보(정규식 매칭율 상위), 라벨 레이어 후보
  (한글 TEXT 밀도 상위 레이어), 화살표 블록 후보(INSERT 반복 상위)를 스코어링해 YAML 초안 생성
  - 이것이 "데이터 많아져도 그대로 작동"의 실체다. 사람은 초안을 검토, 수정만 한다
  - Acceptance: 현 시설에서 wizard 초안이 수동 프로파일과 핵심 필드 80% 일치

### S1.2 추출 완성 (3일)
- [ ] **T1.2.1** HVAC 추출기: AHU 태그+위치. 존 경계는 실측 후 가능 시. 폴백: 태그만
- [ ] **T1.2.2** 설계개요 추출기: 표 복원(행 그룹핑 |dy|<300) + 키워드 사전 항목만. facility 메타로 저장
- [ ] **T1.2.3** 장비 추출기: 좌표 수집 → room 귀속 (method=nearest, Stage2에서 contains 승격)
- [ ] **T1.2.4** Grade 추출기: 프로파일에 `hatch_color_to_grade` 매핑 스키마 확정, 데이터 수령 전까지 스켈레톤.
  question 테이블에 수령 요청 기록
  - Stage 공통 Acceptance: `gxpai run all` E2E 통과, 추출율 리포트(방 라벨 매칭률, 장비 귀속률) 자동 출력

### S1.3 신규 시설 온보딩 리허설 (1일)
- [ ] **T1.3.1** `docs/ONBOARDING_NEW_FACILITY.md` 작성: zip 수령→facility add→inventory→
  profile wizard→검토→run all→리포트 검수, 체크리스트 형식
- [ ] **T1.3.2** 합성 "가짜 신규 시설" 생성(레이어명 변형 + 방번호 5자리 변형한 미니 DXF)으로 온보딩 절차 실측
  - Acceptance: 코드 수정 0줄로 통과. 실패 시 하드코딩 잔존 → 즉시 제거 (이 테스트가 아키텍처의 심판)

## Stage 2 — Compliance Engine (2주) ← **필수 납품 코어**

### S2.1 방 경계 & 인접 (4일, 최고 난도)
- [ ] **T2.1.1** 3전략 폴백 체인을 `geometry/boundaries.py`에 명시적 구현:
  ```
  strategy 1: 프로파일 지정 방경계 폴리라인 레이어 (닫힘 && 면적 5~500㎡ && 라벨 내포)
  strategy 2: XREF 원본 (수령 시)
  strategy 3: 벽체 LINE flood-fill (shapely buffer(50)→union→라벨점 소속 공간)
              — 시트 bbox로 crop 후 처리, 시트당 메모리 상한
  실패: boundary NULL + method='label_only'
  ```
  방마다 어느 전략으로 얻었는지 `room.boundary_method` 기록 (신뢰도 추적)
  - Acceptance: 3F/4F 111방 중 boundary 80%+. 층별 면적합 vs 설계개요 오차 ±15%
- [ ] **T2.1.2** 인접행렬: buffer(150) 교차 → room_adjacency. boundary 없는 방은 최근접 k=3 근사(method 구분)
  - Acceptance: 무작위 5방 인접목록 PDF 육안 대조 오류 ≤1
- [ ] **T2.1.3** 장비 귀속 승격: point-in-polygon으로 재계산, method 갱신

### S2.2 온톨로지 (Neo4j) (3일)
- [ ] **T2.2.1** 스키마 v1: (Facility)-[:HAS]->(Floor)-[:HAS]->(Room),
  Room-[:ADJACENT_TO]-Room, Room-[:PRESSURE_OVER]->Room, Room-[:IN_ZONE]->(Zone:Grade),
  Room-[:SERVED_BY]->(AHU), Room-[:CONTAINS]->(Equipment).
  모든 노드에 `facility_id` 속성 — **다중 시설 격리 키**
- [ ] **T2.2.2** builder: DB→Neo4j 멱등 적재 (재실행 시 해당 run 삭제 후 재생성)
- [ ] **T2.2.3** PRESSURE_OVER 도출: 화살표 rotation 벡터 → 걸친 인접 경계의 고압/저압 판정.
  boundary 없는 구간은 최근접 2방 근사 + `approx=true` 플래그
- [ ] **T2.2.4** `ontology/queries.py` 표준 질의 8종: 압력 경로, 갱의 체인, AHU 서비스 방,
  Grade 경계 통과 인접쌍, 시설 간 방유형 통계(Stage 3 priors용) 등. **엔진은 이 모듈만 사용**
  - Acceptance: Cypher 브라우저에서 3F 그래프 시각 확인 + PRESSURE_OVER 5개 PDF 화살표 대조

### S2.3 violations (4일)
- [ ] **T2.3.1** 규칙 YAML v1 (6종: PRES-001/002, ADJ-001/002, LBL-001/002 — v1 문서 정의 승계)
  + `rules/refs/`에 규칙별 GMP 근거 조항 초안 (별표17, PIC/S Annex — **컨설턴트 검수 대상 표기**)
- [ ] **T2.3.2** 엔진: 규칙 로드→checks 동적 실행→violation 테이블 적재.
  Grade 미확보 상태의 PRES-001은 방이름 서열 휴리스틱으로 가동하되 리포트에 휴리스틱 명시
- [ ] **T2.3.3** 회귀 fixture: 합성 도면에 위반 6종을 각각 심은 케이스 → 전 규칙 검출 테스트
  - Acceptance: LBL-001이 실데이터 기존 4건 재검출 + 합성 위반 6/6 검출 + false-positive 0 (정상 합성 도면에서)

### S2.4 리포트 (2일)
- [ ] **T2.4.1** SVG 렌더: 층별, Grade 색상, violations 마커, `data-room-no` 속성(기계가독).
  boundary 없는 방은 라벨 마커
- [ ] **T2.4.2** HTML 리포트: violations 표(심각도 정렬, 근거 좌표 링크) + SVG 임베드 +
  품질 지표(매칭률/boundary율/귀속률) + 파이프라인 버전 스탬프. 단일 파일, CDN 금지
  - Acceptance: **이 리포트가 중간보고 겸 포트폴리오 1호 산출물**. 발주처 시연 가능 수준

## Stage 3 — Generation Engine (2주, best-effort → 포트폴리오 핵심)

- [ ] **T3.1** PlanSpec 스키마: 시설타입/방 목록(유형, 요구면적, Grade)/생산규모/제약. YAML+JSON Schema 검증
- [ ] **T3.2** priors.py: 레퍼런스 온톨로지(들)에서 통계 추출 —
  (방유형쌍→인접빈도), (방유형→면적분포), (Grade 전이→차압 방향 패턴), 갱의 체인 템플릿.
  **시설 N개를 모두 합산하는 구조로** (지금은 N=1)
- [ ] **T3.3** CSP: 기존 v0(OR-Tools) 이식 + hard 제약(면적 하한, Grade 인접 금지쌍, 갱의 체인) +
  soft 제약(priors 가중치). 그리드→직사각형 packing 순으로 단계 상향
- [ ] **T3.4** 자가검증 루프: 생성안→가상 run으로 DB 적재→Stage2 엔진 검증→critical>0이면
  위반 엣지를 제약으로 추가해 재시도(≤5회). — 카톡방 AlexAI의 "스스로 테스트하고 고치는 하네스" 방식
- [ ] **T3.5** DXF 출력: GXP-* 레이어 체계, R2013, 한글 스타일. 초기 세트 = 평면(방 폴리곤+라벨) /
  청정도 구분도 / 차압 방향도 3장. (28장 세트는 Stage 5 로드맵으로 명시만)
  - Acceptance: 3F 방 목록 입력 → critical 0 배치안 + DXF 3장, ezdxf 라운드트립 + 뷰어 오픈.
    **before(실도면)/after(생성안) 비교 이미지 = 포트폴리오 2호**

## Stage 4 — Intelligence Layer (제품화, 계약 후반 또는 차기)

- [ ] **T4.1** LLM 파서: 질의서/회의록/URS(문서) → PlanSpec 초안. LLM API(모델은 Stage 4 착수 시 선정) + few-shot,
  파싱 confidence per-field, 사람 검토 UI는 CLI diff로 대체. 목표 정확도 95% (계획서 기준) —
  측정 프로토콜(골드셋 10건) 먼저 정의
- [ ] **T4.2** RAG: 방/규칙/과거 violations 텍스트를 pgvector 임베딩 → "이 방 배치의 유사 선례" 검색.
  Neo4j 그래프 질의와 하이브리드 (GraphRAG)
- [ ] **T4.3** 피드백 학습 루프: violation.status(accepted/false_positive)와 room.review_status
  누적 → 규칙 파라미터(거리 임계 등) 자동 튜닝 리포트 + priors 재계산 배치.
  "건수가 누적되면 완성도가 향상되는 구조"(계획서 1.1)의 실제 구현체
- [ ] **T4.4** 프로파일 자동화 고도화: wizard를 LLM 보조로 승격 (inventory→프로파일 전체 초안)

## Stage 5 — Service Layer (2단계 사업 — 인터페이스만 지금 준비)
- FastAPI 래핑: CLI 커맨드 1:1 매핑 (`POST /api/v1/facilities`, `/runs`, `/violations`...) —
  cli.py가 core 함수를 직접 부르는 구조라면 API는 껍데기만 추가하면 된다. **그래서 CLI 계약이 중요**
- Web CAD/전자서명/대시보드는 계획서상 타 팀 스코프. 우리는 API Contract(JSON 스키마)를
  `docs/API_CONTRACT.md`로 선제 문서화 → 협업 시 주도권

---

# PART D. 운영 규약

## D.1 일정 (필수 납품 기준 5~6주)
| 주차 | Stage | 마일스톤 |
|---|---|---|
| 1~1.5주 | S1 | 플랫폼 가동, 온보딩 리허설 통과 (코드수정 0줄 테스트) |
| 2~3.5주 | S2 | boundary 80%+, Neo4j 온톨로지, 규칙 6종, **HTML 리포트 = 중간보고** |
| 4~5.5주 | S3 | 자가검증 배치 루프, DXF 3장, before/after |
| 6주 | QA/납품 | E2E, 문서 4종, 납품 패키지 |
| 이후 | S4 | 계약 협의에 따라 |

리스크 강등 규칙: S2.1이 4일 초과 → strategy 3 포기, boundary 확보분만 폴리곤 규칙 적용
(나머지 근사 + 리포트에 커버리지 명시). S3.3 packing 난항 → 그리드 배치로 납품하고 packing은 로드맵 표기.
**일정 > 완성도. 단, 품질 지표를 숨기지 않고 리포트에 드러내는 것으로 정직성 유지.**

## D.2 작업 세션 프로토콜
1. docs/GUIDELINE.md → PROGRESS.md → 현재 태스크 확인
2. 태스크 1개 → 구현 → **Acceptance 실행 로그를 PROGRESS.md에 붙임** → 커밋 `[S2.1] ...`
3. 15분/3회 룰: 막히면 태스크에 명시된 폴백 실행 or question 테이블 기록 후 다음 태스크
4. DB 스키마 변경 = 마이그레이션 파일. Neo4j 적재 = 멱등. 대형 DXF = 캐시 확인 먼저
5. 세션 종료: PROGRESS.md에 "다음 첫 태스크" 1줄

## D.3 미결 질문 시드 (question 테이블 초기값)
TA 단위(CMH/Pa) / XREF 원본 / Grade DXF / 1F, 2F 차압도 / 문 블록 컨벤션 /
규칙 GMP 근거 컨설턴트 검수 / AutoCAD 실기 오픈 테스트 / (신규) 향후 수령 zip의 설계사 동일 여부
(동일 설계사면 프로파일 재사용률 높음 — 온보딩 견적에 반영)

---

# PART E. 포트폴리오 마감 기준 (docs/PORTFOLIO.md로 관리)

이 프로젝트는 용역인 동시에 본인 대표 프로젝트다. **납품물과 포트폴리오 산출물을 분리 관리**하되,
고객 데이터가 노출되는 것은 전부 익명화/합성 데이터 버전을 병행 생성한다.

## E.1 포트폴리오 산출물 체크리스트
1. **아키텍처 다이어그램**: Stage 1~5 계층 + 데이터 흐름 (zip→DB→Neo4j→violations→생성→DXF)
2. **정량 지표 표** (전부 파이프라인이 자동 산출하는 값):
   방 라벨 매칭률(94/111), boundary 확보율, violations 검출 정밀도(합성셋 6/6),
   신규 시설 온보딩 소요시간(코드수정 0줄), 생성 루프 수렴 횟수
3. **before/after 비주얼**: 실도면 SVG(익명화) vs 자동 검증 마커 vs 생성 배치안
4. **합성 데모 시설**: 고객 데이터 없이 전체 파이프라인을 시연 가능한 공개용 미니 시설
   (tests/fixtures/synthetic 확장) — GitHub 공개 리포의 데모가 됨
5. **기술 글 1편**: "GxP 도면의 온톨로지화 — DXF에서 지식그래프, 그리고 규칙 검증까지"
   (더티데이터 정제 병목, 3전략 폴백, 화살표→PRESSURE_OVER 도출이 좋은 소재)
6. **연구 접점 메모**: 방-인접-압력 그래프는 본인 전공(그래프 학습, 건설 안전 XAI)과 직결 —
   "GMP 시설 그래프에서 위반 패턴 학습" 같은 후속 연구 아이디어를 PORTFOLIO.md에 축적

## E.2 공개 범위 규약
- 공개 리포: 엔진 코드 + 합성 데모 + 문서 (고객명/실도면/실 방이름 전부 제거)
- 비공개: raw/, artifacts/, 고객 식별 가능 프로파일 값
- 발주처와 공개 범위 사전 서면 합의 (question 테이블에 항목 추가) — **포트폴리오 사용 허락을
  계약 초기에 받아두는 것이 마감 후 분쟁을 막는다**

## E.3 "완성"의 정의 (이 기준을 채우면 마무리로 선언)
- [ ] 신규 zip → 코드수정 0줄 → 리포트, 실측 1회 이상 성공
- [ ] violations 6종 이상 + 컨설턴트 근거 검수 1회 반영
- [ ] 자가검증 루프로 critical 0 배치안 + DXF 출력
- [ ] 합성 데모로 처음부터 끝까지 재현되는 공개 리포
- [ ] 지표 표 + 기술 글 + 다이어그램 완비
