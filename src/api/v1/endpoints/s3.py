from fastapi import APIRouter, Query, UploadFile
from typing import Union
from services.location_service import get_state_from_location, get_distance_km

router = APIRouter()


@router.post("/upload")
def upload_file(file: UploadFile):
    """
    Upload a file to S3 and return its URL.
    """
    from services.s3.s3_service import S3Service

    s3_service = S3Service()
    result = s3_service.upload_file(file, key=file.filename)
    return result

@router.delete("/delete")
def delete_file(key: str = Query(..., description="S3 key of the file to delete")):
    """
    Delete a file from S3 using its key.
    """
    from services.s3.s3_service import S3Service

    s3_service = S3Service()
    success = s3_service.delete_file(key)
    return {"success": success}