import os
from pathlib import Path
from typing import Union
from core.exceptions import CabboException
from core.config import settings

ALLOWED_IMAGE_EXTENSIONS = ["image/png"]


def save_customer_profile_picture(customer_id: str, file, max_size_mb: int = 2) -> str:
    """
    Save a profile picture for a customer. Returns the relative URL.
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
    image_dir = os.path.join(settings.SHARE_PATH, "images", "customers")
    os.makedirs(image_dir, exist_ok=True)
    image_path = os.path.join(image_dir, f"{customer_id}.png")
    with open(image_path, "wb") as f:
        f.write(contents)
    # Return the relative URL for static serving
    return f"/images/customers/{customer_id}.png"


def remove_customer_profile_picture(customer_id: str) -> bool:
    """
    Remove the profile picture file for a customer if it exists.
    Returns True if removed, False if file did not exist.
    Raises CabboException on error.
    """
    image_path = os.path.join(
        settings.SHARE_PATH, "images", "customers", f"{customer_id}.png"
    )
    if os.path.exists(image_path):
        try:
            os.remove(image_path)
            return True
        except Exception as e:
            raise CabboException(
                f"Failed to remove profile picture: {str(e)}", status_code=500
            )
    return False


def save_driver_profile_picture(driver_id: str, file, max_size_mb: int = 2) -> str:
    """
    Save a profile picture for a driver. Returns the relative URL.
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
    image_dir = os.path.join(settings.SHARE_PATH, "images", "drivers")
    os.makedirs(image_dir, exist_ok=True)
    image_path = os.path.join(image_dir, f"{driver_id}.png")
    with open(image_path, "wb") as f:
        f.write(contents)
    # Return the relative URL for static serving
    return f"/images/drivers/{driver_id}.png"


def remove_driver_profile_picture(driver_id: str) -> bool:
    """
    Remove the profile picture file for a driver if it exists.
    Returns True if removed, False if file did not exist.
    Raises CabboException on error.
    """
    image_path = os.path.join(
        settings.SHARE_PATH, "images", "drivers", f"{driver_id}.png"
    )
    if os.path.exists(image_path):
        try:
            os.remove(image_path)
            return True
        except Exception as e:
            raise CabboException(
                f"Failed to remove profile picture: {str(e)}", status_code=500
            )
    return False

def save_file(path:Union[Path, str], content: str=""):
    """
    Save a file to the specified path.
    """
    try:
        with open(path, "w") as f:
            f.write(content)
    except Exception as e:
        return False
    return True

def is_file_exists(path:Union[Path, str]) -> bool:
    """
    Check if a file exists at the specified path.
    """
    return os.path.exists(path)