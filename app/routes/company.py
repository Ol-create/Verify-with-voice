# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.orm import Session
# from app.db import get_db
# from app.models import Company
# from app.schemas import CompanySignupRequest
# import secrets
# import uuid

# router = APIRouter()

# @router.post("/companies/signup")
# async def company_signup(payload: CompanySignupRequest, db: Session = Depends(get_db)):
#     # Check if company already exists
#     existing_company = db.query(Company).filter(Company.name == payload.name).first()
#     if existing_company:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=f"Company '{payload.name}' already exists."
#         )

#     # Generate API key/secret with prefix
#     api_key = f"test_tv_{secrets.token_hex(16)}"
#     api_secret = f"test_tv_{secrets.token_hex(32)}"

#     company = Company(
#         id=uuid.uuid4(),
#         name=payload.name,
#         api_key=api_key,
#         api_secret=api_secret,
#     )

#     db.add(company)
#     db.commit()
#     db.refresh(company)

#     return {
#         "id": str(company.id),
#         "name": company.name,
#         "api_key": company.api_key,
#         "api_secret": company.api_secret,
#     }
