from typing import List, Set

from sqlalchemy import any_
from models.cab.pricing_schema import (
    AirportCabPricingSchema,
    AirportPricingBreakdownSchema,
    FixedPlatformPricingConfigSchema,
    LocalCabPricingSchema,
    LocalPricingBreakdownSchema,
    OutstationCabPricingSchema,
    OverageWarningConfigSchema,
    TollParkingConfigSchema,
    PlatformPricingConfigSchema,
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
    TripTypeWiseConfig,
)
from sqlalchemy.orm import Session
from models.cab.pricing_orm import (
    CabType,
    FixedPlatformPricingConfig,
    FuelType,
    AirportCabPricing,
    LocalCabPricing,
    OutstationCabPricing,
    PlatformPricingConfig,
)
from models.trip.trip_enums import CarTypeEnum, TripTypeEnum
from core.exceptions import CabboException
from services.location_service import get_distance_km, get_state_from_location
from models.geography.geo_enums import APP_AIRPORT_LOCATION
from core.constants import APP_HOME_STATE
from models.cab.pricing_orm import OverageWarningConfig, TollParkingConfig
from datetime import datetime, timezone, timedelta
import math

from utils.utility import validate_date_time


def retrieve_interstate_permit_fee(unique_states: List[str], db: Session):
    # For interstate trips, we need to consider permit fees
    # Convert all unique_states to lower case for matching
    unique_states_lower = [s.lower() for s in unique_states]
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


def retrieve_trip_type_wise_common_pricing_config(
    db: Session, trip_type: TripTypeEnum
) -> TripTypeWiseConfig:
    """
    Returns a TripTypeWiseConfig object with warning_config, toll_parking_charge, platform_fee_config and fixed_platform_fee_config for the given trip_type.
    """
    trip_type_object = db.query(TripTypeMaster).filter_by(trip_type=trip_type).first()
    if not trip_type_object:
        raise CabboException("Invalid trip type", status_code=400)

    trip_type_id = trip_type_object.id
    warning_config_orm = (
        db.query(OverageWarningConfig).filter_by(trip_type_id=trip_type_id).first()
    )
    toll_parking_charge_orm = (
        db.query(TollParkingConfig).filter_by(trip_type_id=trip_type_id).first()
    )
    platform_fee_config_orm = (
        db.query(PlatformPricingConfig)
        .join(TripTypeMaster, PlatformPricingConfig.trip_type_id == TripTypeMaster.id)
        .filter(TripTypeMaster.id == trip_type_id)
        .first()
    )
    fixed_platform_fee_config_orm = db.query(FixedPlatformPricingConfig).first()

    warning_config = (
        OverageWarningConfigSchema.model_validate(warning_config_orm)
        if warning_config_orm
        else None
    )
    toll_parking_charge = (
        TollParkingConfigSchema.model_validate(toll_parking_charge_orm)
        if toll_parking_charge_orm
        else None
    )
    platform_fee_config = (
        PlatformPricingConfigSchema.model_validate(platform_fee_config_orm)
        if platform_fee_config_orm
        else None
    )

    fixed_platform_fee_config = (
        FixedPlatformPricingConfigSchema.model_validate(fixed_platform_fee_config_orm)
        if fixed_platform_fee_config_orm
        else None
    )

    return TripTypeWiseConfig(
        warning_config=warning_config,
        toll_parking_charge=toll_parking_charge,
        platform_fee_config=platform_fee_config,
        fixed_platform_fee_config=fixed_platform_fee_config,
    )


def get_trip_search_options(search_in: TripSearchRequest, db: Session) -> list:
    options: List[TripSearchOption] = []
    configs = retrieve_trip_type_wise_common_pricing_config(db, search_in.trip_type)
    warning_config = configs.warning_config  # OverageWarningConfigSchema
    toll_parking_charge = configs.toll_parking_charge  # TollParkingConfigSchema
    platform_fee_config = configs.platform_fee_config  # PlatformPricingConfigSchema
    fixed_platform_fee_config = (
        configs.fixed_platform_fee_config
    )  # FixedPlatformPricingConfigSchema

    platform_fee_percent = (
        platform_fee_config.platform_fee_percent if platform_fee_config else 0
    )

    toll = 0.0
    parking = 0.0
    if search_in.trip_type == TripTypeEnum.airport_pickup:  # from airport
        _, _, est_km = get_trip_origin_destination_distance_airport_pickup(search_in)
        parking = toll_parking_charge.parking if toll_parking_charge else 0.0
        toll = (
            toll_parking_charge.toll
            if search_in.toll_road_preferred and toll_parking_charge
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
            max_included_km = pricing_schema.max_included_km
            overage_amount_per_km = pricing_schema.overage_amount_per_km
            placard_charge = (
                pricing_schema.placard_charge if search_in.placard_required else 0.0
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
            warning_km_threshold = warning_config.warning_km_threshold
            margin = max_included_km - est_km  # Allow negative values for overage
            indicative_overage_warning = margin <= warning_km_threshold
            # Platform fee is a sum of a fixed cost to service fee and a percentage of the total price calculated before adding platform fee
            platform_fee_amount = fixed_platform_fee_config.fixed_platform_fee + (
                platform_fee_percent * total_price_before_platform_fee / 100
            )
            price_breakdown = AirportPricingBreakdownSchema(
                base_fare=math.ceil(base_price),
                placard_charge=math.ceil(placard_charge),
                tolls_estimate=math.ceil(toll),
                parking_estimate=math.ceil(parking),
                platform_fee=math.ceil(platform_fee_amount),
                overage_amount_per_km=(
                    overage_amount_per_km if indicative_overage_warning else 0.0
                ),
                overage_estimate=(
                    math.ceil(overage_amount) if indicative_overage_warning else 0.0
                ),
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
                    indicative_overage_warning=indicative_overage_warning,
                )
            )

    elif search_in.trip_type == TripTypeEnum.airport_drop:  # to airport
        _, _, est_km = get_trip_origin_destination_distance_airport_drop(search_in)
        toll = (
            toll_parking_charge.toll
            if search_in.toll_road_preferred and toll_parking_charge
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
            max_included_km = pricing_schema.max_included_km
            overage_amount_per_km = pricing_schema.overage_amount_per_km
            base_price = base_fare_per_km * min(est_km, max_included_km)
            overage_amount = max(0, est_km - max_included_km) * overage_amount_per_km
            # Total price includes base fare, toll and parking charges (if any)
            # We wont add the overage charge to the total price for airport pickups because overages is an estimation and not a fixed charge
            # Overages will apply if at the end of the trip the actual distance is more than the estimated distance
            # This indicator is to ensure that the customer is aware that overage charges may apply for this route
            total_price_before_platform_fee = math.ceil(base_price + toll + parking)
            warning_km_threshold = warning_config.warning_km_threshold
            margin = max_included_km - est_km  # Allow negative values for overage
            indicative_overage_warning = margin <= warning_km_threshold
            # Platform fee is a sum of a fixed cost to service fee and a percentage of the total price calculated before adding platform fee
            platform_fee_amount = fixed_platform_fee_config.fixed_platform_fee + (
                platform_fee_percent * total_price_before_platform_fee / 100
            )

            price_breakdown = AirportPricingBreakdownSchema(
                base_fare=math.ceil(base_price),
                tolls_estimate=math.ceil(toll),
                parking_estimate=0.0,  # Parking is not applicable for airport drop
                platform_fee=math.ceil(platform_fee_amount),
                overage_amount_per_km=(
                    overage_amount_per_km if indicative_overage_warning else 0.0
                ),
                overage_estimate=(
                    math.ceil(overage_amount) if indicative_overage_warning else 0.0
                ),
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
                    indicative_overage_warning=indicative_overage_warning,
                )
            )
    elif search_in.trip_type == TripTypeEnum.local:
        _, _, _ = get_trip_origin_destination_distance_local(search_in)
        minimum_toll = toll
        minimum_parking = (
            toll_parking_charge.minimum_parking if toll_parking_charge else 0.0
        )
        duration = search_in.duration_hours or 4
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
            min_included_hours = pricing_schema.min_included_hours
            if not duration:
                duration = min_included_hours  # Ensure duration is at least the minimum included hours
            max_included_hours = pricing_schema.max_included_hours
            overage_amount_per_hour = pricing_schema.overage_amount_per_hour
            base_hours = min(duration, max_included_hours)
            num_overage_hours = max(0, duration - max_included_hours)
            base_fare = hourly_rate * base_hours
            overage_amount = overage_amount_per_hour * num_overage_hours
            total_price_before_platform_fee = (
                base_fare + minimum_toll + minimum_parking + overage_amount
            )

            # Platform fee is a sum of a fixed cost to service fee and a percentage of the total price calculated before adding platform fee
            platform_fee_amount = fixed_platform_fee_config.fixed_platform_fee + (
                platform_fee_percent * total_price_before_platform_fee / 100
            )

            price_breakdown = LocalPricingBreakdownSchema(
                base_fare=math.ceil(base_fare),
                tolls_estimate=math.ceil(minimum_toll),
                parking_estimate=math.ceil(minimum_parking),
                platform_fee=math.ceil(platform_fee_amount),
                overage_amount_per_hour=(
                    overage_amount_per_hour if duration > max_included_hours else 0.0
                ),
                overage_estimate=(
                    math.ceil(overage_amount) if duration > max_included_hours else 0.0
                ),
            )
            options.append(
                TripSearchOption(
                    car_type=cab_type_schema.name,  # Use display name from schema
                    fuel_type=fuel_type_schema.name,  # Use display name from schema
                    total_price=math.ceil(
                        total_price_before_platform_fee + price_breakdown.platform_fee
                    ),
                    price_breakdown=price_breakdown,
                    estimated_hours=duration,
                    indicative_overage_warning=duration > max_included_hours,
                )
            )
    elif search_in.trip_type == TripTypeEnum.outstation:
        _, _, est_km = get_trip_origin_destination_distance_outstation(search_in)
        total_trip_days = validate_outstation_schedule(search_in)

        minimum_toll = toll_parking_charge.minimum_toll if toll_parking_charge else 0.0
        minimum_parking = (
            toll_parking_charge.minimum_parking if toll_parking_charge else 0.0
        )

        # Identify unique state borders crossed (including between hops)
        is_interstate, total_unique_states, unique_states = track_state_transitions(
            search_in
        )
        permit_fee = 0.0
        est_km = 2 * est_km  # Always Round trip distance for outstation
        if is_interstate:
            permit_fee = retrieve_interstate_permit_fee(
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
            pricing_schema = OutstationCabPricingSchema.model_validate(pricing)
            cab_type_schema = CabTypeSchema.model_validate(cab_type)
            fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
            base_fare_per_km = pricing_schema.base_fare_per_km
            min_included_km_per_day = pricing_schema.min_included_km_per_day
            overage_amount_per_km = pricing_schema.overage_amount_per_km
            driver_allowance_per_day = pricing_schema.driver_allowance_per_day
            # Calculate total trip days
            included_km = min_included_km_per_day * total_trip_days
            base_price = base_fare_per_km * included_km
            overage_km = max(0, est_km - included_km)
            overage_amount = overage_km * overage_amount_per_km
            driver_allowance = driver_allowance_per_day * total_trip_days
            # Total before platform fee
            total_price_before_platform_fee = (
                base_price
                + driver_allowance
                + minimum_toll
                + minimum_parking
                + permit_fee
                + overage_amount
            )
            platform_fee_amount = fixed_platform_fee_config.fixed_platform_fee + (
                platform_fee_percent * total_price_before_platform_fee / 100
            )
            price_breakdown = OutstationPricingBreakdownSchema(
                base_fare=math.ceil(base_price),
                driver_allowance=math.ceil(driver_allowance),
                tolls_estimate=math.ceil(minimum_toll),
                parking_estimate=math.ceil(minimum_parking),
                permit_fee=math.ceil(permit_fee) if permit_fee else 0.0,
                overage_estimate=math.ceil(overage_amount) if overage_amount else 0.0,
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
                    estimated_km=est_km,
                    indicative_overage_warning=overage_km > 0,
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
    return _options


def track_state_transitions(search_in: TripSearchRequest):
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


def validate_outstation_schedule(search_in: TripSearchRequest):
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


def get_trip_origin_destination_distance_airport_pickup(search_in: TripSearchRequest):
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


def get_trip_origin_destination_distance_airport_drop(search_in: TripSearchRequest):
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


def get_trip_origin_destination_distance_local(search_in: TripSearchRequest):
    if not search_in.origin:
        raise CabboException("Origin is required for local trip", status_code=400)

    if not search_in.destination:
        search_in.destination = (
            search_in.origin
        )  # For local trips, origin and destination can be the same if not specified

    return (
        search_in.origin,
        search_in.destination,
        0.0,
    )  # Local trips don't require distance estimation as they are hourly based, can be 0 or any default value


def get_trip_origin_destination_distance_outstation(search_in: TripSearchRequest):
    if not search_in.origin:
        raise CabboException("Origin is required for outstation trip", status_code=400)

    if not search_in.destination:
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
