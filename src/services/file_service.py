import os
from pathlib import Path
import re
from typing import Union

from fastapi import UploadFile
from core.exceptions import CabboException
from core.config import settings
from models.common import S3ObjectInfo
from models.documents.kyc_document_enum import KYCDocumentTypeEnum
from services.s3.s3_key_builder import S3KeyBuilder
from services.s3.s3_service import S3Service

ALLOWED_IMAGE_EXTENSIONS = ["image/png"]


def save_customer_profile_picture(customer_id: str, file:UploadFile, max_size_mb: int = 2) -> S3ObjectInfo:
    """
    Save a profile picture for a customer. Returns the S3ImageInfo with key and URL.
    Raises CabboException on error.
    """
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_EXTENSIONS:
        raise CabboException(
            f"Only these image types are allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}.",
            status_code=400,
        )
    # Validate file size
    contents = file.file.read()
    if len(contents) > max_size_mb * 1024 * 1024:
        raise CabboException(
            f"File size exceeds {max_size_mb}MB limit.", status_code=400
        )
    # Save file

    #Extract extension
    ext = get_file_extension(file.filename)

    # Generate S3 key
    key = S3KeyBuilder.customer_avatar(customer_id, ext)

    # Upload to S3
    s3_service = S3Service()
    s3_result = s3_service.upload_file(file, key)
    return s3_result



def remove_customer_profile_picture(key: str) -> bool:
    """
    Remove the profile picture file for a customer if it exists.
    Returns True if removed, False if file did not exist.
    Raises CabboException on error.
    """
    s3_service = S3Service()
    return s3_service.delete_file(key)


def save_driver_profile_picture(driver_id: str, file:UploadFile, max_size_mb: int = 2) -> S3ObjectInfo:
    """
    Save a profile picture for a driver. Returns the S3ImageInfo with key and URL.
    Raises CabboException on error.
    """
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_EXTENSIONS:
        raise CabboException(
            f"Only these image types are allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}.",
            status_code=400,
        )
    # Validate file size
    contents = file.file.read()
    if len(contents) > max_size_mb * 1024 * 1024:
        raise CabboException(
            f"File size exceeds {max_size_mb}MB limit.", status_code=400
        )
   
    #Extract extension
    ext = get_file_extension(file.filename)

    # Generate S3 key
    key = S3KeyBuilder.driver_avatar(driver_id, ext)

    # Upload to S3
    s3_service = S3Service()
    s3_result = s3_service.upload_file(file, key)
    return s3_result



def remove_driver_profile_picture(key: str) -> bool:
    """
    Remove the profile picture file for a driver if it exists.
    Returns True if removed, False if file did not exist.
    Raises CabboException on error.
    """
    s3_service = S3Service()
    return s3_service.delete_file(key)


def save_driver_kyc_document_file(
    driver_id: str, file: UploadFile, doc_type: KYCDocumentTypeEnum
) -> S3ObjectInfo:
    """
    Save a KYC document file for a driver. Returns the S3ImageInfo with key and URL.
    Raises CabboException on error.
    """
    # Generate S3 key
    key = S3KeyBuilder.driver_kyc(driver_id, sanitize_filename(file.filename), doc_type.value.lower())
    # Upload to S3
    s3_service = S3Service()
    s3_result = s3_service.upload_file(file, key)
    return s3_result

def remove_driver_kyc_document_file(key: str) -> bool:
    """
    Remove a KYC document file for a driver if it exists.
    Returns True if removed, False if file did not exist.
    Raises CabboException on error.
    """
    s3_service = S3Service()
    return s3_service.delete_file(key)

def save_file(path: Union[Path, str], content: str = ""):
    """
    Save a file to the specified path.
    """
    try:
        with open(path, "w") as f:
            f.write(content)
    except Exception as e:
        return False
    return True


def is_file_exists(path: Union[Path, str]) -> bool:
    """
    Check if a file exists at the specified path.
    """
    return os.path.exists(path)


def create_directory(path: Union[Path, str]):
    """
    Create a directory at the specified path if it doesn't exist.
    """
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        print(f"Failed to create directory {path}: {str(e)}")
        return False


def create_directories(paths: list[Union[Path, str]]):
    """
    Create multiple directories from a list of paths.
    """
    for path in paths:
        if not create_directory(path):
            return False
    return True


def copy_file(
    src: Union[Path, str], dest: Union[Path, str], overwrite: bool = True
) -> bool:
    """
    Copy a file from src to dest.
    """
    try:
        from shutil import copy2

        if not os.path.exists(src):
            print(f"Source file {src} does not exist.")
            return False
        if not os.path.exists(os.path.dirname(dest)):
            create_directory(os.path.dirname(dest))
        # If file exists at dest, it will be overwritten only if overwrite is True
        if not overwrite and os.path.exists(dest):
            print(
                f"Destination file {dest} already exists and overwrite is set to False."
            )
            return False

        copy2(src, dest)
        return True
    except Exception as e:
        print(f"Failed to copy file from {src} to {dest}: {str(e)}")
        return False


def get_file_extension(filename: Union[Path, str]) -> str:
    if isinstance(filename, Path):
        extension = filename.suffix
        return extension[1:].lower() if extension else ""

    if not filename or "." not in filename:
        raise ValueError("Invalid file name")
    return filename.split(".")[-1].lower()


def sanitize_filename(filename: str) -> str:
    filename = filename.lower()
    filename = filename.replace(" ", "_")
    filename = re.sub(r"[^a-z0-9._-]", "", filename)
    return filename
