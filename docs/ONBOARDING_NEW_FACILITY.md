# 신규 시설 온보딩 절차 (T1.3.1 — 초안)

> 목표: 새 zip 수령 시 **코드 수정 0줄**로 리포트까지. 이 절차가 아키텍처의 심판(T1.3.2).

## 체크리스트
1. [ ] zip을 `raw/` 밖 안전한 곳에 수령 (커밋 금지)
2. [ ] `gxpai facility add <zip> --name "<시설명>" --profile <기존 or 신규 profile_id>`
       → DB에 facility/drawing 행 + sha256 매니페스트 생성
3. [ ] `gxpai inventory <facility_id>` → 레이어/텍스트/블록 통계 확인
4. [ ] `gxpai profile wizard <facility_id>` → 프로파일 초안 자동 생성
5. [ ] 초안을 사람이 검토·수정만 (`profiles/<new>.yaml`)
6. [ ] `gxpai run all <facility_id>` (ingest→graph→validate→report)
7. [ ] `artifacts/<facility_id>/<run_id>/report.html` 검수 — 품질 지표(매칭률/boundary율/귀속률) 확인

## 판단 기준
- 동일 설계사 도면이면 기존 프로파일 재사용률↑ (온보딩 견적에 반영 — question 시드 참조).
- wizard 초안이 수동 프로파일과 핵심 필드 80% 일치해야 정상.
