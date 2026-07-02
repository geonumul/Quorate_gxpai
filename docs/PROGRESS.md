# PROGRESS — 태스크 진행 상태

세션 프로토콜(D.2): GUIDELINE → PROGRESS → 현재 태스크 확인 → 구현 → Acceptance 실행 로그 첨부 → 커밋.

## 현재 위치
- **날짜**: 2026-07-02
- **완료**: 저장소 골격(디렉터리 트리, pyproject, docker-compose, migration 001, CLI 골격, 프로파일/규칙 YAML 초안). v0.1 스크립트 `legacy/`에 보존.
- **다음 첫 태스크**: **T1.1.1** — docker 스택 기동 + 마이그레이션 적용 확인 + `gxpai facility add <zip>` 구현 (DB에 facility/drawing 행 + sha256 매니페스트).

## Stage 1 — Ingestion Platform
- [~] T1.1.1  골격 완료 / DB 기동·facility add 구현 남음
- [ ] T1.1.2  v0.1 → extractors 플러그인 이식 (Acceptance: room 테이블 = master_rooms.json 111행 일치)
- [ ] T1.1.3  profile wizard (인벤토리 → 프로파일 초안)
- [ ] T1.2.1  HVAC 추출기 (AHU 태그+위치)
- [ ] T1.2.2  설계개요 추출기 (표 복원)
- [ ] T1.2.3  장비 추출기 (nearest 귀속)
- [ ] T1.2.4  Grade 추출기 스켈레톤 (데이터 수령 대기)
- [ ] T1.3.1  ONBOARDING 문서
- [ ] T1.3.2  합성 신규 시설 온보딩 리허설 (코드수정 0줄 테스트)

## Stage 2 — Compliance Engine (필수 납품)
- [ ] T2.1.* 방 경계 3전략 폴백 / 인접 / 장비 귀속 승격
- [ ] T2.2.* Neo4j 온톨로지 스키마·빌더·PRESSURE_OVER·표준질의
- [ ] T2.3.* 규칙 엔진 + 회귀 fixture (합성 위반 6/6)
- [ ] T2.4.* SVG + HTML 리포트 (= 중간보고)

## Stage 3~5
- 로드맵은 docs/GUIDELINE.md PART C 참조.
