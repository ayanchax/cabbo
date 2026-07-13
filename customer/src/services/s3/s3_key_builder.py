import uuid


class S3KeyBuilder:


    @staticmethod
    def customer_avatar(customer_id: str, extension: str) -> str:
        return f"customers/profile/{customer_id}/images/avatar/{uuid.uuid4().hex}.{extension}"

    @staticmethod
    def driver_avatar(driver_id: str, extension: str) -> str:
        return f"drivers/profile/{driver_id}/images/avatar/{uuid.uuid4().hex}.{extension}"

    @staticmethod
    def driver_kyc(driver_id: str, kyc_filename:str, category: str) -> str:
        return f"drivers/profile/{driver_id}/kyc/{category}/{kyc_filename}"