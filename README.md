# GXPAI Engine

의약품 공장(GMP 시설)의 설계 도면을 읽어서 방·기압·장비 정보를 구조화하고, 규정 위반을
자동으로 검사하며, 나중에는 규정을 지키는 배치안까지 생성하는 엔진이다.

GMP는 의약품을 안전하게 만들기 위한 제조·품질관리 기준이다. 이런 공장은 방마다 공기 청정도와
기압, 동선 규정이 까다로워서 지금은 사람이 도면을 일일이 검토한다. 이 프로젝트는 그 검토를
자동화하고, 한 공장이 아니라 여러 공장에 그대로 쓸 수 있게 만드는 것이 목표다.

핵심 설계 원칙: 새 공장 도면이 와도 코드는 고치지 않고 설정 파일(프로파일)만 추가해서 처리한다.
프로파일은 "이 공장 도면을 어떻게 읽어야 하는지" 적어둔 시설별 설정서다.

## 단계

1. 읽기(Ingestion) - 도면에서 방·기압·장비를 뽑아 데이터로 저장
2. 검사(Compliance) - 규정 위반을 찾아 리포트로 출력 (이번 계약의 핵심 납품물)
3. 생성(Generation) - 요구조건을 주면 규정을 지키는 배치안을 자동 생성
4. 지능화(Intelligence) - 요구서 문서를 AI가 읽어 입력으로 변환, 수정이력 학습
5. 서비스(Service) - 위 기능을 웹 API로 제공 (2단계 사업)

## 현재 상태

1단계(읽기)까지 동작한다. 실제 공장 도면에서 방 111개, 장비 418개, 공조기(공기조화기, AHU)
20개를 추출해 저장하는 것을 확인했고, 레이어 이름과 방 번호 체계가 전혀 다른 합성 도면도
코드 수정 없이 처리되는 것을 테스트로 확인했다. 자세한 진척은 [docs/PROGRESS.md](docs/PROGRESS.md).

## 동작 방식

```
도면(zip/DXF) --> 읽기 --> PostgreSQL(표 형태 저장) --+
                                                     +--> Neo4j(관계 저장) --> 검사 --> 위반 리포트
   프로파일(시설별 설정) --------------------------+                        --> 생성 --> 새 도면(DXF)
```

- DXF: CAD 도면을 다른 프로그램도 읽을 수 있게 풀어쓴 파일 형식. 원본 DWG(AutoCAD 전용)는 DXF로 변환해서 쓴다.
- PostgreSQL: 정보를 표(행·열) 형태로 저장하는 데이터베이스. 방·도면 목록을 담는다.
- Neo4j: 정보를 관계(A방이 B방과 붙어있다, 기압이 A에서 B로 흐른다) 형태로 저장하는 데이터베이스.
- 규칙과 프로파일은 코드가 아니라 데이터(`rules/`, `profiles/`)라서, 파일만 추가하면 새 규칙·새 시설에 대응한다.

설계 전반은 [docs/GUIDELINE.md](docs/GUIDELINE.md) 참고.

## 개발 환경

```bash
# 1. 데이터베이스 기동 (Docker 필요)
cp .env.example .env
docker compose up -d          # PostgreSQL + Neo4j

# 2. 엔진 설치 (Python 3.11+)
python -m venv .venv
. .venv/Scripts/activate       # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

# 3. 확인
gxpai --help
pytest
```

## 명령어

```bash
gxpai facility add <폴더또는zip> --name "공장이름" --profile osd_hs_2025
gxpai inventory <시설ID>        # 도면 속 레이어·글자·블록 통계
gxpai profile wizard <시설ID>   # 도면을 훑어 프로파일 초안 자동 생성
gxpai ingest <시설ID>           # 방·장비·기압을 추출해 저장
```

`facility add`, `inventory`, `profile wizard`, `ingest`는 현재 동작한다. `validate`(검사),
`report`(리포트), `generate`(생성)는 2·3단계에서 구현할 예정이다.

## 저장소 규칙

- 고객 원본 도면은 커밋하지 않는다. `raw/`, `artifacts/`, `*.dxf`, `*.dwg`, `*.zip`은 `.gitignore`로
  차단하고, 공개용 예제는 합성(가짜) 도면만 쓴다.
- 입력 도면은 수정하지 않는다. 모든 산출물은 다시 생성할 수 있는 파생물이다.
- 산출물에는 코드 버전·프로파일 버전·원본 지문(파일 내용으로 계산한 고유값, 위·변조 확인용)을
  기록해서, 같은 입력이면 항상 같은 결과가 나오게 한다.
- 데이터베이스 구조 변경은 마이그레이션 파일(`db/migrations/NNN_*.sql`)로만 한다.

## 폴더 구조

```
gxpai/          엔진 코드 (읽기·검사·생성 모듈)
profiles/       시설별 설정서
rules/          규정 위반 검사 규칙
db/migrations/  데이터베이스 구조 정의
docs/           설계·진행·검증·생성전략 문서
tests/          테스트 + 합성 예제 도면
legacy/         초기 프로토타입 (참고용)
```
