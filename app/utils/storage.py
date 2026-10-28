import mimetypes
import uuid

import boto3

from app.config import settings

# Pull from your Pydantic settings (already wired to .env)
AWS_ACCESS_KEY = settings.AWS_ACCESS_KEY_ID
AWS_SECRET_KEY = settings.AWS_SECRET_ACCESS_KEY
S3_BUCKET = settings.S3_BUCKET_NAME
S3_REGION = settings.AWS_REGION

s3 = boto3.client(
    "s3",
    region_name=S3_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)


def upload_audio(file_path: str, key_prefix: str, original_filename: str) -> str:
    """
    Upload audio file from a local path to S3 under `key_prefix` and return its s3:// URI.
    The object key is `{key_prefix}/{uuid}-{original_filename}`.
    """
    file_key = f"{key_prefix.strip('/')}/{uuid.uuid4()}-{original_filename}"
    content_type = mimetypes.guess_type(original_filename)[0] or "application/octet-stream"

    s3.upload_file(
        file_path,
        S3_BUCKET,
        file_key,
        ExtraArgs={"ContentType": content_type},
    )

    return f"s3://{S3_BUCKET}/{file_key}"
