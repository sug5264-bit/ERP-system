"""Seed initial data for the WellGreen ERP PoC.

Sample data is themed after a beverage / F&B distribution company:
음료, 라들러, 수입맥주, 스낵 + 편의점/유통사 고객.
"""
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.main import create_app  # ensures tables created
from app.modules.auth.models import Role, User
from app.modules.currencies.models import Currency, ExchangeRate
from app.modules.finance.models import Account, AccountType
from app.modules.hr.models import Department, Employee
from app.modules.inventory.models import Item
from app.modules.sales.models import Customer
from app.modules.tenants.models import Tenant, UserTenant

create_app()


def run() -> None:
    db = SessionLocal()
    try:
        # Users -----------------------------------------------------------------
        if not settings.seed_demo_users:
            print(
                "seed_demo_users=false; skipping demo accounts.\n"
                "→ 운영 admin은 'python -m scripts.create_admin --email <ID> --name <이름>' 로 생성하세요."
            )
        else:
            if settings.is_production:
                raise RuntimeError(
                    "운영 환경에서 데모 계정 시드를 거부합니다.\n"
                    "SEED_DEMO_USERS=false 설정 후, 운영 admin은\n"
                    "'python -m scripts.create_admin' 으로 생성하세요."
                )
            default_users = [
                ("admin@wellgreen.com", "관리자", Role.admin, "admin1234"),
                ("manager@wellgreen.com", "김영업", Role.manager, "password1234"),
                ("staff@wellgreen.com", "이실무", Role.staff, "password1234"),
                ("viewer@wellgreen.com", "박조회", Role.viewer, "password1234"),
            ]
            for email, name, role, pw in default_users:
                if not db.query(User).filter(User.email == email).first():
                    db.add(
                        User(
                            email=email,
                            full_name=name,
                            hashed_password=hash_password(pw),
                            role=role,
                        )
                    )
            db.flush()

        # 데모 비즈니스 데이터 (거래처/품목/계정과목) — production 보호용 분리 플래그.
        if not settings.seed_demo_data:
            print(
                "seed_demo_data=false; skipping demo tenants/customers/items/accounts.\n"
                "→ 운영 데이터는 /admin 메뉴에서 직접 등록하거나 Excel import 사용."
            )
            db.commit()
            print("Seed completed (users only or skipped entirely).")
            return

        if settings.is_production:
            raise RuntimeError(
                "운영 환경에서 데모 비즈니스 데이터 시드를 거부합니다.\n"
                "SEED_DEMO_DATA=false 설정 후 다시 실행하세요."
            )

        # Tenants (multi-tenancy) ----------------------------------------------
        if not db.query(Tenant).first():
            t1 = Tenant(code="WG-KR", name="웰그린 코리아", description="국내 음료/주류 유통")
            t2 = Tenant(code="WG-RAD", name="웰그린 라들러", description="라들러 음료 제조 자회사")
            t3 = Tenant(code="WG-LOG", name="트루웰 물류", description="종합 물류 자회사")
            db.add_all([t1, t2, t3])
            db.flush()
            admin = db.query(User).filter(User.email == "admin@wellgreen.com").first()
            if admin:
                for t in (t1, t2, t3):
                    db.add(UserTenant(user_id=admin.id, tenant_id=t.id, is_default=(t is t1)))

        # Departments -----------------------------------------------------------
        if not db.query(Department).first():
            db.add_all(
                [
                    Department(name="영업본부"),
                    Department(name="물류센터"),
                    Department(name="구매팀"),
                    Department(name="제조본부"),
                    Department(name="경영지원"),
                ]
            )

        # Employees -------------------------------------------------------------
        if not db.query(Employee).first():
            db.add_all(
                [
                    Employee(employee_no="WG-0001", full_name="김지훈", email="kim.jh@wellgreen.com", position="영업팀장", salary=55000000),
                    Employee(employee_no="WG-0002", full_name="이서연", email="lee.sy@wellgreen.com", position="대리", salary=42000000),
                    Employee(employee_no="WG-0003", full_name="박도현", email="park.dh@wellgreen.com", position="물류 매니저", salary=48000000),
                    Employee(employee_no="WG-0004", full_name="최유진", email="choi.yj@wellgreen.com", position="구매 담당", salary=40000000),
                ]
            )

        # Finance accounts (편의점·유통 회계 기반) -------------------------------
        if not db.query(Account).first():
            db.add_all(
                [
                    Account(code="1000", name="현금", type=AccountType.asset),
                    Account(code="1100", name="외상매출금", type=AccountType.asset),
                    Account(code="1200", name="상품(음료)", type=AccountType.asset),
                    Account(code="2000", name="외상매입금", type=AccountType.liability),
                    Account(code="2100", name="주류세 미지급금", type=AccountType.liability),
                    Account(code="3000", name="자본금", type=AccountType.equity),
                    Account(code="4000", name="음료 매출", type=AccountType.revenue),
                    Account(code="4100", name="주류 매출", type=AccountType.revenue),
                    Account(code="4200", name="스낵 매출", type=AccountType.revenue),
                    Account(code="5000", name="매출원가", type=AccountType.expense),
                    Account(code="5100", name="물류운송비", type=AccountType.expense),
                ]
            )

        # Inventory items (음료/주류/스낵) --------------------------------------
        if not db.query(Item).first():
            db.add_all(
                [
                    Item(sku="WG-RAD-LE-330", name="웰그린 라들러 레몬 330ml", unit="CAN", unit_price=2500, stock_qty=2400),
                    Item(sku="WG-RAD-GR-330", name="웰그린 라들러 자몽 330ml", unit="CAN", unit_price=2500, stock_qty=1800),
                    Item(sku="WG-RAD-AP-330", name="웰그린 라들러 사과 330ml", unit="CAN", unit_price=2500, stock_qty=1200),
                    Item(sku="IMP-PILS-500", name="유럽 필스너 맥주 500ml", unit="BTL", unit_price=4800, stock_qty=900),
                    Item(sku="IMP-WIES-500", name="독일 바이젠 맥주 500ml", unit="BTL", unit_price=5200, stock_qty=600),
                    Item(sku="WG-COLA-355", name="웰그린 콜라 355ml", unit="CAN", unit_price=1500, stock_qty=3000),
                    Item(sku="WG-SODA-500", name="웰그린 스파클링 워터 500ml", unit="BTL", unit_price=1300, stock_qty=2200),
                    Item(sku="EU-CHIP-150", name="감자칩 오리지널 150g", unit="EA", unit_price=2800, stock_qty=800),
                    Item(sku="EU-CHOC-100", name="유럽 다크초콜릿 100g", unit="EA", unit_price=3200, stock_qty=400),
                ]
            )

        # Customers (편의점·도매점) --------------------------------------------
        if not db.query(Customer).first():
            tenant_kr = db.query(Tenant).filter(Tenant.code == "WG-KR").first()
            db.add_all(
                [
                    Customer(name="세븐일레븐 본사", email="purchase@7eleven.co.kr", company="코리아세븐", phone="02-1234-5678", tenant_id=tenant_kr.id if tenant_kr else None),
                    Customer(name="GS25 구매팀", email="buyer@gs25.co.kr", company="GS리테일", phone="02-2345-6789", tenant_id=tenant_kr.id if tenant_kr else None),
                    Customer(name="CU 본사", email="purchase@bgfretail.com", company="BGF리테일", phone="02-3456-7890", tenant_id=tenant_kr.id if tenant_kr else None),
                    Customer(name="이마트 24", email="b2b@emart24.co.kr", company="이마트24", phone="02-4567-8901", tenant_id=tenant_kr.id if tenant_kr else None),
                    Customer(name="한강 도매상사", email="hangang@whole.kr", company="한강유통", phone="02-5678-9012", tenant_id=tenant_kr.id if tenant_kr else None),
                ]
            )

        # Currencies -----------------------------------------------------------
        if not db.query(Currency).first():
            krw = Currency(code="KRW", name="대한민국 원", symbol="₩", is_base=True)
            usd = Currency(code="USD", name="미국 달러", symbol="$")
            eur = Currency(code="EUR", name="유로", symbol="€")
            jpy = Currency(code="JPY", name="일본 엔", symbol="¥")
            db.add_all([krw, usd, eur, jpy])
            db.flush()
            db.add_all(
                [
                    ExchangeRate(currency_id=usd.id, rate_to_base=1350),
                    ExchangeRate(currency_id=eur.id, rate_to_base=1450),
                    ExchangeRate(currency_id=jpy.id, rate_to_base=9.2),
                ]
            )

        db.commit()
        print("Seed completed.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
