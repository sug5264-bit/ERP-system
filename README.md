# WellGreen ERP

음료/주류 제조 + 편의점 유통 + 수입식품 + 종합 물류를 다루는 가상 회사
**WellGreen**(웰그린)을 위한 모듈식 ERP 시스템 PoC입니다.
디자인 톤은 well-green.com 의 브랜드 컬러(브랜드 그린)에서 차용했습니다.

## 스택

- **Backend**: FastAPI + SQLAlchemy 2.0 + Postgres (Alembic 마이그레이션) / SQLite (로컬)
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind
- **Auth**: JWT (Bearer) + RBAC (admin / manager / staff / viewer)
- **구조**: Modular Monolith — 추후 모듈 추가가 용이

## 모듈

| 키 | 모듈 | 설명 |
|---|---|---|
| `hr` | HR / 인사 | 직원, 부서 관리 |
| `finance` | 재무 / 회계 | 계정과목, 분개 전표 |
| `inventory` | 재고 / 물류 | 품목, 입출고 이동 |
| `sales` | 영업 / CRM | 고객, 주문 (재고 차감 연동) |
| `reports` | 보고서 | 대시보드용 집계 (매출/재고/직원/계정) |
| `audit` | 감사 로그 | 모든 쓰기 요청을 자동 기록 (admin 전용) |
| `notifications` | 알림 | 재고 부족 / 미확정 주문 등 실시간 계산 |
| `attachments` | 첨부파일 | 모든 모듈 레코드에 파일 첨부 가능 |
| `approvals` | 결재 워크플로 | 다단계 결재 (승인/반려/취소), 이메일 통보 |
| `search` | 검색 | 모든 모듈 통합 검색 (직원/고객/품목/주문/계정/전표) |
| `currencies` | 통화/환율 | 다중 통화 지원, 환율 변환 (KRW/USD/EUR/JPY) |
| `tenants` | 멀티테넌시 | 본사/자회사 단위로 데이터 격리 (X-Tenant-ID 헤더) |
| `custom_fields` | 커스텀 필드 (EAV) | 모듈별 임의 속성 정의/저장 |
| `admin_ops` | 백업·복원·임포트 | 전체 JSON 백업/복원, Excel(xlsx) 일괄 등록 |
| `graphql` | GraphQL 게이트웨이 | `/graphql` 단일 엔드포인트 (read-only) |

### 추가 기능
- **i18n**: 한국어/영어 토글 (사이드바 상단 버튼)
- **대시보드**: 6개 KPI + 월별 매출 / 부서별 직원 / 재고가치 차트 (의존성 없는 inline SVG)
- **사용자 관리** (`/admin/users`): admin이 사용자 추가/삭제/역할 변경 + **모듈별 권한 오버라이드**
- **감사 로그** (`/admin/audit`): 사용자/메서드/경로/상태코드 필터 + CSV/Excel/PDF 내보내기
- **데이터 내보내기**: HR/재고/영업/감사 모든 페이지에서 CSV/Excel/PDF 다운로드
- **알림 벨**: 헤더 우측에 실시간 알림 (30초마다 갱신)
- **첨부파일**: 직원·주문 등에 파일 업로드/다운로드 (10MB 제한, 로컬 디스크 저장)
- **모듈별 권한 세분화**: 사용자별로 모듈마다 다른 역할 부여 가능
  - 예: HR=manager, Finance=viewer, Inventory=staff
  - 미설정 모듈은 사용자의 기본 역할 적용
- **결재 워크플로** (`/approvals`): 다단계 결재 (요청/승인/반려/취소)
  - 결재할 요청 / 내가 올린 요청 / 전체 탭
  - 각 단계 결재자 지정, 순차 진행, 어느 단계든 반려 시 즉시 종료
  - 결재 요청 시 첫 결재자에게 이메일 자동 발송 (SMTP 설정 시)
- **다크모드**: 헤더 우측 ☀️/🌙 토글, 시스템 선호도 자동 감지, localStorage 저장
- **통합 검색**: 헤더 검색바에서 모든 모듈을 ILIKE로 검색
- **OAuth/SSO**: Google 지원
  - 환경변수 `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` 설정 시 활성화
  - 로그인 화면에 "Google로 로그인" 버튼 자동 노출
  - 첫 로그인 시 사용자 자동 생성 (`OAUTH_DEFAULT_ROLE` 역할로)
- **이메일 알림 (SMTP)**: 결재 요청 + 재고부족 일괄 발송
  - SMTP 미설정 시 stdout으로 로그 (개발 편의)
  - `POST /api/notifications/email-alerts` (admin)
- **WebSocket 실시간 알림**: `/api/notifications/ws?token=...` 연결 시 결재 요청·승인·반려 푸시
  - 프론트는 우상단 토스트로 표시, 자동 재연결
- **다중 통화/환율**: KRW(base), USD, JPY 시드 + `/api/currencies/convert`
  - 헤더 통화 선택기 → 모든 단가/금액이 선택 통화로 표시
  - admin이 환율을 직접 입력/갱신 (날짜별)
- **재고 LOT/Serial 추적**: 품목별 LOT (lot_number, 수량, 유효기간, 공급사, 시리얼)
  - 입출고 시 lot_id 지정하면 lot 수량도 함께 조정
  - 재고 페이지의 'LOT' 버튼으로 추가/조회
- **예약 보고서**: APScheduler로 5분마다 due 체크 → PDF 생성 → 이메일 발송
  - 빈도: daily / weekly / monthly, 수신자 콤마 구분
  - "지금 실행" 버튼으로 즉시 발송 가능
  - 생성된 PDF는 `uploads/`에 저장
- **RLS (Record-level access)**: 영업 모듈에 적용 (`Customer.owner_id`, `SalesOrder.owner_id`)
  - admin/manager는 전체 조회, staff/viewer는 자신이 만든 레코드만
  - `app/core/rls.py`의 `scope_to_owner(query, model, user, module)` 헬퍼로 다른 모듈에도 동일 패턴 적용 가능
- **멀티테넌시**: `Tenant` + `UserTenant` + `X-Tenant-ID` 헤더 기반 스코핑
  - 헤더 사이드바에 테넌트 선택기 (웰그린 코리아 / 라들러 / 트루웰 물류)
  - 영업 모듈(고객/주문)은 자동으로 테넌트별 격리
- **커스텀 필드 (EAV)**: 모든 모듈 레코드에 임의 속성 추가 가능
  - 타입: text / number / date / boolean / select(옵션 리스트)
  - admin이 `/admin/custom-fields`에서 정의, 모듈 페이지에서 값 입력
- **백업 / 복원 / Excel 임포트** (`/admin/data`)
  - 모든 테이블 → 단일 JSON 다운로드 (`GET /api/admin/backup`)
  - JSON 업로드로 복원 (`truncate_first` 옵션으로 기존 데이터 wipe)
  - .xlsx 일괄 등록: 품목 / 고객 / 직원 (한글·영문 헤더 모두 지원)
- **GraphQL 게이트웨이**: `/graphql` (POST) — `employees`, `items`, `customers`, `orders` 쿼리
  - JWT Authorization 헤더 그대로 사용, 외부 파트너용 단일 엔드포인트
- **모바일 PWA**: `/manifest.webmanifest` + Service Worker
  - 브랜드 그린 테마, 홈 화면 추가 가능, 오프라인 셸 캐싱
- **WellGreen 브랜딩**: Tailwind `brand` 팔레트 (green-600 계열), 🌱 로고
  - 시드 데이터: 라들러/필스너/바이젠/콜라/스파클링워터/감자칩 등 F&B 제품
  - 테넌트: 웰그린 코리아 / 웰그린 라들러 / 트루웰 물류
  - 고객: 세븐일레븐, GS25, CU, 이마트24, 한강 도매상사

## 디렉토리 구조

```
ERP-system/
├── backend/
│   ├── app/
│   │   ├── core/          # config, db, auth, security, base_model
│   │   ├── modules/
│   │   │   ├── auth/      # 사용자, 로그인
│   │   │   ├── hr/
│   │   │   ├── finance/
│   │   │   ├── inventory/
│   │   │   └── sales/
│   │   └── main.py        # 모듈 자동 등록
│   ├── scripts/seed.py    # 초기 데이터 시드
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/               # Next.js App Router
│   │   ├── login/
│   │   ├── hr/ finance/ inventory/ sales/
│   │   ├── layout.tsx
│   │   └── page.tsx       # 대시보드
│   ├── components/        # Sidebar, AuthGate, DataTable, AppShell
│   ├── lib/               # api 클라이언트, 모듈 레지스트리
│   └── Dockerfile
└── docker-compose.yml
```

## 빠른 시작

### Docker (권장)

```bash
docker compose up --build
```

- Backend: http://localhost:8000 (Swagger: `/docs`)
- Frontend: http://localhost:3000
- Postgres: localhost:5432 (erp / erp)
- 기본 계정 (모두 `@wellgreen.com`):
  - `admin@wellgreen.com` / `admin1234` (admin)
  - `manager@wellgreen.com` / `password1234` (manager)
  - `staff@wellgreen.com` / `password1234` (staff)
  - `viewer@wellgreen.com` / `password1234` (viewer)

### 로컬 실행

**Backend (SQLite, 빠른 시작)**
```bash
cd backend
pip install -r requirements.txt
python scripts/seed.py            # 자동 create_all + 초기 데이터
uvicorn app.main:app --reload
```

**Backend (Postgres + Alembic, 운영 권장)**
```bash
cd backend
export DATABASE_URL=postgresql+psycopg2://erp:erp@localhost:5432/erp
export AUTO_CREATE_TABLES=0
alembic upgrade head               # 마이그레이션 적용
python scripts/seed.py             # 초기 데이터
uvicorn app.main:app --reload
```

**스키마 변경 시 새 마이그레이션 생성**
```bash
alembic revision --autogenerate -m "add new column"
alembic upgrade head
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

## 새 모듈 추가하기

이 프로젝트는 **모듈식 구조**로 설계되어, 새 모듈을 일관된 패턴으로 추가할 수 있습니다.

### 1) 백엔드

`backend/app/modules/<new_module>/` 폴더에 다음 파일 생성:

```
<new_module>/
├── __init__.py
├── models.py       # SQLAlchemy 모델 (BaseEntity 상속)
├── schemas.py      # Pydantic 스키마
├── service.py      # 비즈니스 로직
└── router.py       # APIRouter (prefix=/api/<new_module>)
```

`backend/app/main.py` 의 `MODULES` 리스트에 모듈 키 추가:

```python
MODULES = ["auth", "hr", "finance", "inventory", "sales", "<new_module>"]
```

### 2) 프론트엔드

`frontend/app/<new_module>/page.tsx` 생성 (HR/재고 페이지 참고).

`frontend/lib/modules.ts` 의 `MODULES` 배열에 추가:

```ts
{ key: "<new_module>", label: "...", href: "/<new_module>" }
```

이게 끝입니다. 사이드바, 라우트, API 등록이 모두 자동으로 처리됩니다.

## 모듈 간 연동 패턴

다른 모듈의 데이터가 필요하면 **service 함수만 호출** 하세요. DB 테이블을 직접 join하지 마세요.

예: `sales` 모듈이 주문 확정 시 `inventory` 모듈의 `adjust_stock_for_sale()` 를 호출 (`backend/app/modules/sales/service.py` 참조).

이 규칙을 지키면 추후 마이크로서비스 분리도 용이합니다.

## API 문서

Backend가 실행 중일 때 자동 생성된 OpenAPI 문서:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## RBAC 권한

`User.role` 필드로 4단계 역할 (admin > manager > staff > viewer)을 관리합니다.

| 작업 | 필요 역할 |
|---|---|
| 모든 모듈 조회 | staff 이상 |
| 입출고, 고객/주문 생성 | staff 이상 |
| 직원 추가/수정, 전표 작성, 주문 확정 | manager 이상 |
| 마스터 데이터 (계정과목, 부서, 품목) | admin |

엔드포인트에 권한을 걸려면:

```python
from app.core.auth import require_role

@router.post("/x", dependencies=[Depends(require_role("manager"))])
def create_x(...): ...
```

## 추후 확장 아이디어

- 구매(Purchase), 제조(Production), 프로젝트(Project), 자산(Asset) 모듈
- 모바일 앱 (동일 JWT API 재사용)
- 외부 시스템 연동 (Webhook, OAuth2 client credentials)
- 감사 로그(Audit log), 다국어(i18n)
