def mask_phone(value: str | None) -> str:
    if not value:
        return "unknown"
    visible = value[-4:] if len(value) >= 4 else value
    return f"***{visible}"


def mask_email(value: str | None) -> str:
    if not value or "@" not in value:
        return "unknown"
    local, domain = value.split("@", 1)
    prefix = local[:2] if len(local) >= 2 else local[:1]
    return f"{prefix}***@{domain}"


def summarize_provider_entity(entity: dict | None) -> dict:
    if not entity:
        return {}
    return {
        "id": entity.get("id"),
        "entity": entity.get("entity"),
        "status": entity.get("status"),
        "amount": entity.get("amount"),
        "currency": entity.get("currency"),
        "receipt": entity.get("receipt"),
    }
