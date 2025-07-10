from typing import List

from core.security import generate_trip_hash, verify_trip_hash
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
from models.customer.passenger_schema import (
    PassengerRead,
    PassengerRequest,
)
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_orm import Trip, TripPackageConfig, TripTypeMaster
from models.trip.trip_schema import (
    AmenitiesSchema,
    TripBookRequest,
    TripPackageConfigSchema,
    TripSearchAdditionalData,
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
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripStatusEnum, TripTypeEnum
from core.exceptions import CabboException
from services.location_service import get_distance_km, get_state_from_location
from models.geography.geo_enums import APP_AIRPORT_LOCATION
from core.constants import APP_HOME_STATE
from datetime import datetime, timezone, timedelta
import math
from services.passenger_service import get_passenger_by_id
from services.pricing_service import (
    get_airport_toll,
    get_airport_trips_disclaimer_lines,
    get_local_trips_disclaimer_lines,
    get_outstation_trips_disclaimer_lines,
    get_preauthorized_minimum_wallet_amount,
    retrieve_interstate_permit_fee,
    retrieve_trip_wise_pricing_config,
)
from utils.utility import validate_date_time
from models.geography.service_area_orm import ServiceableGeographyOrm
from models.trip.trip_enums import TripTypeEnum


def _retrieve_trip_package_by_id(
    package_id: str, db: Session, fallback_duration: int=4, fallback_km: int=40
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


def _validate_passenger_id(search_in: TripSearchRequest, requestor: str, db: Session):
    if (
        search_in.passenger
        and isinstance(search_in.passenger, PassengerRequest)
        and search_in.passenger.id
    ):
        search_in.passenger.id = search_in.passenger.id.strip()
        passenger = get_passenger_by_id(passenger_id=search_in.passenger.id, db=db)
        if not passenger:
            raise CabboException("Invalid passenger ID provided", status_code=400)
        if passenger.customer_id != requestor:
            raise CabboException(
                "Passenger does not belong to the requesting customer", status_code=403
            )
        if not passenger.is_active:
            raise CabboException("Passenger is not active", status_code=403)
        passenger_read = PassengerRead.model_validate(
            passenger
        )  # Validate passenger schema
        search_in.passenger.name = (
            passenger_read.name
        )  # Attach passenger details to request
        search_in.passenger.phone_number = passenger_read.phone_number
    else:

        search_in.passenger = "self"  # Use a string to indicate self-booking


def get_trip_search_options(
    search_in: TripSearchRequest, requestor: str, db: Session
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
    _validate_passenger_id(
        search_in, requestor, db
    )  # Validate passenger ID if provided
    _populate_default_preferences(search_in)  # Ensure preferences are set
    _validate_serviceable_area(search_in, db)  # Enforce serviceable area boundaries
    options: List[TripSearchOption] = []
    configs = retrieve_trip_wise_pricing_config(db, search_in.trip_type)
    platform_fee_percent = configs.dynamic_platform_fee_percent
    toll = 0.0
    parking = 0.0
    in_car_amenities = _get_default_amenities()
    total_trip_days = (
        None  # Default to 1 day for local and airport trips, can be overridden later
    )
    est_km = None
    total_unique_states:int = 0
    unique_states=[]

    is_interstate = False  # Default to False, will be set for outstation trips
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
            .filter(AirportCabPricing.is_available_in_network == True)  # Ensure only available cabs are considered
            .all()
        )
        package_short_label = "Airport Pickup"

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
            package_label = f"{package_short_label} | AC {cab_type_schema.name} - ({fuel_type_schema.name})"

            price_breakdown = AirportPricingBreakdownSchema(
                base_fare=math.ceil(base_price),
                placard_charge=math.ceil(placard_charge),
                toll=math.ceil(toll),
                parking=math.ceil(parking),
                platform_fee=math.ceil(platform_fee_amount),
            )
            disclaimer_lines = get_airport_trips_disclaimer_lines(
                overage_amount_per_km, max_included_km
            )
            option = TripSearchOption(
                    car_type=cab_type_schema.name,  # Use display name from schema
                    fuel_type=fuel_type_schema.name,  # Use display name from schema
                    total_price=math.ceil(
                        total_price_before_platform_fee + price_breakdown.platform_fee
                    ),
                    price_breakdown=price_breakdown,
                    package=package_label,  # Use package string for display
                    package_short_label=package_short_label,
                    overages=(
                        OveragesSchema(
                            indicative_overage_warning=indicative_overage_warning,
                            overage_amount_per_km=(
                                overage_amount_per_km
                                if indicative_overage_warning
                                else 0.0
                            ),
                            overage_estimate_amount=(
                                math.ceil(overage_amount)
                                if indicative_overage_warning
                                else 0.0
                            ),
                            disclaimer=disclaimer_lines,
                            extra_charges_disclaimers=disclaimer_lines,
                        )
                    ),
                )
            
            hash = generate_trip_hash(option.model_dump(), search_in.model_dump())  # Generate hash for the option
            option.hash = hash  # Attach the generated hash to the option
            options.append(
                option
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
            .filter(AirportCabPricing.is_available_in_network == True)  # Ensure only available cabs are considered
            .all()
        )
        package_short_label = "Airport Drop"
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
            package_label = f"{package_short_label} | AC {cab_type_schema.name} - ({fuel_type_schema.name})"
            price_breakdown = AirportPricingBreakdownSchema(
                base_fare=math.ceil(base_price),
                toll=math.ceil(toll),
                platform_fee=math.ceil(platform_fee_amount),
            )
            disclaimer_lines = get_airport_trips_disclaimer_lines(
                overage_amount_per_km, max_included_km
            )
            option=TripSearchOption(
                car_type=cab_type_schema.name,  # Use display name
                    fuel_type=fuel_type_schema.name,  # Use display name
                    total_price=math.ceil(
                        total_price_before_platform_fee + price_breakdown.platform_fee
                    ),
                    price_breakdown=price_breakdown,
                    package=package_label,
                    package_short_label=package_short_label,
                    overages=(
                        OveragesSchema(
                            indicative_overage_warning=indicative_overage_warning,
                            overage_amount_per_km=(
                                overage_amount_per_km
                                if indicative_overage_warning
                                else 0.0
                            ),
                            overage_estimate_amount=(
                                math.ceil(overage_amount)
                                if indicative_overage_warning
                                else 0.0
                            ),
                            disclaimer=disclaimer_lines,
                            extra_charges_disclaimers=disclaimer_lines,
                        )
                    ))
            hash = generate_trip_hash(option.model_dump(), search_in.model_dump())  # Generate hash for the option
            option.hash = hash  # Attach the generated hash to the option
            options.append(option)
            
    elif search_in.trip_type == TripTypeEnum.local:
        _validate_local_trip_schedule(search_in)  # Validate local trip schedule
        _, _, _ = _get_trip_origin_destination_distance_local(search_in)
        inclusions, exclusions = _get_local_inclusions_exclusions()
        in_car_amenities.phone_charger = (
            True  # Always include phone charger for local trips
        )
        in_car_amenities.aux_cable = True  # Always include aux cable for local trips
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

        package_short_label = package.package_label
        package_label = f"{package_short_label} | AC {search_in.preferred_car_type} - ({search_in.preferred_fuel_type})"
        package_included_hours = package.included_hours
        package_included_km = package.included_km
        
        search_in.expected_end_date = validate_date_time(search_in.start_date) + timedelta(
            hours=package_included_hours
        )
        local_pricings = (
            db.query(LocalCabPricing, CabType, FuelType)
            .join(CabType, LocalCabPricing.cab_type_id == CabType.id)
            .join(FuelType, LocalCabPricing.fuel_type_id == FuelType.id)
            .filter(
                LocalCabPricing.is_available_in_network == True,)  # Ensure only available cabs are considered
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
                driver_allowance=(
                    math.ceil(package.driver_allowance)
                    if package.driver_allowance
                    else 0.0
                ),
            )
            # For local trips, we can't estimate distance in advance since routes are uncertain and hence no est_km is provided.
            # Overage charges will be initially presented as 0.00 and will be calculated only if the customer exceeds the included hours or km, to keep them informed through a disclaimer message that extra charges may apply at the end of the trip.
            overage_amount_per_km = pricing_schema.overage_amount_per_km
            overage_amount_per_hour = pricing_schema.overage_amount_per_hour
            disclaimer_lines = get_local_trips_disclaimer_lines(
                package_label=package.package_label,
                overage_amount_per_hour=overage_amount_per_hour,
                overage_amount_per_km=overage_amount_per_km,
                applicable_driver_allowance=price_breakdown.driver_allowance,
            )

            disclaimer_message = (
                "Extra charges may apply: " + "\n - " + "\n - ".join(disclaimer_lines)
            )
            option= TripSearchOption(
                    car_type=cab_type_schema.name,  # Use display name from schema
                    fuel_type=fuel_type_schema.name,  # Use display name from schema
                    total_price=math.ceil(
                        total_price_before_platform_fee + price_breakdown.platform_fee
                    ),
                    price_breakdown=price_breakdown,
                    included_hours=package_included_hours,
                    included_km=package_included_km,
                    package=package_label,  # Use package string for display
                    package_short_label=package_short_label,
                    overages=(
                        OveragesSchema(
                            disclaimer=disclaimer_message,
                            extra_charges_disclaimers=disclaimer_lines,
                        )
                    ),
                )
            hash = generate_trip_hash(option.model_dump(), search_in.model_dump())  # Generate hash for the option
            option.hash = hash  # Attach the generated hash to the option
            options.append(option)
             
            
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
        is_interstate, total_unique_states, unique_states = _track_state_transitions(search_in)
        inclusions, exclusions = _get_outstation_inclusions_exclusions(is_interstate)
        in_car_amenities.candies = True  # Candies are included for outstation trips
        in_car_amenities.phone_charger = (
            True  # Always include phone charger for outstation trips
        )
        in_car_amenities.aux_cable = (
            True  # Always include aux cable for outstation trips
        )
        in_car_amenities.bluetooth = (
            True  # Always include bluetooth for outstation trips
        )
        permit_fee = 0.0
        est_km = (
            2 * est_km
        )  # Always Round trip distance for outstation, therefore multiply by 2
        night_surcharge_per_hour = (
            configs.fixed_night_pricing.night_overage_amount_per_block
        )
        night_hours_display_label = configs.fixed_night_pricing.night_hours_label
        search_in.expected_end_date = search_in.end_date
        # Fetch all outstation cab pricings
        outstation_pricings = (
            db.query(OutstationCabPricing, CabType, FuelType)
            .join(CabType, OutstationCabPricing.cab_type_id == CabType.id)
            .join(FuelType, OutstationCabPricing.fuel_type_id == FuelType.id)
            .filter(
                OutstationCabPricing.is_available_in_network == True, ) # Ensure only available cabs are considered
            .all()
        )
        for pricing, cab_type, fuel_type in outstation_pricings:
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
            package_short_label = (
                f"{max(est_km, included_km)} km | Round trip | ({total_trip_days} days)"
            )
            package_label = f"{package_short_label} - AC {cab_type_schema.name} - ({fuel_type_schema.name})"

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
            disclaimer_lines = get_outstation_trips_disclaimer_lines(
                night_hours_display_label=night_hours_display_label,
                night_surcharge_per_hour=night_surcharge_per_hour,
            )
            disclaimer = "Extra charges may apply:\n - " + "\n - ".join(
                disclaimer_lines
            )
            option =  TripSearchOption(
                    car_type=cab_type_schema.name,
                    fuel_type=fuel_type_schema.name,
                    total_price=math.ceil(
                        total_price_before_platform_fee + platform_fee_amount
                    ),
                    price_breakdown=price_breakdown,
                    included_km=included_km,
                    package=package_label,
                    package_short_label=package_short_label,
                    overages=(
                        OveragesSchema(
                            indicative_overage_warning=indicative_overage_warning,
                            overage_amount_per_km=(
                                overage_amount_per_km
                                if indicative_overage_warning
                                else 0.0
                            ),
                            overage_estimate_amount=(
                                math.ceil(overage_amount)
                                if indicative_overage_warning
                                else 0.0
                            ),
                            disclaimer=disclaimer,
                            extra_charges_disclaimers=disclaimer_lines,
                        )
                    ),
                )
            
            
            hash = generate_trip_hash(option.model_dump(), search_in.model_dump())  # Generate hash for the option
            option.hash = hash  # Attach the generated hash to the option
            options.append(option)
           
            
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
    metadata=TripSearchAdditionalData(
        inclusions=inclusions,
        exclusions=exclusions,
        in_car_amenities=in_car_amenities,
        total_trip_days=total_trip_days,
        estimated_km=est_km,
        choices=len(_options),  # Total number of options returned
        is_round_trip=True,
        is_interstate=is_interstate,
        total_unique_states=total_unique_states,
        unique_states=unique_states if is_interstate else None,
        )
    return TripSearchResponse(
        options=_options,
        preferences=search_in,
        metadata=metadata,
    )


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
        "Premium AC cab experience with professional driver",
    ]
    exclusions = [
        "Personal expenses",
        "Self sponsored driver meals",
        "Tolls(if applicable)",
        "Extra parking(if any)",
    ]
    return inclusions, exclusions


def _get_default_amenities():
    return AmenitiesSchema(
        water_bottle=True,
        tissues=True,
        ac=True,
        music_system=True,
    )


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
        "Premium AC cab experience with professional driver",
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
            "Premium AC cab experience with professional driver",
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
            "Premium AC cab experience with professional driver",
        ]
    else:
        # If toll road is not preferred, we don't include toll charges
        # and hence we don't include it in the inclusions list
        inclusions = [
            "Base fare",
            "Water bottles and tissues",
            "Platform fee",
            "Premium AC cab experience with professional driver",
        ]

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
            "Premium AC cab experience with professional driver",
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
            "Premium AC cab experience with professional driver",
        ]
    elif not toll_road_preferred and placard_required:
        inclusions = [
            "Base fare",
            "Parking",
            "Platform fee",
            "Premium AC cab experience with professional driver",
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
            "Premium AC cab experience with professional driver",
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
    unique_states = set[str]()
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


def _validate_local_trip_schedule(search_in: TripSearchRequest):
    """
    Validates the start date and end date for local trips.
    Ensures that:
    - Start date is provided
    - Start date is not in the past
    - Start date is at least 3 hours from now
    Args:
        search_in (TripSearchRequest): The trip search request containing start date.
    Raises:
        CabboException: If any validation fails, with appropriate error messages.
    """
    if search_in.start_date is None:
        raise CabboException("Start date is required for local trip", status_code=400)
    # Parse and validate start_date
    start_date = validate_date_time(date_time=search_in.start_date)

    now = datetime.now(timezone.utc)
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)

    # Check for past dates
    if start_date < now:
        raise CabboException(
            "Start date for local trip cannot be in the past.", status_code=400
        )
    # Start date must be at least 6 hours after now
    min_start = now + timedelta(hours=6)
    if start_date < min_start:
        raise CabboException(
            "Start date for local trip must be at least 6 hours from now.",
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
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)

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
    # Start date must be at least 3 hours after now
    min_start = now + timedelta(hours=3)
    if start_date < min_start:
        raise CabboException(
            "Start date for outstation trip must be at least 3 hours from now.",
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
    if est_km<100:
        # Ensure that the estimated distance is at least 100 km for outstation trips
        raise CabboException(
            "Outstation trips must have a minimum distance of 100 km, the route you have selected is less than 100 km, try with a different route or switch to local trip",
            status_code=400,
        )

    return search_in.origin, search_in.destination, est_km


def _validate_serviceable_area(search_in: TripSearchRequest, db: Session):
    """
    Validates if the trip search request is within the serviceable area for the given trip type.
    Raises CabboException if the request is outside the serviceable area.
    """
    trip_type = search_in.trip_type
    # Query the serviceable area config for this trip type
    service_area = db.query(ServiceableGeographyOrm).join(
        TripTypeMaster, ServiceableGeographyOrm.trip_type_id == TripTypeMaster.id
    ).filter(ServiceableGeographyOrm.trip_type_id == TripTypeMaster.id, TripTypeMaster.trip_type==trip_type).first()
    if not service_area:
        raise CabboException(f"Serviceable area not configured for trip type: {trip_type}", status_code=500)

    # For local and airport trips, check city/airport
    if trip_type in [TripTypeEnum.local, TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        city_names = service_area.service_area_cities or []
        
        if not city_names:
            raise CabboException(
                f"Serviceable cities not configured for trip type: {trip_type}",
                status_code=500,
            )
        airport_place_ids = service_area.airport_place_ids or []
        # For local: check origin city
        if trip_type == TripTypeEnum.local:
            if not search_in.origin:
                raise CabboException("Origin is required for local trip", status_code=400)
            origin_city = getattr(search_in.origin, 'display_name', '').lower()
            message = f"Local trips are only serviceable in: {', '.join(city_names)}"
            context = f"The city '{origin_city}' you have selected for local trip is not serviceable, try again with a different city."
            if not any(city.lower() in origin_city for city in city_names):
                raise CabboException({
                    "message": message,
                    "context": context,
                }, status_code=400)
        
        #For airport drop, check origin city
        elif trip_type == TripTypeEnum.airport_drop:
            if not airport_place_ids:
                raise CabboException(
                    "Airport place IDs not configured for airport drop trips",
                    status_code=500,
                )
            if not search_in.origin:
                raise CabboException("Origin is required for airport drop", status_code=400)
            origin_city = getattr(search_in.origin, 'display_name', '').lower()
            if not any(city.lower() in origin_city for city in city_names):
                message = f"Airport drop trips are only serviceable in: {', '.join(city_names)}"
                context = f"The city '{origin_city}' you have selected for airport drop is not serviceable, try again with a different city."
                raise CabboException({
                    "message": message,
                    "context": context,
                }, status_code=400)
            airport_place_id = getattr(search_in.destination, 'place_id', None)
            if airport_place_id is not None and airport_place_id not in airport_place_ids:
                raise CabboException(f"Airport drop trips are only serviceable to: {', '.join(airport_place_ids)}", status_code=400)
        
        #For airport pickup, check destination city
        elif trip_type == TripTypeEnum.airport_pickup:
            if not airport_place_ids:
                raise CabboException(
                    "Airport place IDs not configured for airport pickup trips",
                    status_code=500,
                )
            if not search_in.destination:
                raise CabboException("Destination is required for airport pickup", status_code=400)
            dest_city = getattr(search_in.destination, 'display_name', '').lower()
            if not any(city.lower() in dest_city for city in city_names):
                message = f"Airport pickup trips are only serviceable in: {', '.join(city_names)}"
                context = f"The city '{dest_city}' you have selected for airport pickup is not serviceable, try again with a different city."
                raise CabboException({
                    message: message,
                   "context": context,
                    }, status_code=400)
            airport_place_id = getattr(search_in.origin, 'place_id', None)
            if airport_place_id is not None and airport_place_id not in airport_place_ids:
                raise CabboException(f"Airport pickup trips are only serviceable from: {', '.join(airport_place_ids)}", status_code=400)
        
    # For outstation, check state codes
    elif trip_type == TripTypeEnum.outstation:
        if not search_in.origin or not search_in.destination:
            raise CabboException("Origin and destination are required for outstation trip", status_code=400)
        origin_state = get_state_from_location(location=search_in.origin, state_code=True)
        allowed_states = service_area.service_area_state_codes or []
        if not origin_state:
            raise CabboException(f"This location is not servicable yet", status_code=400)
        if origin_state not in allowed_states:
            message = f"Outstation trips are only serviceable from: {', '.join(allowed_states)}"
            context = f"The origin state '{origin_state}' you have selected for outstation trip is not serviceable, try again with a different state."
            raise CabboException({
                "message": message,
                "context": context,
            }, status_code=400)
        dest_state = get_state_from_location(location=search_in.destination, state_code=True)
        if not dest_state:
            raise CabboException(f"This location is not servicable yet", status_code=400)
        if dest_state not in allowed_states:
                message = f"Outstation trips are only serviceable to: {', '.join(allowed_states)}"
                context = f"The destination state '{dest_state}' you have selected for outstation trip is not serviceable, try again with a different state."
                raise CabboException({
                    "message": message,
                    "context": context,
                }, status_code=400)
        if search_in.hops:
            invalid_hops = []
            for hop in search_in.hops:
                hop_state = get_state_from_location(location=hop, state_code=True)
                if not hop_state:
                    continue
                if hop_state not in allowed_states:
                    invalid_hops.append(hop_state)
            if invalid_hops:
                message = (
                    f"Outstation trips are only serviceable to: {', '.join(allowed_states)}."
                )
                context = f"One or more hops in your trip is not serviceable: {', '.join(invalid_hops)}, try again with different hops within serviceable states or remove them."
                raise CabboException(
                    {
                        "message": message,
                        "context": context,
                    },
                    status_code=400,
                )
                    
    else:
        # If the trip type is not supported, raise an exception
        raise CabboException(f"Trip type {trip_type} is not supported", status_code=501)
    
    print(f"Trip search request is within serviceable area for trip type: {trip_type}")

def _verify_trip_hash(booking_request: TripBookRequest):
    if not booking_request.option or not booking_request.option.hash:
        raise CabboException("Invalid booking request, option hash is required", status_code=400)
    if not booking_request.preferences:
        raise CabboException("Invalid booking request, preferences are required", status_code=400)
    # Validate the trip option hash
    if not verify_trip_hash(option=booking_request.option.model_dump(), preferences=booking_request.preferences.model_dump(), client_hash=booking_request.option.hash):
        raise CabboException("Invalid booking request, option hash is not valid", status_code=400)

def _validate_duplicate_local_bookings(booking_request: TripBookRequest, requestor: str, db: Session, overlap_hours: int = 24):
        start_date = validate_date_time(date_time=booking_request.preferences.start_date)
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        end_date = start_date + timedelta(hours=overlap_hours)  # Check for bookings within the next 24 hours
        existing_bookings = db.query(Trip).join(TripTypeMaster).filter(
            Trip.trip_type_id == TripTypeMaster.id,
            Trip.creator_id == requestor,
            Trip.start_datetime >= start_date,
            Trip.start_datetime <= end_date,
            Trip.status != TripStatusEnum.cancelled
        ).all()
        if existing_bookings:
            raise CabboException("You already have a booking for this time slot", status_code=400)

def _validate_duplicate_outstation_bookings(booking_request: TripBookRequest, requestor: str, db: Session):
        start_date = validate_date_time(date_time=booking_request.preferences.start_date)
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        end_date = validate_date_time(date_time=booking_request.preferences.end_date)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        existing_bookings = (
            db.query(Trip)
            .join(TripTypeMaster)
            .filter(
                Trip.trip_type_id == TripTypeMaster.id,
                Trip.creator_id == requestor,
                Trip.status != TripStatusEnum.cancelled,
                Trip.start_datetime < end_date,
                Trip.end_datetime > start_date,
            )
            .all()
        )
        if existing_bookings:
            raise CabboException("You already have a booking for this time slot", status_code=400)

def _validate_airport_bookings(booking_request: TripBookRequest, requestor: str, db: Session, overlap_hours: int = 6):
        start_date = validate_date_time(date_time=booking_request.preferences.start_date)
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        end_date = start_date + timedelta(hours=overlap_hours)  # Check for bookings within the next 6 hours
        existing_bookings = db.query(Trip).join(TripTypeMaster).filter(
            Trip.trip_type_id == TripTypeMaster.id,
            Trip.creator_id == requestor,
            Trip.start_datetime >= start_date,  
            Trip.start_datetime <= end_date,
            Trip.status != TripStatusEnum.cancelled
        ).all()
        if existing_bookings:
            raise CabboException("You already have a booking for this time slot", status_code=400)

def _validate_booking_request(booking_request: TripBookRequest, requestor: str, db: Session):
    # case 1: If the trip is local, check for existing bookings for the same customer with the same start date within the next 24 hours
    
    if booking_request.preferences.trip_type == TripTypeEnum.local:
        _validate_duplicate_local_bookings(booking_request=booking_request, requestor=requestor, db=db)
    
    # case 2: If the trip is outstation, check for existing bookings for the same customer between the start and end dates

    elif booking_request.preferences.trip_type == TripTypeEnum.outstation:
        _validate_duplicate_outstation_bookings(booking_request=booking_request, requestor=requestor, db=db)
    
    # case 3: If the trip is airport pickup or drop, check for existing bookings for the same customer with the same start date within the next 6 hours
    elif booking_request.preferences.trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        _validate_airport_bookings(booking_request=booking_request, requestor=requestor, db=db)

    else:
        raise CabboException(f"Trip type {booking_request.preferences.trip_type} is not supported for booking", status_code=501)

def _get_trip_type_id_by_trip_type(trip_type: TripTypeEnum, db: Session) -> str:
    """
    Retrieves the trip type ID from the database based on the provided trip type.
    Args:
        trip_type (TripTypeEnum): The trip type for which to retrieve the ID.
        db (Session): The database session for ORM operations.
    Returns:
        str: The ID of the trip type.
    Raises:
        CabboException: If the trip type is not found in the database.
    """
    trip_type_obj = db.query(TripTypeMaster).filter(TripTypeMaster.trip_type == trip_type).first()
    if not trip_type_obj:
        raise CabboException(f"Trip type {trip_type} not found", status_code=404)
    return trip_type_obj.id

def _delete_temp_trip(requestor: str, db: Session):
    """
    Deletes all temporary trip details for the given requestor.
    Args:
        requestor (str): The user or system initiating the deletion.
        db (Session): The database session for ORM operations.
    """
    try:
        db.query(TempTrip).filter(TempTrip.creator_id == requestor).delete()
        print(f"Temporary trip details deleted for requestor: {requestor}")
    except Exception as e:
        raise CabboException(f"Failed to delete temporary trip details: {str(e)}", status_code=500)

def _calculate_expected_end_datetime(trip_type: TripTypeEnum, start_date: datetime, end_date: datetime, db:Session, package_id: str = None) -> datetime:
    """
    Calculates the expected end datetime for a trip based on the trip type, start date, end date, and package ID.
    Args:
        trip_type (TripTypeEnum): The type of trip (local, outstation, airport).
        start_date (datetime): The start date of the trip.
        end_date (datetime): The end date of the trip.
        package_id (str): The package ID if applicable.
    Returns:
        datetime: The expected end datetime for the trip.
    """
    if trip_type == TripTypeEnum.local:
        # For local trips, retrieve the package duration if available, otherwise default to 6 hours
        if package_id:
            package = _retrieve_trip_package_by_id(package_id=package_id, db=db)
            if package and package.included_hours:
                return start_date + timedelta(hours=package.included_hours)
        return start_date + timedelta(hours=4)  # Default to 4 hours for local trips
    
    elif trip_type == TripTypeEnum.outstation:
        # For outstation trips, use the provided end date
        return end_date
    
    elif trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        # For airport trips, we can assume a short duration
        return start_date + timedelta(hours=1)  # Default to 1 hour for airport trips
    else:
        raise CabboException(f"Trip type {trip_type} is not supported for expected end datetime calculation", status_code=501)

def _get_total_num_luggages(booking_request: TripBookRequest) -> int:
    """
    Calculates the total number of luggages based on the booking request.
    Args:
        booking_request (TripBookRequest): The trip booking request containing luggage details.
    Returns:
        int: The total number of luggages.
    """
    return (
        booking_request.preferences.num_large_suitcases
        + booking_request.preferences.num_carryons
        + booking_request.preferences.num_backpacks
        + booking_request.preferences.num_other_bags
    )

def _get_tolls_estimate(booking_request: TripBookRequest) -> float:
    """
    Calculates the estimated tolls for the trip based on the booking request.
    Args:
        booking_request (TripBookRequest): The trip booking request containing toll details.
    Returns:
        float: The estimated tolls for the trip.
    """
    if booking_request.preferences.trip_type == TripTypeEnum.local:
        # For local trips, tolls are not applicable
        return 0.0
    elif booking_request.preferences.trip_type == TripTypeEnum.outstation:
        # For outstation trips, use the tolls estimate from the request if available
        return booking_request.option.price_breakdown.minimum_toll_wallet if booking_request.option.price_breakdown.minimum_toll_wallet  else 0.0
    elif booking_request.preferences.trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        # For airport trips, use the tolls estimate from the request if available
        return booking_request.option.price_breakdown.toll if booking_request.preferences.toll_road_preferred and  booking_request.option.price_breakdown.toll else 0.0
    else:
        raise CabboException(f"Trip type {booking_request.preferences.trip_type} is not supported for tolls estimation", status_code=501)

def _get_parking_estimate(booking_request: TripBookRequest) -> float:
    """
    Calculates the estimated parking charges for the trip based on the booking request.
    Args:
        booking_request (TripBookRequest): The trip booking request containing parking details.
    Returns:
        float: The estimated parking charges for the trip.
    """
    if booking_request.preferences.trip_type == TripTypeEnum.local:
        # For local trips, parking is not applicable
        return booking_request.option.price_breakdown.minimum_parking_wallet if booking_request.option.price_breakdown.minimum_parking_wallet else 0.0
    elif booking_request.preferences.trip_type == TripTypeEnum.outstation:
        # For outstation trips, use the parking estimate from the request if available
        return booking_request.option.price_breakdown.minimum_parking_wallet if booking_request.option.price_breakdown.minimum_parking_wallet else 0.0
    elif booking_request.preferences.trip_type ==TripTypeEnum.airport_pickup:
        # For airport pickup, use the parking estimate from the request if available
        return booking_request.option.price_breakdown.parking if booking_request.option.price_breakdown.parking else 0.0
    else:
        return 0.0  # For airport drop, parking is not applicable

def _create_temporary_trip(booking_request: TripBookRequest, requestor: str, db: Session) -> TempTrip:
    """
    
    Creates a temporary trip record in the database based on the booking request.
    This function validates the booking request, calculates necessary fields, and stores the trip details.
    Args:
        booking_request (TripBookRequest): The trip booking request containing preferences and options.
        requestor (str): The user or system initiating the trip creation.
        db (Session): The database session for ORM operations.
    Returns:
        TempTrip: The created temporary trip record.
    Raises:
        CabboException: If the booking request is invalid or if any database operation fails.
    """
    trip_type_id = _get_trip_type_id_by_trip_type(booking_request.preferences.trip_type, db=db)
    validated_start_date = validate_date_time(date_time=booking_request.preferences.start_date)
    if validated_start_date.tzinfo is None:
        validated_start_date = validated_start_date.replace(tzinfo=timezone.utc)
    validated_end_date = None
    if booking_request.preferences.end_date:
        validated_end_date = validate_date_time(date_time=booking_request.preferences.end_date)
        if validated_end_date.tzinfo is None:
            validated_end_date = validated_end_date.replace(tzinfo=timezone.utc)
    
    temp_trip = TempTrip(
        creator_id=requestor,
        trip_type_id=trip_type_id,
        origin_display_name=booking_request.preferences.origin.display_name,
        origin_lat=booking_request.preferences.origin.lat,
        origin_lng=booking_request.preferences.origin.lng,
        origin_place_id=booking_request.preferences.origin.place_id,
        origin_address=booking_request.preferences.origin.address,
        destination_display_name=booking_request.preferences.destination.display_name,
        destination_lat=booking_request.preferences.destination.lat,
        destination_lng=booking_request.preferences.destination.lng,
        destination_place_id=booking_request.preferences.destination.place_id,
        destination_address=booking_request.preferences.destination.address,
        hops=booking_request.preferences.hops if booking_request.preferences.hops else None,
        is_interstate=booking_request.metadata.is_interstate if booking_request.preferences.trip_type == TripTypeEnum.outstation else False,
        total_unique_states=booking_request.metadata.total_unique_states if booking_request.preferences.trip_type == TripTypeEnum.outstation else None,
        unique_states=booking_request.metadata.unique_states if booking_request.preferences.trip_type == TripTypeEnum.outstation else None,
        package_id=booking_request.preferences.package_id if booking_request.preferences.package_id else None,
        package_label=booking_request.option.package if booking_request.option.package else None,
        package_label_short=booking_request.option.package_short_label if booking_request.option.package_short_label else None,
        start_datetime=validated_start_date,
        end_datetime=validated_end_date,
        expected_end_datetime=_calculate_expected_end_datetime(booking_request.preferences.trip_type, validated_start_date, validated_end_date, db, booking_request.preferences.package_id),
        total_days=booking_request.metadata.total_trip_days if booking_request.metadata.total_trip_days else None,
        num_adults=booking_request.preferences.num_adults,
        num_children=booking_request.preferences.num_children,
        num_large_suitcases=booking_request.preferences.num_large_suitcases,
        num_carryons=booking_request.preferences.num_carryons,
        num_backpacks=booking_request.preferences.num_backpacks,
        num_other_bags=booking_request.preferences.num_other_bags,
        num_luggages=_get_total_num_luggages(booking_request=booking_request),
        preferred_car_type=booking_request.preferences.preferred_car_type,
        preferred_fuel_type=booking_request.preferences.preferred_fuel_type,
        in_car_amenities=booking_request.metadata.in_car_amenities.model_dump() if booking_request.metadata.in_car_amenities else None,
        price_breakdown=booking_request.option.price_breakdown.model_dump() if booking_request.option.price_breakdown else None,
        overages=booking_request.option.overages.model_dump() if booking_request.option.overages else None,
        base_fare=booking_request.option.price_breakdown.base_fare,
        driver_allowance=booking_request.option.price_breakdown.driver_allowance if  booking_request.option.price_breakdown.driver_allowance else 0.0,
        tolls_estimate=_get_tolls_estimate(booking_request=booking_request),
        parking_estimate=_get_parking_estimate(booking_request=booking_request),
        permit_fee=booking_request.option.price_breakdown.permit_fee if booking_request.metadata.is_interstate and booking_request.option.price_breakdown.permit_fee else 0.0,
        platform_fee=booking_request.option.price_breakdown.platform_fee if booking_request.option.price_breakdown.platform_fee else 0.0,
        final_price=booking_request.option.total_price,
        final_display_price=(booking_request.option.total_price - booking_request.option.price_breakdown.platform_fee) ,
        inclusions=booking_request.metadata.inclusions if booking_request.metadata.inclusions else None,
        exclusions=booking_request.metadata.exclusions if booking_request.metadata.exclusions else None,
        flight_number=booking_request.preferences.flight_number if booking_request.preferences.flight_number else None,
        terminal_number=booking_request.preferences.terminal_number if booking_request.preferences.terminal_number else None,
        toll_road_preferred=booking_request.preferences.toll_road_preferred if booking_request.preferences.toll_road_preferred else False,
        placard_required=booking_request.preferences.placard_required if booking_request.preferences.placard_required else False,
        placard_name=booking_request.preferences.placard_name if booking_request.preferences.placard_name else None,
        estimated_km=booking_request.metadata.estimated_km if booking_request.metadata.estimated_km else 0.0,
        indicative_overage_warning=booking_request.option.overages.indicative_overage_warning if booking_request.option.overages.indicative_overage_warning else None,
        alternate_customer_phone=None,
        passenger_id=booking_request.preferences.passenger.id if booking_request.preferences.passenger and booking_request.preferences.passenger.id else None,
    )
    try:
        db.add(temp_trip)
        db.commit()
        db.refresh(temp_trip)
        print(f"Temporary trip created for requestor: {requestor}")
    except Exception as e:
        db.rollback()
        raise CabboException(f"Failed to create temporary trip: {str(e)}", status_code=500)

def initiate_booking(booking_request:TripBookRequest, requestor:str, db:Session):

    """
    Initiates a booking for a trip based on the provided booking request.
    Args:
        booking_request (TripBookRequest): The trip booking request containing trip details.
        requestor (str): The user or system initiating the booking.
        db (Session): The database session for ORM operations.
    Returns:
        TripBookResponse: The response containing booking details.
    Raises:
        CabboException: If the booking request is invalid or if any error occurs during booking.

    """
    # Verify the trip_in.option.hash, if not valid (tampered), raise exception and return error response
    _verify_trip_hash(booking_request=booking_request)
    
    # Check for duplicate or conflicting bookings for the same customer.
    _validate_booking_request(booking_request=booking_request, requestor=requestor, db=db)

    #Delete all previous temporary trip details for the customer
    _delete_temp_trip(requestor=requestor, db=db)

    # Create a new Temp Trip object from the booking request
    _create_temporary_trip(booking_request=booking_request, requestor=requestor, db=db)

    # Create razor pay order for the trip
    