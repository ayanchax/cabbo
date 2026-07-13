.PHONY: help alembic-autogen alembic-upgrade alembic-downgrade alembic-history

help:
    @echo "Usage:"
    @echo "  make alembic-autogen m='Migration message'   # Autogenerate migration"
    @echo "  make alembic-upgrade                        # Upgrade DB to latest"
    @echo "  make alembic-downgrade rev=<revision>       # Downgrade DB to revision"
    @echo "  make alembic-history                        # Show migration history"

alembic-autogen:
    alembic revision --autogenerate -m "$(m)"

alembic-upgrade:
    alembic upgrade head

alembic-downgrade:
    alembic downgrade $(rev)

alembic-history:
    alembic history --verbose