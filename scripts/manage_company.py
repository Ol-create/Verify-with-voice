"""
Create a company or rotate its API credentials.

    python -m scripts.manage_company create "Acme Bank"
    python -m scripts.manage_company rotate "Acme Bank"

The API key and secret are printed once. Only their hashes are stored, so they
can't be shown again: if they're lost, rotate them.
"""
import argparse
import sys

from app.db import SessionLocal
from app.models import Company
from app.utils.security import display_prefix, generate_api_credentials, hash_credential


def _set_credentials(company: Company) -> tuple[str, str]:
    api_key, api_secret = generate_api_credentials()
    company.api_key_hash = hash_credential(api_key)
    company.api_key_prefix = display_prefix(api_key)
    company.api_secret_hash = hash_credential(api_secret)
    return api_key, api_secret


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["create", "rotate"])
    parser.add_argument("name", help="company name")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.name == args.name).first()
        if args.action == "create":
            if company:
                print(f"Company '{args.name}' already exists. Use 'rotate' for new credentials.", file=sys.stderr)
                return 1
            company = Company(name=args.name)
            db.add(company)
        elif not company:
            print(f"Company '{args.name}' not found.", file=sys.stderr)
            return 1

        api_key, api_secret = _set_credentials(company)
        db.commit()

        print(f"Company:    {company.name} ({company.id})")
        print(f"API key:    {api_key}")
        print(f"API secret: {api_secret}")
        print("Store these now. They can't be shown again.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
