# ERP System (PoC)

사내 PoC / 내부 도구용 모듈식 ERP 시스템입니다.

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

### 추가 기능
- **i18n**: 한국어/영어 토글 (사이드바 상단 버튼)
- **대시보드**: 6개 KPI + 월별 매출 / 부서별 직원 / 재고가치 차트 (의존성 없는 inline SVG)
- **사용자 관리** (`/admin/users`): admin이 사용자 추가/삭제/역할 변경
- **감사 로그** (`/admin/audit`): 누가/언제/어떤 API를 호출했는지 조회

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
- 기본 계정 (모두 비밀번호 `password1234`, admin만 `admin1234`):
  - `admin@example.com` (admin) — 시스템/마스터 데이터 모두 가능
  - `manager@example.com` (manager) — 직원 추가, 전표 작성, 주문 확정
  - `staff@example.com` (staff) — 입출고, 고객/주문 생성
  - `viewer@example.com` (viewer) — 읽기 전용

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
