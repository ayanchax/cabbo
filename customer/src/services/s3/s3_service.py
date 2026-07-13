import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile
from customer_api.src.core.config import settings
from customer_api.src.models.common import S3ObjectInfo
import logging
log = logging.getLogger(__name__)



class S3Service:

    def __init__(self):
        self.client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=settings.AWS_REGION,
        )
        self.bucket = settings.S3_BUCKET
        self.base_url = settings.S3_BASE_URL

    def upload_file(self, file: UploadFile, key: str) -> S3ObjectInfo:
        try:
            file.file.seek(0)

            self.client.upload_fileobj(
                file.file,
                self.bucket,
                key,
                ExtraArgs={"ContentType": file.content_type},
            )
            log.info(f"File uploaded to S3 bucket: {self.bucket} with key: {key}")
            return S3ObjectInfo(key=key, url=f"{self.base_url}/{key}")

        except (BotoCoreError, ClientError) as e:
            log.error(f"S3 upload failed: {str(e)}")
            return None

    def delete_file(self, key: str) -> bool:
        """
        Delete file from S3.
        """
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)  # Raises if not exists
            self.client.delete_object(Bucket=self.bucket, Key=key)
            log.info(f"File deleted from S3 bucket: {self.bucket} with key: {key}")
            return True

        except (BotoCoreError, ClientError) as e:
            log.error(f"S3 delete failed: {str(e)}")
            return False
