from datetime import datetime, timezone
import math
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models.taxation.tax_orm import TaxConfiguration
from models.taxation.tax_schema import TaxConfigurationSchema


PLATFORM_FEE_TAX_SCOPE = "platform_fee"


def create_tax_configuration(
    payload: TaxConfigurationSchema, db: Session
) -> TaxConfigurationSchema:
    tax_config = TaxConfiguration(**payload.model_dump(exclude_none=True))
    db.add(tax_config)
    db.commit()
    db.refresh(tax_config)
    return TaxConfigurationSchema.model_validate(tax_config)


async def a_get_active_tax_configuration(
    db: AsyncSession,
    country_id: str,
    tax_scope: str,
    as_of: Optional[datetime] = None,
) -> Optional[TaxConfigurationSchema]:
    as_of = as_of or datetime.now(timezone.utc)
    result = await db.execute(
        select(TaxConfiguration)
        .where(
            TaxConfiguration.country_id == country_id,
            TaxConfiguration.tax_scope == tax_scope,
            TaxConfiguration.is_active == True,
            TaxConfiguration.effective_from <= as_of,
            or_(
                TaxConfiguration.effective_to.is_(None),
                TaxConfiguration.effective_to >= as_of,
            ),
        )
        .order_by(TaxConfiguration.effective_from.desc())
    )
    tax_config = result.scalars().first()
    return TaxConfigurationSchema.model_validate(tax_config) if tax_config else None


def get_active_tax_configuration(
    db: Session,
    country_id: str,
    tax_scope: str,
    as_of: Optional[datetime] = None,
) -> Optional[TaxConfigurationSchema]:
    as_of = as_of or datetime.now(timezone.utc)
    tax_config = (
        db.query(TaxConfiguration)
        .filter(
            and_(
                TaxConfiguration.country_id == country_id,
                TaxConfiguration.tax_scope == tax_scope,
                TaxConfiguration.is_active == True,
                TaxConfiguration.effective_from <= as_of,
                or_(
                    TaxConfiguration.effective_to.is_(None),
                    TaxConfiguration.effective_to >= as_of,
                ),
            )
        )
        .order_by(TaxConfiguration.effective_from.desc())
        .first()
    )
    return TaxConfigurationSchema.model_validate(tax_config) if tax_config else None


def compute_tax_amount(taxable_amount: float, tax_rate_percent: float) -> int:
    if not taxable_amount or not tax_rate_percent:
        return 0
    return math.ceil(taxable_amount * tax_rate_percent / 100)


def compute_tax_on_base_platform_fee(
    platform_fee_base: float,
    tax_config: Optional[TaxConfigurationSchema] = None,
) -> dict:
    tax_amount = (
        compute_tax_amount(platform_fee_base, tax_config.rate_percent)
        if tax_config
        else 0
    )
    return {
        "platform_fee": math.ceil(platform_fee_base + tax_amount),
        "platform_fee_base": platform_fee_base,
        "platform_fee_tax": tax_amount,
        "platform_fee_tax_rate_percent": tax_config.rate_percent if tax_config else None,
        "platform_fee_tax_type": tax_config.tax_type if tax_config else None,
    }