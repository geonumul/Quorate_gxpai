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
- **다음 첫 태스크(Stage 2 진입)**: S-1(화살표 방향 의미 확정 - `blocks` 정의 지오메트리 분석, 최우선) → T2.1.1(방 경계 3전략). Stage2 진입 게이트: R-F2(OCS 미러 3947건 WCS 변환) 필수. 검증 백로그는 docs/RISK_METHODOLOGY*.md.
- **Stage 1 잔여 백로그**: T1.2.2(설계개요 표 복원).

## Stage 1 - Ingestion Platform  ← 사실상 완료 (T1.2.2 표복원만 백로그)
- [x] T1.1.1  골격 + docker 스택 + facility add (지문+종류판별, facility/drawing 적재)
- [x] T1.1.2  extractors 이식. **Acceptance 통과: room 111행(3F51/4F60) = master_rooms.json 일치**
- [x] T1.1.3  profile wizard (인벤토리→초안, 내용 패턴 스코어링). CLI: `gxpai profile wizard`
- [x] T1.2.1  HVAC 추출기 (AHU 20개 적재)
- [ ] T1.2.2  설계개요 표 복원 - **백로그** (행 그룹핑 필요; 현재 미구현)
- [x] T1.2.3  장비 추출기 (418개 추출 / 376개 방 귀속, method=nearest)
- [x] T1.2.4  Grade 추출기 스켈레톤 (pending_data) + question 시드(TA단위/Grade/화살표방향)
- [x] T1.3.1  ONBOARDING 문서 (실제 CLI 반영)
- [x] T1.3.2  **합성 신규 시설 온보딩 통과: 다른 레이어명/5자리 번호를 코드수정 0줄(프로파일만)로 처리.**
     테스트: tests/test_synthetic_onboarding.py (R-F1/S-3/S-10 회귀 고정). 발견·제거한 하드코딩: 종류판별 한/영 일반화.

### 검증 지표 (자동 산출값)
- 번호방 111 (3F 51 / 4F 60) · 무번호공간 52 · 장비 418(귀속 376) · AHU 20 · 화살표 98 · TA 98
- 인벤토리 진단: 평면도 OCS미러 3947(R-F2, Stage2 경계작업 시 처리), 정렬텍스트 774(R-F1 반영됨)

## Stage 2 - Compliance Engine (필수 납품)
- [ ] T2.1.* 방 경계 3전략 폴백 / 인접 / 장비 귀속 승격
- [ ] T2.2.* Neo4j 온톨로지 스키마·빌더·PRESSURE_OVER·표준질의
- [ ] T2.3.* 규칙 엔진 + 회귀 fixture (합성 위반 6/6)
- [ ] T2.4.* SVG + HTML 리포트 (= 중간보고)

## Stage 3~5
- 로드맵은 docs/GUIDELINE.md PART C 참조.
