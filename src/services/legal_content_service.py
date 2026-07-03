from pathlib import Path
from typing import Any

from core.exceptions import CabboException, GENERIC_EXCEPTION
from models.legal_schema import LegalPageInternal, LegalPageRead, LegalPageSummary


LEGAL_CONTENT_DIR = Path(__file__).resolve().parents[2] / "content" / "legal"


def _parse_frontmatter_value(value: str) -> Any:
    value = value.strip()
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.isdigit():
        return int(value)
    return value


def _read_legal_page(path: Path) -> LegalPageInternal:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise CabboException(
            f"Legal page {path.name} is missing frontmatter.",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )

    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise CabboException(
            f"Legal page {path.name} has invalid frontmatter.",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )

    metadata: dict[str, Any] = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if not line:
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise CabboException(
                f"Legal page {path.name} has invalid metadata line: {line}",
                status_code=500,
                error_code=GENERIC_EXCEPTION,
            )
        metadata[key.strip()] = _parse_frontmatter_value(value)

    metadata["content"] = parts[2].lstrip()
    return LegalPageInternal(**metadata)


def list_legal_pages() -> list[LegalPageSummary]:
    pages = sorted(_load_published_pages(), key=lambda page: page.display_order)
    return [LegalPageSummary(**page.model_dump()) for page in pages]


def get_legal_page_by_slug(slug: str) -> LegalPageRead:
    for page in _load_published_pages():
        if page.slug == slug:
            return LegalPageRead(**page.model_dump())

    raise CabboException(
        "Legal page not found.",
        status_code=404,
        error_code=GENERIC_EXCEPTION,
    )


def _load_published_pages() -> list[LegalPageInternal]:
    if not LEGAL_CONTENT_DIR.exists():
        raise CabboException(
            "Legal content directory not found.",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )

    pages = [
        _read_legal_page(path)
        for path in LEGAL_CONTENT_DIR.glob("*.md")
        if path.is_file()
    ]
    return [page for page in pages if page.status == "published"]
