def preserve_temp_trip(metadata) -> bool:
    """Keep payment-linked booking details until payment reconciliation resolves them.

    A missing checkout callback does not establish that a payment failed.
    Keep verified/payment-ID records too, including legacy provider metadata.
    """
    if not isinstance(metadata, dict):
        return bool(metadata)  # Unknown metadata must not silently lose payment evidence.
    return metadata.get("payment_verified") is True or any(
        value and (key.endswith("_order_id") or key.endswith("_payment_id"))
        for key, value in metadata.items()
    )
