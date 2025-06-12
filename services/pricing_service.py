from typing import List, Set

from sqlalchemy import any_
from models.cab.pricing_schema import (
    AirportCabPricingSchema,
    AirportPricingBreakdownSchema,
    CommonPricingConfigSchema,
    LocalCabPricingSchema,
    LocalPricingBreakdownSchema,
    OutstationCabPricingSchema,
    OveragesSchema,
    CabTypeSchema,
    FuelTypeSchema,
    OutstationPricingBreakdownSchema,
)
from models.geography.state_orm import GeoStateModel
from models.geography.state_schema import GeoStateOut
from models.trip.trip_orm import TripTypeMaster
from models.trip.trip_schema import (
    TripSearchRequest,
    TripSearchOption,
    TripSearchResponse,
)
from sqlalchemy.orm import Session
from models.cab.pricing_orm import (
    CabType,
    CommonPricingConfiguration,
    FixedPlatformPricing,
    FuelType,
    AirportCabPricing,
    LocalCabPricing,
    OutstationCabPricing,
    FixedPlatformPricing,
)
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripTypeEnum
from core.exceptions import CabboException
from services.location_service import get_distance_km, get_state_from_location
from models.geography.geo_enums import APP_AIRPORT_LOCATION
from core.constants import APP_HOME_STATE
from datetime import datetime, timezone, timedelta
import math

from utils.utility import validate_date_time


def _retrieve_interstate_permit_fee(unique_states: List[str], db: Session):
    """
    Calculates and returns the total interstate permit fee for a list of unique states crossed during a trip.

    This method is used for outstation/interstate trips to determine the total permit fees that must be charged
    based on all unique states crossed (case-insensitive). It fetches the permit fee for each state from the
    database and sums them up. If no states are provided, returns 0.0. If any state is not found, raises an error.

    Args:
        unique_states (List[str]): List of unique state names (case-insensitive) crossed during the trip.
        db (Session): SQLAlchemy database session for ORM queries.

    Returns:
        float: The total permit fee for all unique states crossed.

    Raises:
        CabboException: If any of the provided states are not found in the database.
    """
    # For interstate trips, we need to consider permit fees
    # Convert all unique_states to lower case for matching
    unique_states_lower = [s.lower() for s in unique_states]
    if not unique_states_lower:
        return 0.0  # No states means no permit fee
    permit_fee = 0.0
    # Fetch all states that match the unique states
    all_states = (
        db.query(GeoStateModel)
        .filter(GeoStateModel.state_name.ilike(any_(unique_states_lower)))
        .all()
    )
    if not all_states:
        raise CabboException(
            "Could not find states for the given interstate locations", status_code=400
        )
    for state in all_states:
        if state.permit_fee:
            temp_permit_fee = GeoStateOut.model_validate(state).permit_fee
            permit_fee += temp_permit_fee

    return permit_fee


def _retrieve_trip_wise_pricing_config(
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
    return (
        common_pricing_config  # CommonPricingConfigSchema including fixed platform fee
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
    options: List[TripSearchOption] = []
    configs = _retrieve_trip_wise_pricing_config(db, search_in.trip_type)
    platform_fee_percent = configs.dynamic_platform_fee_percent
    toll = 0.0
    parking = 0.0

    if search_in.trip_type == TripTypeEnum.airport_pickup:  # from airport
        _, _, est_km = _get_trip_origin_destination_distance_airport_pickup(search_in)
        parking = configs.parking if configs.parking is not None else 0.0
        toll = (
            configs.toll
            if search_in.toll_road_preferred and configs.toll is not None
            else 0.0
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
        _, _, est_km = _get_trip_origin_destination_distance_airport_drop(search_in)
        toll = (
            configs.toll
            if search_in.toll_road_preferred and configs.toll is not None
            else 0.0
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
        minimum_toll = toll
        minimum_parking = (
            configs.minimum_parking if configs.minimum_parking is not None else 0.0
        )
        duration = search_in.duration_hours or configs.min_included_hours
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
            min_included_hours = configs.min_included_hours
            if not duration:
                duration = min_included_hours  # Ensure duration is at least the minimum included hours
            max_included_hours = configs.max_included_hours
            overage_amount_per_hour = pricing_schema.overage_per_hour
            base_hours = min(duration, max_included_hours)
            num_overage_hours = max(0, duration - max_included_hours)
            base_fare = hourly_rate * base_hours
            overage_amount = overage_amount_per_hour * num_overage_hours
            total_price_before_platform_fee = (
                base_fare + minimum_toll + minimum_parking + overage_amount
            )

            # Platform fee is a sum of a fixed cost to service and a percentage of the total price calculated before adding platform fee
            platform_fee_amount = configs.fixed_platform_fee + (
                platform_fee_percent * total_price_before_platform_fee / 100
            )

            price_breakdown = LocalPricingBreakdownSchema(
                base_fare=math.ceil(base_fare),
                minimum_toll=math.ceil(minimum_toll),
                minimum_parking=math.ceil(minimum_parking),
                platform_fee=math.ceil(platform_fee_amount),
            )
            indicative_overage_warning = duration > max_included_hours
            options.append(
                TripSearchOption(
                    car_type=cab_type_schema.name,  # Use display name from schema
                    fuel_type=fuel_type_schema.name,  # Use display name from schema
                    total_price=math.ceil(
                        total_price_before_platform_fee + price_breakdown.platform_fee
                    ),
                    price_breakdown=price_breakdown,
                    estimated_hours=duration,
                    overages=(
                        OveragesSchema(
                            indicative_overage_warning=indicative_overage_warning,
                            overage_amount_per_hour=(
                                overage_amount_per_hour
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
    elif search_in.trip_type == TripTypeEnum.outstation:
        _, _, est_km = _get_trip_origin_destination_distance_outstation(search_in)
        total_trip_days = _validate_outstation_schedule(search_in)

        minimum_toll = configs.minimum_toll if configs.minimum_toll is not None else 0.0
        minimum_parking = (
            configs.minimum_parking if configs.minimum_parking is not None else 0.0
        )

        # Identify unique state borders crossed (including between hops)
        is_interstate, _, unique_states = _track_state_transitions(search_in)
        permit_fee = 0.0
        est_km = (
            2 * est_km
        )  # Always Round trip distance for outstation, therefore multiply by 2
        if is_interstate:
            permit_fee = _retrieve_interstate_permit_fee(
                unique_states, db
            )  # Permit fee for interstate roundtrips is charged only once per state gate during entry(for entry and exit)
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

            # Total before platform fee
            total_price_before_platform_fee = (
                base_price
                + driver_allowance_amount
                + minimum_toll
                + minimum_parking
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
                minimum_toll=math.ceil(minimum_toll),
                minimum_parking=math.ceil(minimum_parking),
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
    return TripSearchResponse(options=options, preferences=search_in)


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


def _validate_outstation_schedule(search_in: TripSearchRequest):
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
    end_date = validate_date_time(date_time=search_in.end_date)

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
