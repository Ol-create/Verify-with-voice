"""
Manage companies and their API credentials.

    python -m scripts.manage_company create "Acme Bank" [--email ops@acme.com]
    python -m scripts.manage_company add-key "Acme Bank" [--key-name production]
    python -m scripts.manage_company list-keys "Acme Bank"
    python -m scripts.manage_company revoke-key <credential id>
    python -m scripts.manage_company rotate "Acme Bank"      # revoke every key, issue a new one
    python -m scripts.manage_company suspend "Acme Bank"
    python -m scripts.manage_company activate "Acme Bank"

API keys and secrets are printed once. Only their hashes are stored, so they
can't be shown again: if they're lost, add a new key and revoke the old one.
"""
import argparse
import sys
import uuid

from app.db import SessionLocal
from app.models import COMPANY_ACTIVE, COMPANY_SUSPENDED, ApiCredential, Company
from app.services.companies import CompanyExists, create_company, find_by_name
from app.services.credentials import active_credentials, issue_credential, revoke_credential


def _print_credentials(company: Company, credential: ApiCredential, api_key: str, api_secret: str) -> None:
    print(f"Company:    {company.name} ({company.id})")
    print(f"Key name:   {credential.name} ({credential.id})")
    print(f"API key:    {api_key}")
    print(f"API secret: {api_secret}")
    print("Store these now. They can't be shown again.")


def _fmt(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "-"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)

    create = sub.add_parser("create", help="create a company and its first API key")
    create.add_argument("name", help="company name")
    create.add_argument("--email")

    add_key = sub.add_parser("add-key", help="issue another API key")
    add_key.add_argument("name", help="company name")
    add_key.add_argument("--key-name", default="default", help="label for the key, e.g. production")

    for action, text in [
        ("list-keys", "list API keys"),
        ("rotate", "revoke every API key and issue a new one"),
        ("suspend", "block the company from getting tokens"),
        ("activate", "allow the company to get tokens"),
    ]:
        sub.add_parser(action, help=text).add_argument("name", help="company name")

    revoke = sub.add_parser("revoke-key", help="revoke one API key")
    revoke.add_argument("credential_id", help="id shown by list-keys")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)

    db = SessionLocal()
    try:
        if args.action == "revoke-key":
            try:
                credential = db.get(ApiCredential, uuid.UUID(args.credential_id))
            except ValueError:
                credential = None
            if not credential:
                print(f"API key '{args.credential_id}' not found.", file=sys.stderr)
                return 1
            revoke_credential(credential)
            db.commit()
            print(f"Revoked {credential.key_prefix}... ({credential.name}) for {credential.company.name}.")
            return 0

        if args.action == "create":
            try:
                company, credential, api_key, api_secret = create_company(db, args.name, args.email)
            except CompanyExists:
                print(f"Company '{args.name}' already exists. Use 'add-key' for new credentials.", file=sys.stderr)
                return 1
            db.commit()
            _print_credentials(company, credential, api_key, api_secret)
            return 0

        company = find_by_name(db, args.name)
        if not company:
            print(f"Company '{args.name}' not found.", file=sys.stderr)
            return 1

        if args.action == "add-key":
            credential, api_key, api_secret = issue_credential(db, company, args.key_name)
            db.commit()
            _print_credentials(company, credential, api_key, api_secret)

        elif args.action == "rotate":
            for credential in active_credentials(company):
                revoke_credential(credential)
            credential, api_key, api_secret = issue_credential(db, company)
            db.commit()
            _print_credentials(company, credential, api_key, api_secret)

        elif args.action == "list-keys":
            print(f"{company.name} ({company.status})")
            for c in sorted(company.credentials, key=lambda c: c.created_at):
                state = f"revoked {_fmt(c.revoked_at)}" if c.revoked_at else "active"
                print(f"  {c.id}  {c.key_prefix}...  {c.name:<12} created {_fmt(c.created_at)}  "
                      f"last used {_fmt(c.last_used_at)}  {state}")

        elif args.action in ("suspend", "activate"):
            company.status = COMPANY_SUSPENDED if args.action == "suspend" else COMPANY_ACTIVE
            db.commit()
            print(f"{company.name} is now {company.status}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
