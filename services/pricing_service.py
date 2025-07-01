from typing import List

from sqlalchemy import func
from core.constants import APP_COUNTRY_CURRENCY_SYMBOL
from models.cab.pricing_schema import (
    CommonPricingConfigSchema,
    FixedNightPricingSchema,
    PermitFeeSchema,
)
from models.geography.state_orm import GeoStateModel
from models.trip.trip_orm import TripTypeMaster
from sqlalchemy.orm import Session
from models.cab.pricing_orm import (
    CabType,
    CommonPricingConfiguration,
    FixedNightPricing,
    FixedPlatformPricing,
    FuelType,
    FixedPlatformPricing,
    PermitFeeConfiguration,
)
from models.trip.trip_enums import TripTypeEnum
from core.exceptions import CabboException


def retrieve_interstate_permit_fee(
    unique_states: List[str],
    trip_days: int,
    cab_type_id: str,
    fuel_type_id: str,
    db: Session,
):
    """
    Calculates and returns the total interstate permit fee for a list of unique states crossed during a trip,
    based on the total trip duration in days, cab type, and fuel type.

    For each unique state, the permit fee is charged for a minimum of 7 days (weekly fee).
    If the trip is longer than 7 days, a pro-rata fee is added for the extra days.

    Args:
        unique_states (List[str]): List of unique state names (case-insensitive) crossed during the trip.
        trip_days (int): Total number of days for the trip (inclusive).
        cab_type_id (str): The cab type ID for which to fetch permit fees.
        fuel_type_id (str): The fuel type ID for which to fetch permit fees.
        db (Session): SQLAlchemy database session for ORM queries.

    Returns:
        float: The total permit fee for all unique states crossed.

    Raises:
        CabboException: If any of the provided states are not found in the database or required parameters are missing.
    """
    unique_states_lower = [s.lower() for s in unique_states]
    if not unique_states_lower or trip_days <= 0:
        # If no states provided or trip days is 0 or less, return 0
        return 0.0
    # Fetch all states with permit fees that match the unique states and are valid for the given cab and fuel type
    if not cab_type_id or not fuel_type_id:
        return 0.0

    # Initialize permit fee to 0
    permit_fee = 0.0
    all_states = (
        db.query(GeoStateModel, PermitFeeConfiguration, CabType, FuelType)
        .join(
            PermitFeeConfiguration,
            PermitFeeConfiguration.state_id == GeoStateModel.id,
        )
        .join(CabType, PermitFeeConfiguration.cab_type_id == CabType.id)
        .join(FuelType, PermitFeeConfiguration.fuel_type_id == FuelType.id)
        .filter(
            func.lower(GeoStateModel.state_name).in_(unique_states_lower),
            PermitFeeConfiguration.permit_fee != None,
            PermitFeeConfiguration.permit_fee > 0,
        )
        .all()
    )
    if not all_states:
        # If no states found with permit fees, return 0
        return 0.0
    for _, permit_fee_config, _, _ in all_states:
        permit_fee_config_schema = PermitFeeSchema.model_validate(permit_fee_config)
        if (
            permit_fee_config_schema.permit_fee is not None
            and permit_fee_config_schema.permit_fee > 0
        ):
            weekly_fee = permit_fee_config_schema.permit_fee
            if trip_days <= 7:
                # If the trip is 7 days or less, charge only the weekly fee
                state_permit_fee = weekly_fee
            else:
                # Calculate pro-rata fee for days beyond the first week
                state_permit_fee = weekly_fee + ((trip_days - 7) * (weekly_fee / 7))
            permit_fee += state_permit_fee
    return permit_fee


def retrieve_trip_wise_pricing_config(
    db: Session, trip_type: TripTypeEnum
) -> CommonPricingConfigSchema:
    """
    Fetches and returns all common pricing and configuration objects for a given trip type.

    This method retrieves the configuration for overage warnings, toll and parking charges,
    platform fee, and fixed platform fee for the specified trip type from the database. These
    configurations are used throughout the pricing logic to ensure that all calculations are
    consistent, admin-editable, and type-safe. The returned TripTypeWiseConfig object is used
    to drive downstream pricing, warnings, and fee breakdowns for all trip workflows.

    Args:
        db (Session): SQLAlchemy database session for ORM queries.
        trip_type (TripTypeEnum): The trip type (local, outstation, airport, etc.) for which to fetch configs.

    Returns:
        TripTypeConfig: An object containing all pricing and config data for the given trip type.
            - config: CommonPricingConfigSchema (includes warning config, toll/parking, platform fee, fixed platform fee, etc.)

    Raises:
        CabboException: If the trip type is invalid or not found in the database, or if required config is missing.

    Notes:
        - All pricing/config data is admin-editable and type-safe.
        - Used by all downstream pricing and trip search logic to ensure consistency.
        - This method is the single source of truth for trip-type-specific pricing config.
    """
    trip_type_object = db.query(TripTypeMaster).filter_by(trip_type=trip_type).first()
    if not trip_type_object:
        raise CabboException("Invalid trip type", status_code=400)

    trip_type_id = trip_type_object.id
    if not trip_type_id:
        raise CabboException(
            "Trip type ID not found for the given trip type", status_code=404
        )

    fixed_platform_fee_config_orm = db.query(FixedPlatformPricing).first()
    fixed_platform_fee = (
        CommonPricingConfigSchema.model_validate(
            fixed_platform_fee_config_orm
        ).fixed_platform_fee
        if fixed_platform_fee_config_orm
        else None
    )
    if not fixed_platform_fee:
        raise CabboException(
            "No fixed platform fee configuration found", status_code=404
        )

    fixed_night_pricing_orm = db.query(FixedNightPricing).first()
    fixed_night_pricing = (
        FixedNightPricingSchema.model_validate(fixed_night_pricing_orm)
        if fixed_night_pricing_orm
        else None
    )
    if not fixed_night_pricing:
        raise CabboException(
            "No fixed night pricing configuration found", status_code=404
        )

    # Fetch all common pricing configurations for the trip type
    common_pricing_config_orm = (
        db.query(CommonPricingConfiguration)
        .filter(CommonPricingConfiguration.trip_type_id == trip_type_id)
        .first()
    )
    if not common_pricing_config_orm:
        raise CabboException(
            "No common pricing configuration found for the given trip type",
            status_code=404,
        )
    common_pricing_config = CommonPricingConfigSchema.model_validate(
        common_pricing_config_orm
    )
    if not common_pricing_config:
        raise CabboException(
            "Common pricing configuration is empty for the given trip type",
            status_code=404,
        )

    # Merge the fixed platform fee into the common pricing config
    common_pricing_config.fixed_platform_fee = fixed_platform_fee
    common_pricing_config.fixed_night_pricing = fixed_night_pricing
    return (
        common_pricing_config  # CommonPricingConfigSchema including fixed platform fee
    )


def get_airport_toll(toll: float, toll_road_preferred: bool):
    return toll if toll_road_preferred and toll is not None else 0.0


def get_preauthorized_minimum_wallet_amount(pre_authorized_wallet_amount: float):
    return (
        pre_authorized_wallet_amount
        if pre_authorized_wallet_amount is not None
        else 0.0
    )


def get_local_trips_disclaimer_lines(
    package_label: str, overage_amount_per_hour: float, overage_amount_per_km: float
):
    """
    Returns the disclaimer lines for local trips, including overage charges and parking fees.

    This function provides the standard disclaimer lines that are used in local trip pricing
    calculations, ensuring that customers are aware of potential extra charges.

    Returns:
        List[str]: A list of disclaimer lines for local trips.
    """
    return [
        f"If you exceed the included hours and/or kilometers in your selected package ({package_label}), {APP_COUNTRY_CURRENCY_SYMBOL}{overage_amount_per_hour} per additional hour and/or {APP_COUNTRY_CURRENCY_SYMBOL}{overage_amount_per_km} per additional km will be charged.",
        "If any tolls are incurred during your trip, they will be billed based on actual usage.",
        "If parking costs exceed the included wallet amount, the extra will be charged. If you use less, the unused balance will be refunded at the end of your trip.",
        "All extra charges are based on actual usage and will be transparently shown in your invoice.",
    ]


def get_outstation_trips_disclaimer_lines(
    night_hours_display_label: str,
    night_surcharge_per_hour: float,
):
    """
    Returns the disclaimer lines for outstation trips, including overage charges and parking fees.

    This function provides the standard disclaimer lines that are used in outstation trip pricing
    calculations, ensuring that customers are aware of potential extra charges.

    Returns:
        List[str]: A list of disclaimer lines for outstation trips.
    """

    return [
        f"If the driver drives during night hours ({night_hours_display_label}), a nightly hourly surcharge of {APP_COUNTRY_CURRENCY_SYMBOL}{night_surcharge_per_hour} will be applied.",
        "If total toll and/or parking costs exceed the included wallet amount, the extra will be charged. If you use less, the unused balance will be refunded at the end of your trip.",
        "All extra charges are based on actual usage and will be transparently shown in your invoice.",
    ]
