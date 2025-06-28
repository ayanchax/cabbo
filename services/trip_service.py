from typing import List, Set

from models.cab.pricing_schema import (
    AirportCabPricingSchema,
    AirportPricingBreakdownSchema,
    LocalCabPricingSchema,
    LocalPricingBreakdownSchema,
    OutstationCabPricingSchema,
    OveragesSchema,
    CabTypeSchema,
    FuelTypeSchema,
    OutstationPricingBreakdownSchema,
)
from models.trip.trip_orm import TripPackageConfig
from models.trip.trip_schema import (
    TripPackageConfigSchema,
    TripSearchRequest,
    TripSearchOption,
    TripSearchResponse,
)
from sqlalchemy.orm import Session
from models.cab.pricing_orm import (
    CabType,
    FuelType,
    AirportCabPricing,
    LocalCabPricing,
    OutstationCabPricing,
)
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripTypeEnum
from core.exceptions import CabboException
from services.location_service import get_distance_km, get_state_from_location
from models.geography.geo_enums import APP_AIRPORT_LOCATION
from core.constants import APP_COUNTRY_CURRENCY_SYMBOL, APP_HOME_STATE
from datetime import datetime, timezone, timedelta
import math
from services.pricing_service import (
    get_airport_toll,
    get_preauthorized_minimum_wallet_amount,
    retrieve_interstate_permit_fee,
    retrieve_trip_wise_pricing_config,
)
from utils.utility import validate_date_time


def _retrieve_trip_package_by_id(
    package_id: str, fallback_duration: int, fallback_km: int, db: Session
):
    if not package_id:
        return TripPackageConfigSchema(
            included_hours=fallback_duration, included_km=fallback_km
        )
    package = (
        db.query(TripPackageConfig).filter(TripPackageConfig.id == package_id).first()
    )
    if not package:
        return TripPackageConfigSchema(
            included_hours=fallback_duration, included_km=fallback_km
        )
    package_schema = TripPackageConfigSchema.model_validate(package)
    return (
        package_schema
        if package_schema.included_hours and package_schema.included_hours > 0
        else TripPackageConfigSchema(
            included_hours=fallback_duration, included_km=fallback_km
        )
    )


def _populate_default_preferences(search_in: TripSearchRequest):
    """
    Ensures all required trip search preferences have sensible defaults.

    - Sets 'preferred_car_type' to CarTypeEnum.sedan if not provided.
    - Sets 'preferred_fuel_type' to FuelTypeEnum.diesel if not provided.
    - Ensures at least one adult is present (defaults to 1 if missing or < 1).
    - Ensures number of children is not negative (defaults to 0 if missing or < 0).

    Args:
        search_in (TripSearchRequest): The trip search request object to populate defaults for.
    """
    if not search_in.preferred_car_type:
        search_in.preferred_car_type = CarTypeEnum.sedan
    if not search_in.preferred_fuel_type:
        search_in.preferred_fuel_type = FuelTypeEnum.diesel
    if search_in.num_adults < 1 or search_in.num_adults is None:
        search_in.num_adults = 1  # Ensure at least one adult is present
    if search_in.num_children < 0 or search_in.num_children is None:
        search_in.num_children = 0


def _validate_placard_requirements(search_in: TripSearchRequest):
    """
    Validates the placard requirements for airport pickup trips.

    If the trip type is airport pickup and placard is required, it checks if the placard name is provided.
    Raises a CabboException if the placard name is missing.

    Args:
        search_in (TripSearchRequest): The trip search request object containing trip details.

    Raises:
        CabboException: If placard name is required but not provided.
    """
    if (
        search_in.trip_type == TripTypeEnum.airport_pickup
        and search_in.placard_required
        and not search_in.placard_name
    ):
        raise CabboException(
            "Placard name is required for airport pickup with placard",
            status_code=400,
        )


def get_trip_search_options(
    search_in: TripSearchRequest, db: Session
) -> TripSearchResponse:
    """
    Returns a list of cab options with detailed pricing and breakdown for a user's trip search and preferences.

    This method is responsible for presenting the user with various cab options (car type and fuel type)
    along with the total price and a transparent price breakdown for each option, whenever a trip booking
    search is made on Cabbo. It incorporates user preferences (car type, fuel type), number of passenger and luggage
    details, and applies advanced business logic for:
      - Luggage-based cab suggestions and overage warnings
      - Transparent toll, parking, and permit fee handling
      - Interstate trip logic and permit fee calculation for outstation trips
      - Platform and fixed service fees
      - Overage estimation and warnings for local, airport, and outstation trips to inform users of potential extra charges
      - Intelligent sorting based on user preferences and trip context
    The returned list is sorted to prioritize the most suitable options for the user's needs.

    Args:
        search_in (TripSearchRequest): The user's trip search request, including trip type, origin, destination,
            passenger count, luggage info, and preferences.
        db (Session): SQLAlchemy database session for fetching pricing/config data.

    Returns:
        TripSearchResponse: List of cab options, each with car type, fuel type, total price, price breakdown,
            and overage information, sorted by suitability for the user's request.

    Raises:
        CabboException: If the trip type is invalid or not supported, or if any validation fails.
    """
    _validate_trip_type(search_in)  # Validate trip type before proceeding
    _populate_default_preferences(search_in)  # Ensure preferences are set
    options: List[TripSearchOption] = []
    configs = retrieve_trip_wise_pricing_config(db, search_in.trip_type)
    platform_fee_percent = configs.dynamic_platform_fee_percent
    toll = 0.0
    parking = 0.0

    if search_in.trip_type == TripTypeEnum.airport_pickup:  # from airport
        _validate_airport_schedule(search_in)  # Validate airport pickup schedule
        _validate_placard_requirements(search_in)  # Validate placard requirements
        _, _, est_km = _get_trip_origin_destination_distance_airport_pickup(search_in)
        parking = configs.parking if configs.parking is not None else 0.0
        toll = get_airport_toll(configs.toll, search_in.toll_road_preferred)
        inclusions, exclusions = _get_airport_pickup_inclusions_exclusions(
            toll_road_preferred=search_in.toll_road_preferred,
            placard_required=search_in.placard_required,
        )
        airport_pricings = (
            db.query(AirportCabPricing, CabType, FuelType)
            .join(CabType, AirportCabPricing.cab_type_id == CabType.id)
            .join(FuelType, AirportCabPricing.fuel_type_id == FuelType.id)
            .all()
        )

        for pricing, cab_type, fuel_type in airport_pricings:
            pricing_schema = AirportCabPricingSchema.model_validate(pricing)
            cab_type_schema = CabTypeSchema.model_validate(cab_type)
            fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
            base_fare_per_km = pricing_schema.airport_fare_per_km
            max_included_km = configs.max_included_km
            overage_amount_per_km = pricing_schema.overage_amount_per_km
            placard_charge = (
                configs.placard_charge
                if search_in.placard_required and configs.placard_charge is not None
                else 0.0
            )
            base_price = base_fare_per_km * min(est_km, max_included_km)
            overage_amount = max(0, est_km - max_included_km) * overage_amount_per_km
            # Total price includes base fare, toll and parking charges and placard charges (if any)
            # We wont add the overage charge to the total price for airport pickups because overages is an estimation and not a fixed charge
            # Overages will apply if at the end of the trip the actual distance covered(as reported by driver) is more than the estimated distance
            # This indicator is to ensure that the customer is aware that overage charges may apply for this route
            total_price_before_platform_fee = math.ceil(
                base_price + toll + parking + placard_charge
            )
            warning_km_threshold = configs.overage_warning_km_threshold
            margin = max_included_km - est_km  # Allow negative values for overage
            indicative_overage_warning = margin <= warning_km_threshold
            # Platform fee is a sum of a fixed cost to service fee and a percentage of the total price calculated before adding platform fee
            platform_fee_amount = configs.fixed_platform_fee + (
                platform_fee_percent * total_price_before_platform_fee / 100
            )
            package_label = f"Airport Pickup | AC {cab_type_schema.name} - ({fuel_type_schema.name})"

            price_breakdown = AirportPricingBreakdownSchema(
                base_fare=math.ceil(base_price),
                placard_charge=math.ceil(placard_charge),
                toll=math.ceil(toll),
                parking=math.ceil(parking),
                platform_fee=math.ceil(platform_fee_amount),
            )
            options.append(
                TripSearchOption(
                    car_type=cab_type_schema.name,  # Use display name from schema
                    fuel_type=fuel_type_schema.name,  # Use display name from schema
                    total_price=math.ceil(
                        total_price_before_platform_fee + price_breakdown.platform_fee
                    ),
                    price_breakdown=price_breakdown,
                    estimated_km=est_km,
                    package=package_label,  # Use package string for display
                    inclusions=inclusions,
                    exclusions=exclusions,
                    overages=(
                        OveragesSchema(
                            indicative_overage_warning=indicative_overage_warning,
                            overage_amount_per_km=(
                                overage_amount_per_km
                                if indicative_overage_warning
                                else 0.0
                            ),
                            overage_estimate=(
                                math.ceil(overage_amount)
                                if indicative_overage_warning
                                else 0.0
                            ),
                        )
                    ),
                )
            )
    elif search_in.trip_type == TripTypeEnum.airport_drop:  # to airport
        _validate_airport_schedule(search_in)  # Validate airport drop schedule
        _, _, est_km = _get_trip_origin_destination_distance_airport_drop(search_in)
        toll = get_airport_toll(configs.toll, search_in.toll_road_preferred)
        inclusions, exclusions = _get_airport_drop_inclusions_exclusions(
            toll_road_preferred=search_in.toll_road_preferred
        )
        airport_pricings = (
            db.query(AirportCabPricing, CabType, FuelType)
            .join(CabType, AirportCabPricing.cab_type_id == CabType.id)
            .join(FuelType, AirportCabPricing.fuel_type_id == FuelType.id)
            .all()
        )
        for pricing, cab_type, fuel_type in airport_pricings:
            pricing_schema = AirportCabPricingSchema.model_validate(pricing)
            cab_type_schema = CabTypeSchema.model_validate(cab_type)
            fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
            base_fare_per_km = pricing_schema.airport_fare_per_km
            max_included_km = configs.max_included_km
            overage_amount_per_km = pricing_schema.overage_amount_per_km
            base_price = base_fare_per_km * min(est_km, max_included_km)
            overage_amount = max(0, est_km - max_included_km) * overage_amount_per_km
            # Total price includes base fare, toll and parking charges (if any)
            # We wont add the overage charge to the total price for airport pickups because overages is an estimation and not a fixed charge
            # Overages will apply if at the end of the trip the actual distance is more than the estimated distance
            # This indicator is to ensure that the customer is aware that overage charges may apply for this route
            total_price_before_platform_fee = math.ceil(base_price + toll + parking)
            warning_km_threshold = configs.overage_warning_km_threshold
            margin = max_included_km - est_km  # Allow negative values for overage
            indicative_overage_warning = margin <= warning_km_threshold
            # Platform fee is a sum of a fixed cost to service fee and a percentage of the total price calculated before adding platform fee
            platform_fee_amount = configs.fixed_platform_fee + (
                platform_fee_percent * total_price_before_platform_fee / 100
            )
            package_label = (
                f"Airport Drop | AC {cab_type_schema.name} - ({fuel_type_schema.name})"
            )
            price_breakdown = AirportPricingBreakdownSchema(
                base_fare=math.ceil(base_price),
                toll=math.ceil(toll),
                platform_fee=math.ceil(platform_fee_amount),
            )
            options.append(
                TripSearchOption(
                    car_type=cab_type_schema.name,  # Use display name
                    fuel_type=fuel_type_schema.name,  # Use display name
                    total_price=math.ceil(
                        total_price_before_platform_fee + price_breakdown.platform_fee
                    ),
                    price_breakdown=price_breakdown,
                    estimated_km=est_km,
                    package=package_label,
                    inclusions=inclusions,
                    exclusions=exclusions,
                    overages=(
                        OveragesSchema(
                            indicative_overage_warning=indicative_overage_warning,
                            overage_amount_per_km=(
                                overage_amount_per_km
                                if indicative_overage_warning
                                else 0.0
                            ),
                            overage_estimate=(
                                math.ceil(overage_amount)
                                if indicative_overage_warning
                                else 0.0
                            ),
                        )
                    ),
                )
            )
    elif search_in.trip_type == TripTypeEnum.local:
        _, _, _ = _get_trip_origin_destination_distance_local(search_in)
        inclusions, exclusions = _get_local_inclusions_exclusions()
        # Minimum parking wallet amount is configured to 80 for local trips, if the total cost of the parking goes above the minimum parking amount, then the surplus amount will be charged to the customer accordingly, otherwise the left/unused amount will be refunded(deducted from final bill) to the customer.
        minimum_parking_wallet = get_preauthorized_minimum_wallet_amount(
            configs.minimum_parking_wallet
        )
        # Get the package ID if provided, otherwise use configs.min_included_hours for duration
        package = _retrieve_trip_package_by_id(
            package_id=search_in.package_id,
            fallback_duration=configs.min_included_hours,
            fallback_km=configs.min_included_km,
            db=db,
        )
        package_label = f"{package.package_label} | AC {search_in.preferred_car_type} - ({search_in.preferred_fuel_type})"
        package_included_hours = package.included_hours
        package_included_km = package.included_km
        local_pricings = (
            db.query(LocalCabPricing, CabType, FuelType)
            .join(CabType, LocalCabPricing.cab_type_id == CabType.id)
            .join(FuelType, LocalCabPricing.fuel_type_id == FuelType.id)
            .all()
        )

        for pricing, cab_type, fuel_type in local_pricings:
            pricing_schema = LocalCabPricingSchema.model_validate(pricing)
            cab_type_schema = CabTypeSchema.model_validate(cab_type)
            fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
            hourly_rate = pricing_schema.hourly_rate
            max_included_hours = configs.max_included_hours
            base_hours = min(package.included_hours, max_included_hours)
            base_fare = hourly_rate * base_hours
            # No tolls are added for local trips as for local trips toll cannot be estimated or walleted in advance, if any tolls are incurred, they will be charged accordingly to the customer once the trip is completed
            total_price_before_platform_fee = base_fare + minimum_parking_wallet

            # Platform fee is a sum of a fixed cost to service and a percentage of the total price calculated before adding platform fee
            platform_fee_amount = configs.fixed_platform_fee + (
                platform_fee_percent * total_price_before_platform_fee / 100
            )

            price_breakdown = LocalPricingBreakdownSchema(
                base_fare=math.ceil(base_fare),
                minimum_parking_wallet=math.ceil(minimum_parking_wallet),
                platform_fee=math.ceil(platform_fee_amount),
            )
            # For local trips, we can't estimate distance in advance since routes are uncertain and hence no est_km is provided.
            # Overage charges will be initially presented as 0.00 and will be calculated only if the customer exceeds the included hours or km, to keep them informed through a disclaimer message that extra charges may apply at the end of the trip.
            overage_amount_per_km = pricing_schema.overage_amount_per_km
            overage_amount_per_hour = pricing_schema.overage_amount_per_hour
            disclaimer_message = f"""Extra charges may apply: 
                                     - If you exceed the included hours and/or kilometers in your selected package({package_label}), {APP_COUNTRY_CURRENCY_SYMBOL}{overage_amount_per_hour} per additional hour and/or {APP_COUNTRY_CURRENCY_SYMBOL}{overage_amount_per_km} per additional km will be charged. 
                                     - If any tolls are incurred during your trip, they will be billed based on actual usage
                                     - If parking expenses during your trip exceed the included wallet amount, the extra will be charged separately. If you use less than the included amount, the unused balance will be refunded (subtracted from your final bill) at the end of your trip.
                                     - All extra charges are based on actual usage and will be transparently shown in your invoice"""
            options.append(
                TripSearchOption(
                    car_type=cab_type_schema.name,  # Use display name from schema
                    fuel_type=fuel_type_schema.name,  # Use display name from schema
                    total_price=math.ceil(
                        total_price_before_platform_fee + price_breakdown.platform_fee
                    ),
                    price_breakdown=price_breakdown,
                    included_hours=package_included_hours,
                    included_km=package_included_km,
                    package=package_label,  # Use package string for display
                    inclusions=inclusions,
                    exclusions=exclusions,
                    overages=(
                        OveragesSchema(
                            disclaimer=disclaimer_message,
                        )
                    ),
                )
            )
    elif search_in.trip_type == TripTypeEnum.outstation:

        _, _, est_km = _get_trip_origin_destination_distance_outstation(search_in)
        total_trip_days = _validate_outstation_trip_schedule(search_in)
        # Minumum toll wallet amount is configured to 500.00 for outstation trips, if the total cost of the toll goes above the minimum toll amount during the trip, then the surplus amount will be charged to the customer accordingly, otherwise the left/unused amount will be refunded(deducted from final bill) to the customer.
        minimum_toll_wallet = get_preauthorized_minimum_wallet_amount(
            configs.minimum_toll_wallet
        )

        # Minimum parking wallet amount is configured to 150 for outstation trips, if the total cost of the parking goes above the minimum parking amount, then the surplus amount will be charged to the customer accordingly, otherwise the left/unused amount will be refunded(deducted from final bill) to the customer.
        minimum_parking_wallet = get_preauthorized_minimum_wallet_amount(
            configs.minimum_parking_wallet
        )

        # Identify unique state borders crossed (including between hops)
        is_interstate, _, unique_states = _track_state_transitions(search_in)
        inclusions, exclusions = _get_outstation_inclusions_exclusions(is_interstate)
        permit_fee = 0.0
        est_km = (
            2 * est_km
        )  # Always Round trip distance for outstation, therefore multiply by 2
        night_surcharge_per_hour = (
            configs.fixed_night_pricing.night_overage_amount_per_block
        )
        night_hours_display_label = configs.fixed_night_pricing.night_hours_label

        # Fetch all outstation cab pricings
        outstation_pricings = (
            db.query(OutstationCabPricing, CabType, FuelType)
            .join(CabType, OutstationCabPricing.cab_type_id == CabType.id)
            .join(FuelType, OutstationCabPricing.fuel_type_id == FuelType.id)
            .all()
        )
        for pricing, cab_type, fuel_type in outstation_pricings:
            # Skip CNG cabs for outstation trips
            if fuel_type.name.lower() == FuelTypeEnum.cng.lower():
                continue
            pricing_schema = OutstationCabPricingSchema.model_validate(pricing)
            cab_type_schema = CabTypeSchema.model_validate(cab_type)
            fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
            # Calculate interstate permit fee if applicable per cab type and fuel type for the unique states crossed
            if is_interstate and unique_states:
                permit_fee = retrieve_interstate_permit_fee(
                    unique_states=unique_states,
                    trip_days=total_trip_days,
                    cab_type_id=cab_type_schema.id,
                    fuel_type_id=fuel_type_schema.id,
                    db=db,
                )
            base_fare_per_km = pricing_schema.base_fare_per_km
            min_included_km_per_day = pricing_schema.min_included_km_per_day
            overage_amount_per_km = pricing_schema.overage_amount_per_km
            driver_allowance_per_day = pricing_schema.driver_allowance_per_day

            included_km = min_included_km_per_day * total_trip_days
            base_price = base_fare_per_km * included_km
            overage_km = max(0, est_km - included_km)
            overage_amount = overage_km * overage_amount_per_km
            driver_allowance_amount = driver_allowance_per_day * total_trip_days

            warning_km_threshold = configs.overage_warning_km_threshold
            margin = included_km - est_km  # Allow negative values for overage
            indicative_overage_warning = margin <= warning_km_threshold
            package_label = f"{max(est_km, included_km)} km | Round trip | ({total_trip_days} days) - AC {cab_type_schema.name} - ({fuel_type_schema.name})"

            # Total before platform fee
            total_price_before_platform_fee = (
                base_price
                + driver_allowance_amount
                + minimum_toll_wallet
                + minimum_parking_wallet
                + permit_fee
                + overage_amount
            )
            # Platform fee is a sum of a fixed cost to service fee and a percentage of the total price calculated before adding platform fee
            platform_fee_amount = configs.fixed_platform_fee + (
                platform_fee_percent * total_price_before_platform_fee / 100
            )
            price_breakdown = OutstationPricingBreakdownSchema(
                base_fare=math.ceil(base_price),
                driver_allowance=math.ceil(driver_allowance_amount),
                minimum_toll_wallet=math.ceil(minimum_toll_wallet),
                minimum_parking_wallet=math.ceil(minimum_parking_wallet),
                permit_fee=math.ceil(permit_fee),
                platform_fee=math.ceil(platform_fee_amount),
            )
            options.append(
                TripSearchOption(
                    car_type=cab_type_schema.name,
                    fuel_type=fuel_type_schema.name,
                    total_price=math.ceil(
                        total_price_before_platform_fee + platform_fee_amount
                    ),
                    price_breakdown=price_breakdown,
                    included_km=included_km,
                    inclusions=inclusions,
                    exclusions=exclusions,
                    package=package_label,
                    overages=(
                        OveragesSchema(
                            indicative_overage_warning=indicative_overage_warning,
                            overage_amount_per_km=(
                                overage_amount_per_km
                                if indicative_overage_warning
                                else 0.0
                            ),
                            overage_estimate=(
                                math.ceil(overage_amount)
                                if indicative_overage_warning
                                else 0.0
                            ),
                            disclaimer=f"""Extra charges may apply:
    - If the driver drives during night hours ({night_hours_display_label}), a nightly hourly surcharge of {APP_COUNTRY_CURRENCY_SYMBOL}{night_surcharge_per_hour} will be applied.
    - If total toll and/or parking expenses during your trip exceed the included wallet amount, the extra will be charged separately. If you use less than the included amount, the unused balance will be refunded (subtracted from your final bill) at the end of your trip.
    - All extra charges are based on actual usage and will be transparently shown in your invoice.""",
                        )
                    ),
                )
            )
    else:
        # If the trip type is not supported, raise an exception
        raise CabboException("Trip is not supported", status_code=501)

    # Intelligent sorting based on user preferences and trip context
    def sort_key(option: TripSearchOption):
        # 1. User preferred car type/fuel type always first
        pref_score = 0
        if (
            search_in.preferred_car_type
            and option.car_type == search_in.preferred_car_type
        ):
            pref_score -= 1000  # Strong preference
        if (
            search_in.preferred_fuel_type
            and option.fuel_type == search_in.preferred_fuel_type
        ):
            pref_score -= 500
        # 2. Passenger count logic
        total_pax = search_in.num_adults + search_in.num_children
        if total_pax > 4:  # More than 4 passengers, prefer larger vehicles
            if option.car_type in [CarTypeEnum.suv, CarTypeEnum.suv_plus]:
                pref_score -= 200
        elif total_pax <= 4:  # 4 or fewer passengers, prefer smaller vehicles
            if option.car_type in [CarTypeEnum.sedan, CarTypeEnum.sedan_plus]:
                pref_score -= 100
        if total_pax <= 3:  #
            if option.car_type == CarTypeEnum.hatchback:
                pref_score -= 50
        # 3. Luggage logic (fine-grained)
        num_large_suitcases = search_in.num_large_suitcases or 0
        num_carryons = search_in.num_carryons or 0
        num_backpacks = search_in.num_backpacks or 0
        num_other_bags = search_in.num_other_bags or 0
        # Strongly prefer SUV/SUV+ only if large suitcases/trolley bags are 3 or more
        if num_large_suitcases >= 3:
            if option.car_type in [CarTypeEnum.suv, CarTypeEnum.suv_plus]:
                pref_score -= 300  # Strong preference for SUV/SUV+
            else:
                pref_score += 200  # Penalize smaller cars
        # Strongly prefer sedan/premium sedan if large suitcases/trolley bags are exactly 2
        elif num_large_suitcases == 2:
            if option.car_type in [CarTypeEnum.sedan, CarTypeEnum.sedan_plus]:
                pref_score -= 200  # Strong preference for sedan/sedan+
            elif option.car_type in [CarTypeEnum.suv, CarTypeEnum.suv_plus]:
                pref_score += 50  # Slightly penalize SUV/SUV+ (overkill for 2 bags)
            elif option.car_type == CarTypeEnum.hatchback:
                pref_score += 200  # Penalize hatchback

        # Moderate preference for SUV/SUV+ for other bag types
        elif num_carryons > 2 or num_backpacks > 1 or num_other_bags > 1:
            if option.car_type in [CarTypeEnum.suv, CarTypeEnum.suv_plus]:
                pref_score -= 150
            else:
                pref_score += 100
        elif num_carryons <= 2 or num_backpacks == 1 or num_other_bags == 1:
            if option.car_type in [CarTypeEnum.sedan, CarTypeEnum.sedan_plus]:
                pref_score -= 100
            elif option.car_type == CarTypeEnum.hatchback:
                pref_score += 100
        # 4. Price as a tiebreaker
        return (pref_score, option.total_price)

    _options = sorted(options, key=sort_key)[
        : len(options)
    ]  #  Limit to top n options based on user preferences and trip context
    return TripSearchResponse(options=_options, preferences=search_in)


def _get_local_inclusions_exclusions():
    """
    Returns the inclusions and exclusions for local trips.
    Returns:
        Tuple[List[str], List[str]]:
            - inclusions (List[str]): List of inclusions for the trip.
            - exclusions (List[str]): List of exclusions for the trip.
    """
    inclusions = [
        "Base fare",
        "Minimum parking allowance",
        "Water bottles and tissues",
        "Platform fee",
    ]
    exclusions = [
        "Personal expenses",
        "Self sponsored driver meals",
        "Tolls(if applicable)",
        "Extra parking(if any)",
    ]
    return inclusions, exclusions


def _get_outstation_inclusions_exclusions(is_interstate: bool):
    """
    Returns the inclusions and exclusions for outstation trips based on whether it is interstate or not.
    Args:
        is_interstate (bool): True if the trip is interstate, False otherwise.
    Returns:
        Tuple[List[str], List[str]]:
            - inclusions (List[str]): List of inclusions for the trip.
            - exclusions (List[str]): List of exclusions for the trip.
    """
    inclusions = [
        "Base fare",
        "Driver allowance",
        "Minimum parking and toll allowance",
        "Water bottles, candies, and tissues",
        "Platform fee",
    ]
    exclusions = [
        "Personal expenses",
        "Self sponsored driver meals and/or accomodation",
        "Night surcharges(if applicable)",
        "Extra tolls(if any)",
        "Extra parking(if any)",
    ]
    if is_interstate:
        inclusions = [
            "Base fare",
            "Driver allowance",
            "Minimum parking and toll allowance",
            "State entry taxes",
            "Water bottles, candies, and tissues",
            "Platform fee",
        ]
    return inclusions, exclusions


def _get_airport_drop_inclusions_exclusions(toll_road_preferred: bool = False):
    """
    Returns the inclusions and exclusions for airport drop trips.
    Returns:
        Tuple[List[str], List[str]]:
            - inclusions (List[str]): List of inclusions for the trip.
            - exclusions (List[str]): List of exclusions for the trip.
    """
    if toll_road_preferred:
        inclusions = [
            "Base fare",
            "Toll",
            "Water bottles and tissues",
            "Platform fee",
        ]
    else:
        # If toll road is not preferred, we don't include toll charges
        # and hence we don't include it in the inclusions list
        inclusions = ["Base fare", "Water bottles and tissues", "Platform fee"]

    exclusions = ["Personal expenses", "Self sponsored driver meals"]
    return inclusions, exclusions


def _get_airport_pickup_inclusions_exclusions(
    toll_road_preferred: bool = False, placard_required: bool = False
):
    """
    Returns the inclusions and exclusions for airport pickup trips.
    Returns:
        Tuple[List[str], List[str]]:
            - inclusions (List[str]): List of inclusions for the trip.
            - exclusions (List[str]): List of exclusions for the trip.
    """
    if toll_road_preferred and placard_required:
        inclusions = [
            "Base fare",
            "Toll",
            "Parking",
            "Platform fee",
            "Water bottles and tissues",
            "Placard charges",
        ]
    elif toll_road_preferred and not placard_required:
        inclusions = [
            "Base fare",
            "Toll",
            "Parking",
            "Water bottles and tissues",
            "Platform fee",
        ]
    elif not toll_road_preferred and placard_required:
        inclusions = [
            "Base fare",
            "Parking",
            "Platform fee",
            "Water bottles and tissues",
            "Placard charges",
        ]
    else:
        # If neither toll road preferred nor placard required
        # then we don't include toll and placard charges
        inclusions = [
            "Base fare",
            "Parking",
            "Water bottles and tissues",
            "Platform fee",
        ]
    exclusions = ["Personal expenses", "Self sponsored driver meals"]
    return inclusions, exclusions


def _track_state_transitions(search_in: TripSearchRequest):
    """
    Tracks state transitions for a trip based on the provided search request.
    This function analyzes the origin, hops, and destination locations in the search request
    to determine if the trip is interstate and counts the number of unique states crossed.
    Args:
        search_in (TripSearchRequest): The trip search request containing origin, hops, and destination locations.
        Returns:
            Tuple[bool, int, List[str]]
                - is_interstate (bool): True if the trip crosses state borders, False otherwise.
                - total_unique_states (int): Total number of unique states crossed during the trip.
                - unique_states (List[str]): List of unique state names (case-insensitive) crossed during the trip.

    """
    all_locations = [search_in.origin]  # Instance of LocationInfo
    if search_in.hops:
        all_locations.extend(search_in.hops)  # List of LocationInfo instances
    all_locations.append(search_in.destination)  # Instance of LocationInfo
    unique_states = Set[str]()
    state_borders_crossed = 0
    prev_state = get_state_from_location(all_locations[0])  # Origin location state
    unique_states.add(prev_state)
    for loc in all_locations[
        1:
    ]:  # Iterate through all locations including hops and destination except the first one
        curr_state = get_state_from_location(loc)
        if curr_state.lower() != prev_state.lower():
            state_borders_crossed += 1
            unique_states.add(curr_state.lower())
        prev_state = curr_state.lower()
    total_unique_states = len(unique_states)
    is_interstate = (
        total_unique_states > 1
    )  # More than one unique state means interstate trip
    return is_interstate, total_unique_states, list(unique_states)


def _validate_trip_type(search_in: TripSearchRequest):
    """
    Validates the trip type in the search request.

    Args:
        search_in (TripSearchRequest): The trip search request containing the trip type.

    Raises:
        CabboException: If the trip type is not supported.
    """
    valid_trip_types = [
        TripTypeEnum.airport_pickup,
        TripTypeEnum.airport_drop,
        TripTypeEnum.local,
        TripTypeEnum.outstation,
    ]
    if search_in.trip_type not in valid_trip_types:
        raise CabboException(
            "Invalid trip type. Supported types are: airport_pickup, airport_drop, local, outstation",
            status_code=400,
        )


def _validate_outstation_trip_schedule(search_in: TripSearchRequest):
    """
    Validates the start and end dates for outstation trips.
    Ensures that:
    - Start date and end date are provided
    - Dates are not in the past
    - Start date is at least 2 days from now
    - Start date is before end date
    - Total trip days are greater than 1
    Args:
        search_in (TripSearchRequest): The trip search request containing start and end dates.
        Returns:
        int: The total number of trip days (inclusive).
    Raises:
        CabboException: If any validation fails, with appropriate error messages.
    """
    if search_in.start_date is None or search_in.end_date is None:
        raise CabboException(
            "Start date and end date are required for outstation trip", status_code=400
        )
    # Parse and validate start_date
    start_date = validate_date_time(date_time=search_in.start_date)
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    end_date = validate_date_time(date_time=search_in.end_date)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)

    # Check for past dates
    if start_date < now or end_date < now:
        raise CabboException(
            "Start date and end date for outstation trip cannot be in the past.",
            status_code=400,
        )
    # Start date must be at least 2 days after now
    min_start = now + timedelta(days=2)
    if start_date < min_start:
        raise CabboException(
            "Start date for outstation trip must be at least 2 days from now.",
            status_code=400,
        )
    if start_date > end_date:
        raise CabboException(
            "Start date cannot be after end date for outstation trip", status_code=400
        )
    # Calculate total number of trip days (inclusive, ceil if fractional)
    total_seconds = (end_date - start_date).total_seconds()
    total_days = math.ceil(total_seconds / 86400)
    if total_days <= 1:
        raise CabboException(
            "Total trip days must be greater than 1 for outstation trips",
            status_code=400,
        )
    return total_days


def _validate_airport_schedule(search_in: TripSearchRequest):

    if search_in.start_date is None:
        raise CabboException(
            "Start date is required for airport transfer", status_code=400
        )
    # Parse and validate start_date
    start_date = validate_date_time(date_time=search_in.start_date)

    now = datetime.now(timezone.utc)
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)

    # Check for past dates
    if start_date < now:
        raise CabboException(
            "Start date for airport transfer cannot be in the past.",
            status_code=400,
        )


def _get_trip_origin_destination_distance_airport_pickup(search_in: TripSearchRequest):
    """
    Validates and retrieves the origin, destination, and estimated distance for airport pickup trips.
    Args:
        search_in (TripSearchRequest): The trip search request containing origin and destination.
        Returns:
           Tuple[LocationInfo, LocationInfo, float]: A tuple containing the origin, destination, and estimated distance in kilometers.
    Raises:
        CabboException: If origin or destination is not provided, or if the estimated distance cannot be calculated.
    """

    if not search_in.origin:
        search_in.origin = APP_AIRPORT_LOCATION.get(APP_HOME_STATE, None)
    if not search_in.origin:
        raise CabboException("Origin is required", status_code=400)

        # Origin is airport, destination is required
    if not search_in.destination:
        raise CabboException("Destination is required", status_code=400)
    est_km = get_distance_km(origin=search_in.origin, destination=search_in.destination)
    if not est_km or est_km <= 0:
        raise CabboException(
            "Could not estimate distance between origin and destination",
            status_code=400,
        )

    return search_in.origin, search_in.destination, est_km


def _get_trip_origin_destination_distance_airport_drop(search_in: TripSearchRequest):
    """
    Validates and retrieves the origin, destination, and estimated distance for airport drop trips.
    Args:
        search_in (TripSearchRequest): The trip search request containing origin and destination.
        Returns: Tuple [LocationInfo, LocationInfo, float]: A tuple containing the origin, destination, and estimated distance in kilometers.
    Raises:
        CabboException: If origin or destination is not provided, or if the estimated distance cannot be calculated.
    """

    if not search_in.origin:
        raise CabboException("Origin is required for airport drop", status_code=400)

    if not search_in.destination:
        search_in.destination = APP_AIRPORT_LOCATION.get(APP_HOME_STATE, None)

    if not search_in.destination:
        raise CabboException(
            "Destination is required for airport drop", status_code=400
        )
    est_km = get_distance_km(origin=search_in.origin, destination=search_in.destination)
    if not est_km or est_km <= 0:
        raise CabboException(
            "Could not estimate distance between origin and destination",
            status_code=400,
        )
    return search_in.origin, search_in.destination, est_km


def _get_trip_origin_destination_distance_local(search_in: TripSearchRequest):
    """
    Validates and retrieves the origin, destination, and estimated distance for local trips.
    Args:
        search_in (TripSearchRequest): The trip search request containing origin and destination.
        Returns:
            Tuple[LocationInfo, LocationInfo, float]: A tuple containing the origin, destination, and estimated distance in kilometers.
    Raises:
        CabboException: If origin is not provided, or if the destination is not provided and cannot be inferred.
    """

    if not search_in.origin:
        raise CabboException("Origin is required for local trip", status_code=400)

    if not search_in.destination:
        search_in.destination = (
            search_in.origin
        )  # For local trips, origin and destination can be the same if not explicitly specified

    return (
        search_in.origin,
        search_in.destination,
        0.0,
    )  # Local trips don't require distance estimation as they are hourly based, can be 0 or any default value


def _get_trip_origin_destination_distance_outstation(search_in: TripSearchRequest):
    """
    Validates and retrieves the origin, destination, and estimated distance for outstation trips.
    Args:
        search_in (TripSearchRequest): The trip search request containing origin and destination.
        Returns:
            Tuple[LocationInfo, LocationInfo, float]: A tuple containing the origin, destination, and estimated distance in kilometers.
        Raises:
            CabboException: If origin or destination is not provided, or if the estimated distance cannot be calculated.

    """

    if (
        not search_in.origin
    ):  # Initial origin for outstation trip, final origin will be the first hop(origin)
        raise CabboException("Origin is required for outstation trip", status_code=400)

    if (
        not search_in.destination
    ):  # Initial destination for outstation trip, final destination will be the first hop(origin)
        raise CabboException(
            "Destination is required for outstation trip", status_code=400
        )

    est_km = get_distance_km(origin=search_in.origin, destination=search_in.destination)

    if not est_km or est_km <= 0:
        # Ensure that the estimated distance is a positive number
        # If the distance is zero or negative, it indicates an error in estimation
        raise CabboException(
            "Could not estimate distance between origin and destination",
            status_code=400,
        )

    return search_in.origin, search_in.destination, est_km
