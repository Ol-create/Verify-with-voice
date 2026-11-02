import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.db import get_db
from app.models import AdminUser, ApiCredential
from app.routes.admin.schemas import CredentialOut
from app.services.credentials import revoke_credential

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/{credential_id}/revoke", response_model=CredentialOut)
async def revoke(
    credential_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Revoke an API key. It stops working at once, including tokens already issued with it.
    Revoking an already-revoked key is a no-op and keeps the original revoke time.
    """
    credential = db.get(ApiCredential, credential_id)
    if not credential:
        raise HTTPException(status_code=404, detail="API key not found")
    was_active = credential.is_active
    revoke_credential(credential)
    db.commit()
    if was_active:
        logger.info("Admin %s revoked key %s (%s) of company %s",
                    admin.email, credential.id, credential.key_prefix, credential.company_id)
    return credential
