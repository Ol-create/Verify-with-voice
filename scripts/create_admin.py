"""
Create a TrueVoice admin, or change an admin's password or access.

    python -m scripts.create_admin --email you@example.com
    python -m scripts.create_admin --email you@example.com --reset-password
    python -m scripts.create_admin --email you@example.com --deactivate     # or --activate

The password is typed at a hidden prompt, never passed on the command line
(that would leave it in your shell history).
"""
import argparse
import getpass
import sys

from app.db import SessionLocal
from app.models import AdminUser
from app.utils.passwords import hash_password, password_problem


def _ask_password() -> str | None:
    password = getpass.getpass("Password: ")
    problem = password_problem(password)
    if problem:
        print(problem, file=sys.stderr)
        return None
    if getpass.getpass("Repeat password: ") != password:
        print("Passwords don't match.", file=sys.stderr)
        return None
    return password


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--reset-password", action="store_true")
    action.add_argument("--deactivate", action="store_true")
    action.add_argument("--activate", action="store_true")
    args = parser.parse_args(argv)
    email = args.email.strip().lower()

    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.email == email).first()
        creating = not (args.reset_password or args.deactivate or args.activate)

        if creating and admin:
            print(f"Admin {email} already exists. Use --reset-password to change the password.", file=sys.stderr)
            return 1
        if not creating and not admin:
            print(f"Admin {email} not found.", file=sys.stderr)
            return 1

        if args.deactivate or args.activate:
            admin.is_active = args.activate
            db.commit()
            print(f"Admin {email} is now {'active' if admin.is_active else 'deactivated'}.")
            return 0

        password = _ask_password()
        if password is None:
            return 1
        if creating:
            admin = AdminUser(email=email, password_hash=hash_password(password))
            db.add(admin)
        else:
            admin.password_hash = hash_password(password)
        db.commit()
        print(f"Admin {email} {'created' if creating else 'password updated'}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
