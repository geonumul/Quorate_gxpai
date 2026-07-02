# 규칙 작성 가이드 (RULE_AUTHORING)

규칙은 **데이터**다. 코드 배포 없이 `rules/*.yaml` 추가/수정만으로 신규 규칙을 도입한다.

## 규칙 1건 구조
```yaml
- id: PRES-001            # 규칙 ID = compliance/checks/ 파일명과 대응
  severity: critical      # critical | major | minor
  title: "..."
  desc: "..."
  ref: "별표17 / PIC-S Annex ... (검수대기)"   # GMP 근거 — 컨설턴트 검수 대상 표기 필수
  status: draft           # draft | active
```

## 규칙 추가 절차
1. `rules/<ruleset>.yaml`에 규칙 항목 추가.
2. `gxpai/compliance/checks/<rule_id>.py`에 검출 로직 구현 (엔진이 파일명으로 동적 로드).
3. `tests/fixtures/synthetic/`에 위반 케이스 + 정상 케이스 fixture 추가.
4. 회귀 테스트: 위반 검출 + 정상 도면 false-positive 0 확인.
5. `rules/refs/<rule_id>.md`에 GMP 근거 조항 메모 (검수 전 `draft`).
