from typing import List

from models.cab.cab_orm import CabType, FuelType
from models.geography.state_orm import StateModel
from models.policies.cancelation_orm import CancellationPolicy
from models.policies.cancelation_schema import CancelationPolicySchema
from models.pricing.pricing_schema import (
    AirportCabPricingSchema,
    CommonPricingConfigurationSchema,
    FixedPlatformFeeConfigurationSchema,
    LocalCabPricingSchema,
    NightPricingConfigurationSchema,
    OutstationCabPricingSchema,
    PermitFeeConfigurationSchema,
    TripPackageConfigSchema,
)
from models.geography.region_orm import RegionModel
from models.trip.trip_orm import TripPackageConfig, TripTypeMaster
from sqlalchemy.orm import Session
from models.pricing.pricing_orm import (
    AirportCabPricing,
    CommonPricingConfiguration,
    LocalCabPricing,
    NightPricingConfiguration,
    FixedPlatformPricingConfiguration,
    OutstationCabPricing,
    PermitFeeConfiguration,
)
from models.trip.trip_enums import TripTypeEnum
from core.exceptions import CabboException
from models.trip.trip_schema import TripBookRequest, TripSearchOption

APP_COUNTRY_CURRENCY_SYMBOL = "₹"  # Placeholder for currency symbol, adjust as needed
 

def retrieve_trip_wise_pricing_config(
    db: Session, trip_type: TripTypeEnum
) -> CommonPricingConfigurationSchema:
    """
    Fetches and returns all common pricing and configuration objects for a given trip type.

    This method retrieves the configuration for overage warnings, toll and parking charges,
    platform fee/convenience fee, and fixed platform fee/infrastructure fee for the specified trip type from the database. These
    configurations are used throughout the pricing logic to ensure that all calculations are
    consistent, admin-editable, and type-safe. The returned TripTypeWiseConfig object is used
    to drive downstream pricing, warnings, and fee breakdowns for all trip workflows.

    Args:
        db (Session): SQLAlchemy database session for ORM queries.
        trip_type (TripTypeEnum): The trip type (local, outstation, airport, etc.) for which to fetch configs.

    Returns:
        TripTypeConfig: An object containing all pricing and config data for the given trip type.
            - config: CommonPricingConfigSchema (includes warning config, toll/parking, platform fee/convenience fee, fixed platform fee/infrastructure fee, etc.)

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

    fixed_platform_fee_config_orm = db.query(FixedPlatformPricingConfiguration).first()
    fixed_platform_fee = (
        CommonPricingConfigurationSchema.model_validate(
            fixed_platform_fee_config_orm
        ).fixed_platform_fee
        if fixed_platform_fee_config_orm
        else None
    )
    if not fixed_platform_fee:
        raise CabboException(
            "No fixed platform fee or infrastructure fee configuration found",
            status_code=404,
        )

    fixed_night_pricing_orm = db.query(NightPricingConfiguration).first()
    fixed_night_pricing = (
        NightPricingConfigurationSchema.model_validate(fixed_night_pricing_orm)
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
    common_pricing_config = CommonPricingConfigurationSchema.model_validate(
        common_pricing_config_orm
    )
    if not common_pricing_config:
        raise CabboException(
            "Common pricing configuration is empty for the given trip type",
            status_code=404,
        )

    # Merge the fixed platform fee/infrastructure fee into the common pricing config
    common_pricing_config.fixed_platform_fee = fixed_platform_fee
    common_pricing_config.night_pricing_configuration = fixed_night_pricing
    return common_pricing_config  # CommonPricingConfigSchema including fixed platform fee/infrastructure fee


def get_airport_toll(toll: float, toll_road_preferred: bool):
    return toll if toll_road_preferred and toll is not None else 0.0


def get_driver_allowance(option: TripSearchOption):
    if not option or not hasattr(option, "price_breakdown"):
        return 0.0
    if option.price_breakdown and hasattr(option.price_breakdown, "driver_allowance"):
        return option.price_breakdown.driver_allowance
    return 0.0


def get_tolls(booking_request: TripBookRequest) -> float:
    """
    Calculates the tolls for the trip based on the booking request.
    Args:
        booking_request (TripBookRequest): The trip booking request containing toll details.
    Returns:
        float: The tolls for the trip.
    """
    if booking_request.preferences.trip_type in [TripTypeEnum.local, TripTypeEnum.outstation]:
        # For local trips and outstation trips, tolls are not estimated in advance
        return 0.0
    
    elif booking_request.preferences.trip_type in [
        TripTypeEnum.airport_pickup,
        TripTypeEnum.airport_drop,
    ]:
        # For airport trips, use the tolls from the request if available
        return (
            booking_request.option.price_breakdown.toll
            if booking_request.preferences.toll_road_preferred
            and booking_request.option.price_breakdown.toll
            else 0.0
        )
    else:
        raise CabboException(
            f"Trip type {booking_request.preferences.trip_type} is not supported for tolls estimation",
            status_code=501,
        )


def get_parking(booking_request: TripBookRequest) -> float:
    """
    Calculates the parking charges for the trip based on the booking request.
    Args:
        booking_request (TripBookRequest): The trip booking request containing parking details.
    Returns:
        float: The parking charges for the trip.
    """
    if booking_request.preferences.trip_type == TripTypeEnum.airport_pickup:
        # For airport pickup, use the parking from the request if available
        return (
            booking_request.option.price_breakdown.parking
            if booking_request.option.price_breakdown.parking
            else 0.0
        )
    else:
        return 0.0  # For all other trip types, parking is not estimated in advance


def get_common_pricing_configurations_by_trip_type_id(
    trip_type_id: str,
    db: Session,
) -> List[CommonPricingConfigurationSchema]:
    """
    Fetches all common pricing configurations for a given trip type ID.
    Args:
        trip_type_id (str): The trip type ID for which to fetch configurations.
        db (Session): SQLAlchemy database session for ORM queries.
        Returns:
        List[CommonPricingConfigurationSchema]: A list of common pricing configuration ORM objects for the given trip type ID.
    """
    common_pricings = (
        db.query(CommonPricingConfiguration)
        .filter(CommonPricingConfiguration.trip_type_id == trip_type_id)
        .all()
    )
    # Model validate each pricing configuration by CommonPricingConfigurationSchema
    return [
        CommonPricingConfigurationSchema.model_validate(pricing)
        for pricing in common_pricings
    ]


def get_base_pricings_outstation(db: Session):
    return (
        db.query(OutstationCabPricing, CabType, FuelType)
        .join(CabType, OutstationCabPricing.cab_type_id == CabType.id)
        .join(FuelType, OutstationCabPricing.fuel_type_id == FuelType.id)
        .filter(
            OutstationCabPricing.is_available_in_network == True,
        )  # Ensure only available cabs are considered
        .all()
    )

def get_base_pricings_airport(db: Session):
    return (
            db.query(AirportCabPricing, CabType, FuelType)
            .join(CabType, AirportCabPricing.cab_type_id == CabType.id)
            .join(FuelType, AirportCabPricing.fuel_type_id == FuelType.id)
            .filter(
                AirportCabPricing.is_available_in_network == True
            )  # Ensure only available cabs are considered
            .all()
    )

def get_base_pricings_local(db: Session):
    base_pricings = (
            db.query(LocalCabPricing, CabType, FuelType)
            .join(CabType, LocalCabPricing.cab_type_id == CabType.id)
            .join(FuelType, LocalCabPricing.fuel_type_id == FuelType.id)
            .filter(
                LocalCabPricing.is_available_in_network == True,
            )  # Ensure only available cabs are considered
            .all()
        )
    return base_pricings


def get_night_pricing_configuration(
    db: Session, id: str, by_state: bool = False
) -> NightPricingConfigurationSchema:
    if by_state:
        night_pricing = (
            db.query(NightPricingConfiguration)
            .filter(
                NightPricingConfiguration.state_id == id,
            )
            .first()
        )
    else:
        night_pricing = (
            db.query(NightPricingConfiguration)
            .filter(
                NightPricingConfiguration.region_id == id,
            )
            .first()
        )
    if night_pricing:
        return NightPricingConfigurationSchema.model_validate(night_pricing)
    return None


def get_permit_fee_configuration(
    db: Session, state_id: str
) -> PermitFeeConfigurationSchema:
    permit_fee = (
        db.query(PermitFeeConfiguration)
        .filter(
            PermitFeeConfiguration.state_id == state_id,
        )
        .first()
    )
    if permit_fee:
        return PermitFeeConfigurationSchema.model_validate(permit_fee)
    return None

def get_fixed_platform_pricing_configuration(db:Session)->FixedPlatformFeeConfigurationSchema:
    platform_fee_data = db.query(FixedPlatformPricingConfiguration).first()
    if not platform_fee_data:
            return None
    platform_fee_data_schema = FixedPlatformFeeConfigurationSchema.model_validate(
            platform_fee_data
        )
    return platform_fee_data_schema

def create_local_cab_pricing(payload:LocalCabPricingSchema,db:Session)->LocalCabPricingSchema:
    local_cab_pricing_orm = LocalCabPricing(**payload.model_dump(exclude={"id"}, exclude_none=True))
    db.add(local_cab_pricing_orm)
    db.flush()
    db.refresh(local_cab_pricing_orm)
    return LocalCabPricingSchema.model_validate(local_cab_pricing_orm)

def create_outstation_cab_pricing(payload:OutstationCabPricingSchema,db:Session)->OutstationCabPricingSchema:
    outstation_cab_pricing_orm = OutstationCabPricing(**payload.model_dump(exclude={"id"}, exclude_none=True))
    db.add(outstation_cab_pricing_orm)
    db.flush()
    db.refresh(outstation_cab_pricing_orm)
    return OutstationCabPricingSchema.model_validate(outstation_cab_pricing_orm)

def create_airport_cab_pricing(payload:AirportCabPricingSchema,db:Session)->AirportCabPricingSchema:
    airport_cab_pricing_orm = AirportCabPricing(**payload.model_dump(exclude={"id"}, exclude_none=True))
    db.add(airport_cab_pricing_orm)
    db.flush()
    db.refresh(airport_cab_pricing_orm)
    return AirportCabPricingSchema.model_validate(airport_cab_pricing_orm)

def create_common_pricing_configuration(payload:CommonPricingConfigurationSchema,db:Session)->CommonPricingConfigurationSchema:
    common_pricing_configuration_orm = CommonPricingConfiguration(**payload.model_dump(exclude={"id"}, exclude_none=True))
    db.add(common_pricing_configuration_orm)
    db.flush()
    db.refresh(common_pricing_configuration_orm)
    return CommonPricingConfigurationSchema.model_validate(common_pricing_configuration_orm)

def create_trip_package_pricing_configuration(payload:TripPackageConfigSchema,db:Session)->TripPackageConfigSchema:
    trip_package_pricing_configuration_orm = TripPackageConfig(**payload.model_dump(exclude={"id"}, exclude_none=True))
    db.add(trip_package_pricing_configuration_orm)
    db.flush()
    db.refresh(trip_package_pricing_configuration_orm)
    return TripPackageConfigSchema.model_validate(trip_package_pricing_configuration_orm)

def create_night_pricing_configuration(payload:NightPricingConfigurationSchema,db:Session)->NightPricingConfigurationSchema:
    night_pricing_configuration_orm = NightPricingConfiguration(**payload.model_dump(exclude={"id"}, exclude_none=True))
    db.add(night_pricing_configuration_orm)
    db.flush()
    db.refresh(night_pricing_configuration_orm)
    return NightPricingConfigurationSchema.model_validate(night_pricing_configuration_orm)

def create_permit_fee_configuration(payload:PermitFeeConfigurationSchema,db:Session)->PermitFeeConfigurationSchema:
    permit_fee_configuration_orm = PermitFeeConfiguration(**payload.model_dump(exclude={"id"}, exclude_none=True))
    db.add(permit_fee_configuration_orm)
    db.flush()
    db.refresh(permit_fee_configuration_orm)
    return PermitFeeConfigurationSchema.model_validate(permit_fee_configuration_orm)

def create_cancellation_policy_pricing(payload:CancelationPolicySchema,db:Session)->CancelationPolicySchema:
    cancellation_policy_orm = CancellationPolicy(**payload.model_dump(exclude={"id"}, exclude_none=True))
    db.add(cancellation_policy_orm)
    db.flush()
    db.refresh(cancellation_policy_orm)
    return CancelationPolicySchema.model_validate(cancellation_policy_orm)

def create_fixed_platform_fee(payload:FixedPlatformFeeConfigurationSchema, db:Session):
    fixed_platform_fee_config = FixedPlatformPricingConfiguration(**payload.model_dump(exclude={"id"}, exclude_none=True))
    db.add(fixed_platform_fee_config)
    db.flush()
    db.refresh(fixed_platform_fee_config)
    return FixedPlatformFeeConfigurationSchema.model_validate(fixed_platform_fee_config)

def get_cancellation_policy_by_state_code(state_code: str, db: Session) -> CancelationPolicySchema:
    cancellation_policy = (
        db.query(CancellationPolicy)
        .join(StateModel, CancellationPolicy.state_id == StateModel.id)
        .filter(
            StateModel.state_code == state_code,
        )
        .first()
    )
    if cancellation_policy:
        return CancelationPolicySchema.model_validate(cancellation_policy)
    return None

def get_cancellation_policies_by_state_code(state_code: str, db: Session) -> List[CancelationPolicySchema]:
    policies = (
        db.query(CancellationPolicy)
        .join(StateModel, CancellationPolicy.state_id == StateModel.id)
        .filter(
            StateModel.state_code == state_code,
        )
        .all()
    )
    if policies:
        return [CancelationPolicySchema.model_validate(policy) for policy in policies]
    return None

def get_cancellation_policy_by_region_code(region_code: str, db: Session) -> CancelationPolicySchema:
    cancellation_policy = (
        db.query(CancellationPolicy)
        .join(RegionModel, CancellationPolicy.region_id == RegionModel.id)
        .filter(
            RegionModel.region_code == region_code,
        )
        .first()
    )
    if cancellation_policy:
        return CancelationPolicySchema.model_validate(cancellation_policy)
    return None 

def get_cancellation_policies_by_region_code(region_code: str, db: Session) -> List[CancelationPolicySchema]:
    policies = (
        db.query(CancellationPolicy)
        .join(RegionModel, CancellationPolicy.region_id == RegionModel.id)
        .filter(
            RegionModel.region_code == region_code,
        ).all()
    )
    if policies:
        return [CancelationPolicySchema.model_validate(policy) for policy in policies]
    return None 