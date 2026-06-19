"""운영용 첫 관리자(super-admin) 계정 생성 스크립트.

배포 직후 데모 계정 없이 admin 1명을 안전하게 만들기 위함.

사용법:
    # 대화형 (권장) — 비밀번호는 화면에 안 보임
    python -m scripts.create_admin --email ops@yourcompany.kr --name "운영 관리자"

    # 비대화형 (CI/CD 자동화) — 비밀번호를 환경변수로
    ADMIN_PASSWORD='강력한비밀번호!' python -m scripts.create_admin \
        --email ops@yourcompany.kr --name "운영 관리자" --password-env ADMIN_PASSWORD

    # 비밀번호 자동 생성 (24자 안전 난수)
    python -m scripts.create_admin --email ops@yourcompany.kr --name "운영" --generate-password

    # 기존 admin의 비밀번호 재설정 (분실 시)
    python -m scripts.create_admin --email ops@yourcompany.kr --name "운영" --reset

보안 안전장치:
- 비밀번호 강도 검증 (≥12자, 대문자/소문자/숫자/특수문자 각 1+)
- CLI 인자로 직접 비밀번호 전달 금지 (히스토리/프로세스 목록 노출 위험)
- ENVIRONMENT=production이고 SEED_DEMO_USERS=true면 경고
- 중복 admin 생성 거부 (--reset 명시 시만 갱신)
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import secrets
import string
import sys


def _strong_password(pw: str) -> tuple[bool, str]:
    """비밀번호 강도 검증. (ok, reason)."""
    if len(pw) < 12:
        return False, "비밀번호는 12자 이상이어야 합니다."
    if not re.search(r"[A-Z]", pw):
        return False, "대문자 1자 이상 포함하세요."
    if not re.search(r"[a-z]", pw):
        return False, "소문자 1자 이상 포함하세요."
    if not re.search(r"\d", pw):
        return False, "숫자 1자 이상 포함하세요."
    if not re.search(r"[^A-Za-z0-9]", pw):
        return False, "특수문자 1자 이상 포함하세요."
    return True, ""


def _generate_password(length: int = 24) -> str:
    """안전 난수 비밀번호. URL-safe 특수문자만 사용해 셸 escape 불필요."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+?"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        ok, _ = _strong_password(pw)
        if ok:
            return pw


def _prompt_password() -> str:
    pw1 = getpass.getpass("비밀번호: ")
    pw2 = getpass.getpass("비밀번호 확인: ")
    if pw1 != pw2:
        print("[ERROR] 비밀번호 확인이 일치하지 않습니다.", file=sys.stderr)
        sys.exit(2)
    return pw1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="운영 admin 계정 생성")
    p.add_argument("--email", required=True, help="관리자 이메일 (로그인 ID)")
    p.add_argument("--name", required=True, help="관리자 이름")
    p.add_argument(
        "--password-env",
        help="비밀번호를 담은 환경변수명 (CI/CD용). 미지정 시 대화형 prompt.",
    )
    p.add_argument(
        "--generate-password",
        action="store_true",
        help="안전한 비밀번호 자동 생성 후 stdout에 1회 출력 (저장 책임 운영자).",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="이미 존재하는 admin의 비밀번호를 갱신 (없으면 새로 생성).",
    )
    args = p.parse_args(argv)

    # 환경 점검
    os.environ.setdefault("ENVIRONMENT", "production")
    from app.core.config import settings  # noqa: E402

    if settings.is_production and settings.seed_demo_users:
        print(
            "[WARN] production 환경인데 SEED_DEMO_USERS=true 입니다. "
            "데모 계정(admin@wellgreen.com)이 같이 시드되었을 수 있습니다. "
            "SEED_DEMO_USERS=false 로 두고 데모 계정을 삭제하세요.",
            file=sys.stderr,
        )

    # 비밀번호 확보
    if args.generate_password:
        pw = _generate_password()
        print("\n[GENERATED PASSWORD — 저장 후 즉시 화면에서 지우세요]")
        print(f"  {pw}\n")
    elif args.password_env:
        pw = os.environ.get(args.password_env, "")
        if not pw:
            print(
                f"[ERROR] 환경변수 {args.password_env} 가 비어있습니다.",
                file=sys.stderr,
            )
            return 2
    else:
        pw = _prompt_password()

    ok, reason = _strong_password(pw)
    if not ok:
        print(f"[ERROR] 비밀번호 강도 부족: {reason}", file=sys.stderr)
        return 2

    # DB 작업 — 모든 모델 import 후 Session 열기.
    # 운영에서는 alembic upgrade head 가 선행됐다고 가정하지만,
    # 미리 import만 해두면 부작용 없음.
    from app.core.db import Base, SessionLocal, engine  # noqa: E402
    from app.core.security import hash_password  # noqa: E402
    from app.main import MODULES  # noqa: E402
    from importlib import import_module

    for m in MODULES:
        import_module(f"app.modules.{m}.models")

    from app.modules.auth.models import Role, User  # noqa: E402

    # 개발/PoC 환경 (auto_create_tables=true) — 첫 실행 시 테이블 보장.
    # 운영(production)에서는 alembic 이 이미 만들어두므로 idempotent.
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing and not args.reset:
            print(
                f"[ERROR] 이미 존재하는 계정: {args.email}\n"
                f"        비밀번호를 갱신하려면 --reset 옵션을 추가하세요.",
                file=sys.stderr,
            )
            return 1

        if existing:
            existing.hashed_password = hash_password(pw)
            existing.role = Role.admin
            existing.full_name = args.name
            db.commit()
            print(f"[OK] {args.email} (admin) 비밀번호 갱신 완료.")
        else:
            user = User(
                email=args.email,
                full_name=args.name,
                hashed_password=hash_password(pw),
                role=Role.admin,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"[OK] {args.email} (admin) 계정 생성 완료. id={user.id}")

        # 데모 admin 계정이 남아있으면 경고
        demo = db.query(User).filter(User.email == "admin@wellgreen.com").first()
        if demo:
            print(
                "\n[WARN] 데모 계정 admin@wellgreen.com 이 아직 존재합니다.\n"
                "       운영 전 반드시 삭제하거나 비밀번호를 변경하세요.\n"
                "       (UI: /admin/users 페이지에서 삭제 가능)",
                file=sys.stderr,
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
