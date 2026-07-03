# PROGRESS - 태스크 진행 상태

세션 프로토콜(D.2): GUIDELINE → PROGRESS → 현재 태스크 확인 → 구현 → Acceptance 실행 로그 첨부 → 커밋.

## 현재 위치
- **날짜**: 2026-07-02
- **완료**: 저장소 골격(디렉터리 트리, pyproject, docker-compose, migration 001, CLI 골격, 프로파일/규칙 YAML 초안). v0.1 스크립트 `legacy/`에 보존.
- **완료**: docker 스택 기동 확인 - postgres/neo4j 컨테이너 healthy, migration 001 자동 적용됨(테이블 10개 생성 + pgvector 확장 설치 확인), neo4j cypher 응답 OK.
  - 실행: `docker compose up -d` / 검증: `docker exec gxpai-postgres psql -U gxpai -d gxpai -c "\dt"` → 10 tables
- **완료**: T1.1.1 `facility add` - DXF 폴더/zip 등록, sha256 지문 + 종류 자동판별, facility/drawing 행 적재 (facility f_1ae3a266, 도면 7건).
- **완료**: T1.1.2 `ingest` - floorplan/pressure 추출기 이식 + 병합 + room 적재. **Acceptance 통과: 번호방 111개(3F 51/4F 60) = master_rooms.json 기준 일치.** 무번호 공간 43.
  - 리스크 반영: R-A1(정규화)·R-A2(TEXT+MTEXT)·S-3(평면도 병합)·S-10(frozen 제외)·R-F1(정렬점)·R-E3(멱등).
- **완료**: T1.2.2 설계개요 표 복원. **Stage 1(읽기) 전체 완료.**
- **완료**: Stage 1 감사(의심·검증) - 1·2층 방 부재는 정상(GMP번호 3·4층만), 6xxx=장비번호, frozen 유령방 0. 데이터손실(화살표/TA/이름) 수정.
- **완료(세로 슬라이스)**: Stage 2 - ingest→graph→validate→report 파이프라인 E2E 동작. LBL 규칙 2종·Neo4j·HTML 리포트.
- **다음 태스크**: (1) 발주처 XREF 벽체 수령 → 방 경계 3전략(T2.1.1) → PostGIS 면적/폴리곤 인접 승격.
  (2) 화살표 의미 발주처 확인 → PRES-001/002 가동. (3) Grade 도면 → ADJ 규칙. (4) T2.3.3 합성 위반 6종 회귀 fixture.
  검증 백로그: docs/RISK_METHODOLOGY*.md, ACC 논문(memory). Stage2 진입 게이트 R-F2(OCS 미러 3947) 경계작업 시 처리.

## Stage 1 - Ingestion Platform  ← 완료
- [x] T1.1.1  골격 + docker 스택 + facility add (지문+종류판별, facility/drawing 적재)
- [x] T1.1.2  extractors 이식. **Acceptance 통과: room 111행(3F51/4F60) = master_rooms.json 일치**
- [x] T1.1.3  profile wizard (인벤토리→초안, 내용 패턴 스코어링). CLI: `gxpai profile wizard`
- [x] T1.2.1  HVAC 추출기 (AHU 20개 적재)
- [x] T1.2.2  설계개요 표 복원 (키워드 앵커 + 행 그룹핑 → facility_meta 9항목)
- [x] T1.2.3  장비 추출기 (418개 추출 / 376개 방 귀속, method=nearest)
- [x] T1.2.4  Grade 추출기 스켈레톤 (pending_data) + question 시드(TA단위/Grade/화살표방향)
- [x] T1.3.1  ONBOARDING 문서 (실제 CLI 반영)
- [x] T1.3.2  **합성 신규 시설 온보딩 통과: 다른 레이어명/5자리 번호를 코드수정 0줄(프로파일만)로 처리.**
     테스트: tests/test_synthetic_onboarding.py (R-F1/S-3/S-10 회귀 고정). 발견·제거한 하드코딩: 종류판별 한/영 일반화.

### 검증 지표 (자동 산출값)
- 번호방 111 (3F 51 / 4F 60) · 무번호공간 52 · 장비 418(귀속 376) · AHU 20 · 화살표 98 · TA 98
- 인벤토리 진단: 평면도 OCS미러 3947(R-F2, Stage2 경계작업 시 처리), 정렬텍스트 774(R-F1 반영됨)

## Stage 2 - Compliance Engine (필수 납품) - 진행 중, 세로 슬라이스 동작
- [~] T2.1  인접: 최근접 k=3 같은층 근사 283간선 적재(method=nearest). **방 경계 폴리곤은 보류**
       (XREF 벽체 미수령 = strategy1/2 불가, strategy3 flood-fill 은 벽 LINE 필요). 발주처 XREF 수령 시 착수.
       장비 귀속 승격(contains)도 경계 의존이라 보류(현재 nearest 376/418).
- [x] T2.2  Neo4j 온톨로지: schema v1 + 멱등 빌더(노드 121·관계 288) + queries(이웃/고립방/통계).
       **PRESSURE_OVER 미생성**(S-1 화살표 의미 미확정 - 규칙 오류 증폭 방지, 정직성).
- [~] T2.3  violations 엔진(규칙 YAML→checks 동적실행→적재, 멱등). **LBL-001(3)·LBL-002(17) 동작·검증.**
       **리팩터: 검사 로직을 순수 함수 evaluate()+DB 어댑터 run() 로 분리**(_model.py) - DB 없이 시험,
       Stage3 생성 자기검증 재사용. PRES-001·ADJ-001 **순수 로직 완성+합성 시험 통과, 게이트(enabled:false)로
       실제 미가동**(S-1 "3중확인 전 가동금지"). PRES-002·ADJ-002 미구현(단위·검수 대기).
- [x] T2.3.3 **합성 위반 회귀 시험**(tests/test_compliance_rules.py, 10건): 각 규칙 위반 검출 + 오탐 0 + 게이트.
- [x] T2.4  단일파일 HTML 리포트(지표+violations+층별 SVG data-room-no) + metrics.json. 정합성 경고 배너.
- [x] 버그수정: CLI 한글 출력 깨짐(cp949) → main() 진입에서 stdout/stderr UTF-8 고정.

### 데이터 대기 백로그
- `docs/데이터_대기_작업.md`: 코드 준비 완료·게이트 잠김 항목(PRES-001/ADJ-001)과 활성화 방법, 미착수(PRES-002/ADJ-002/경계) 추적.

### Stage 2 교차검증 수렴 (신뢰 근거)
- 고립방(X-14, 그래프) 17 = LBL-002(차압도전용) 17 = 도면간 방차이. 독립 3소스 일치.
- 리포트 '양쪽도면 매칭' 94 = v0.1 기준 94. 번호방 111개는 변경 후에도 유지되는 기준값(전 단계 불변).

### S-1 화살표 방향 (분석 결과 기록)
- 블록 A$C2C2E3906(98회): rotation=0 에서 화살촉이 -y(아래). 세계각도 = 270°+rotation.
- 기하 방향 확정. 단 "화살촉=고압→저압" 의미는 발주처 확인/명백케이스 대조 필요(question 등록). 확인 전 PRES 규칙 미가동.

## Stage 3~5
- 로드맵은 docs/GUIDELINE.md PART C 참조.
