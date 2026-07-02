# 신규 시설 온보딩 절차 (T1.3.1 - 초안)

> 목표: 새 zip 수령 시 **코드 수정 0줄**로 리포트까지. 이 절차가 아키텍처의 심판(T1.3.2).

## 체크리스트 (현재 동작 기준)
1. [ ] zip 또는 DXF 폴더를 `raw/` 밖 안전한 곳에 수령 (커밋 금지)
2. [ ] `gxpai facility add <zip또는폴더> --name "<시설명>" --profile <profile_id>`
       → DXF를 raw/{facility_id}/ 로 복사, sha256 지문 + 종류 자동판별, facility/drawing 적재
3. [ ] `gxpai inventory <facility_id>` → 레이어/텍스트/블록 통계 + 진단(정렬텍스트/OCS미러/frozen)
4. [ ] `gxpai profile wizard <facility_id>` → `profiles/_draft_<facility_id>.yaml` 초안 자동 생성
5. [ ] 초안을 사람이 검토·수정 → `profiles/<new>.yaml` 로 정식 배치, facility 재등록
6. [ ] `gxpai ingest <facility_id>` → room/equipment/ahu 적재 + 미결질문 시드 (run_id 발급)
7. [ ] 검증 쿼리로 번호방/장비귀속/AHU 수 확인 (리포트 명령은 Stage 2 에서)

> 실측 완료(2026-07-02): 합성 시설(다른 레이어명·5자리 번호)을 **코드 수정 0줄**로 통과.
> 단, 도면 파일명이 특이하면 종류판별 키워드 확인 필요(현재 한/영 키워드 지원).

## 판단 기준
- 동일 설계사 도면이면 기존 프로파일 재사용률↑ (온보딩 견적에 반영 - question 시드 참조).
- wizard 초안이 수동 프로파일과 핵심 필드 80% 일치해야 정상.
