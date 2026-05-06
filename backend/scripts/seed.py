"""Seed initial admin user and a few sample records for PoC."""
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.main import create_app  # ensures tables created
from app.modules.auth.models import User
from app.modules.finance.models import Account, AccountType
from app.modules.hr.models import Department, Employee
from app.modules.inventory.models import Item

create_app()


def run() -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "admin@example.com").first():
            db.add(
                User(
                    email="admin@example.com",
                    full_name="Admin",
                    hashed_password=hash_password("admin1234"),
                    is_admin=True,
                )
            )

        if not db.query(Department).first():
            db.add_all(
                [
                    Department(name="Engineering"),
                    Department(name="Sales"),
                    Department(name="HR"),
                ]
            )

        if not db.query(Account).first():
            db.add_all(
                [
                    Account(code="1000", name="Cash", type=AccountType.asset),
                    Account(code="1100", name="Accounts Receivable", type=AccountType.asset),
                    Account(code="2000", name="Accounts Payable", type=AccountType.liability),
                    Account(code="4000", name="Sales Revenue", type=AccountType.revenue),
                    Account(code="5000", name="Cost of Goods Sold", type=AccountType.expense),
                ]
            )

        if not db.query(Item).first():
            db.add_all(
                [
                    Item(sku="SKU-001", name="Widget A", unit="EA", unit_price=10000, stock_qty=100),
                    Item(sku="SKU-002", name="Widget B", unit="EA", unit_price=20000, stock_qty=50),
                ]
            )

        db.commit()
        print("Seed completed.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
