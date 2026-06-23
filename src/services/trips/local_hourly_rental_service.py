from datetime import timedelta
import math
from typing import List, Optional, Union

from core.constants import APP_NAME
from core.config import settings
from core.exceptions import CabboException, LOCAL_TRIP_ORIGIN_REQUIRED, GENERIC_EXCEPTION
from core.store import ConfigStore
from core.trip_constants import COMMON_EXCLUSIONS, COMMON_INCLUSIONS
from core.trip_helpers import (
    generate_trip_field_dictionary,
    generate_trip_hash,
    get_default_trip_amenities,
)
from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema, VehicleCapacitySchema
from models.customer.customer_orm import Customer
from models.customer.customer_schema import CustomerRead
from models.customer.passenger_schema import PassengerRequest
from models.driver.driver_schema import DriverReadSchema
from models.map.location_schema import LocationInfo
from models.pricing.pricing_schema import (
    Currency,
    LocalCabPricingSchema,
    LocalPricingBreakdownSchema,
    OveragesSchema,
    TripPackageConfigSchema,
)
from models.trip.trip_enums import CarTypeEnum
from models.trip.trip_orm import Trip
from models.trip.trip_schema import (
    TripSearchAdditionalData,
    TripSearchOption,
    TripSearchRequest,
    TripSearchResponse,
)
from services.cab_service import get_car_type_rank, get_recommended_car_type
from services.configuration_service import get_region_from_location

from services.policy_service import get_refund_and_cancellation_policy_by_jurisdiction_code, get_refund_and_cancellation_policy_lines
from services.pricing_service import compute_final_platform_fee
from services.validation_service import validate_local_trip_schedule
from utils.utility import format_trip_datetime, to_timezone_aware_datetime, validate_date_time


def _get_inclusions_exclusions_for_local_trip():
    """
    Returns the inclusions and exclusions for local trips.
    Returns:
        Tuple[List[str], List[str]]:
            - inclusions (List[str]): List of inclusions for the trip.
            - exclusions (List[str]): List of exclusions for the trip.
    """
    inclusions = COMMON_INCLUSIONS[:]  # base set
    inclusions.extend(
        [
            "Water bottles and tissues",
        ]
    )
    exclusions = COMMON_EXCLUSIONS[:]

    return inclusions, exclusions


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
        raise CabboException("Origin is required for local trip", status_code=400, error_code=LOCAL_TRIP_ORIGIN_REQUIRED)

    if not search_in.destination:
        search_in.destination = (
            search_in.origin
        )  # For local trips, origin and destination can be the same if not explicitly specified

    return (
        search_in.origin,
        search_in.destination,
        0.0,
    )  # Local trips don't require distance estimation as they are hourly based, can be 0 or any default value

def _get_local_trips_common_disclaimer_lines(currency:str, applicable_driver_allowance: float = 0.0):
    non_refund_line = "You will be charged the full fare even if your trip is shorter than the booked duration or included mileage."

    disclaimer_lines = [
        non_refund_line,

        "Extra charges apply for tolls, paid parking, and exceeding included hours or mileage (if applicable) - pay the driver directly.",
    ]
    if applicable_driver_allowance > 0.0:
        disclaimer_lines.insert(
            1,
            f"An additional driver allowance of {currency}{applicable_driver_allowance} will be charged if you exceed the included hours.",
        )
    return disclaimer_lines

def _get_local_trips_disclaimer_lines(
    package_label: str,
    currency: str,
    overage_amount_per_hour: float,
    overage_amount_per_km: float,
    applicable_driver_allowance: float = 0.0,
):
    """
    Returns the disclaimer lines for local trips, including overage charges and parking fees.

    This function provides the standard disclaimer lines that are used in local trip pricing
    calculations, ensuring that customers are aware of potential extra charges.

    Returns:
        List[str]: A list of disclaimer lines for local trips.
    """
    non_refund_line = "You will be charged the full fare even if your trip is shorter than the booked duration or included mileage."
    
    # Always ceil per minute and per km overage amounts for display
    #Converting per hour overage to per minute for better customer understanding and transparency, as local trips are primarily charged based on time. This allows customers to understand how much they will be charged for each additional minute if they exceed the included hours in their package, which can help them manage their trip duration effectively to avoid overage charges. The per km overage is also rounded up to ensure that customers are aware of the maximum potential charge for exceeding the included kilometers.
    # Plus no surprise numbers for customers.
    rounded_overage_amount_per_minute = int(math.ceil(overage_amount_per_hour/60)) if overage_amount_per_hour is not None else 0
    rounded_overage_amount_per_km = int(math.ceil(overage_amount_per_km)) if overage_amount_per_km is not None else 0

    disclaimer_lines = [
            f"If you exceed the included hours and/or kilometres in your selected package ({package_label}), an additional charge of {currency}{rounded_overage_amount_per_minute} per minute and/or {currency}{rounded_overage_amount_per_km} per km will apply.",
            non_refund_line,
            "Extra charges apply for tolls, paid parking, and exceeding included hours or mileage (if applicable) - pay the driver directly.",
        ]

    if applicable_driver_allowance > 0.0:
        disclaimer_lines.insert(
            1,
            f"An additional driver allowance of {currency}{applicable_driver_allowance} will be charged if you exceed the included hours.",
        )

    return disclaimer_lines


def _get_trip_package_by_id(
    packages: List[TripPackageConfigSchema],
    package_id: str,
    fallback_duration: int = 4,
    fallback_km: int = 40,
    fallback_label: str = "4Hours / 40KM",
):
    if not package_id:
        return TripPackageConfigSchema(
            included_hours=fallback_duration,
            included_km=fallback_km,
            package_label=fallback_label,
        )
    for package in packages:
        if package.id == package_id:
            return package


def _get_local_trip_pricing_configuration_by_region(
    region_code: str, config_store: ConfigStore
):
    """
    Retrieves configuration settings for a specific region code from the configuration store.
    Args:
        region_code (str): The region code to look up.
        config_store (ConfigStore): The configuration store instance.
    Returns:
        MasterPricingConfiguration: Configuration settings for the specified region code.
    """

    region_code = region_code.upper()
    # Find the local hourly rental configuration for the given region code
    return config_store.local.get(region_code, None)


def get_local_trip_options(search_in: TripSearchRequest, config_store: ConfigStore):
    """
    Retrieves local trip options based on the search request.
    Args:
        search_in (TripSearchRequest): The trip search request containing origin details.
        config_store (ConfigStore): The configuration store instance.
    Returns:
        TripSearchResponse: The response containing available local trip options.
    Raises:
        CabboException: If no local trip options are available for the selected region and criteria.

    """

    # Pricing configuration will be always based on origin region for local trips.
    configuration = _get_local_trip_pricing_configuration_by_region(
        region_code=search_in.origin.region_code, config_store=config_store
    )
    if not configuration:
        raise CabboException(
            "No local trip options available for the selected region and criteria.",
            status_code=404,
            error_code=GENERIC_EXCEPTION,
        )
    currency = config_store.geographies.country_server.currency_symbol

    validate_local_trip_schedule(search_in)  # Validate local trip schedule
    _, _, _ = _get_trip_origin_destination_distance_local(search_in)
    inclusions, exclusions = _get_inclusions_exclusions_for_local_trip()
    in_car_amenities = get_default_trip_amenities()

    in_car_amenities.phone_charger = (
        True  # Always include phone charger for local trips
    )
    in_car_amenities.aux_cable = True  # Always include aux cable for local trips
    
    # Get the package ID if provided, otherwise use configs.min_included_hours for duration

    package = _get_trip_package_by_id(
        package_id=search_in.package_id,
        packages=configuration.auxiliary_pricing.trip_packages,
    )

    package_short_label = package.package_label
    package_included_hours = package.included_hours
    package_included_km = package.included_km
    total_included_minutes = package_included_hours * 60

    search_in.start_date = validate_date_time(search_in.start_date, timezone_str=search_in.timezone)
    # Ensure start date is in correct format and timezone-aware for local trips
    search_in.start_date =to_timezone_aware_datetime(search_in.start_date)
    
    expected_end_date = validate_date_time(search_in.start_date, timezone_str=search_in.timezone) + timedelta(
        hours=package_included_hours
    )
    search_in.expected_end_date = expected_end_date
     # Ensure expected end date is set for local trips and timezone-aware
    search_in.expected_end_date = to_timezone_aware_datetime(search_in.expected_end_date)
    
    platform_fee_percent = (
        configuration.auxiliary_pricing.common.dynamic_platform_fee_percent
    )
    local_pricings = configuration.base_pricing
    options: List[TripSearchOption] = []


    for pricing, cab_type, fuel_type in local_pricings:
        pricing_schema = LocalCabPricingSchema.model_validate(pricing)
        cab_type_schema = CabTypeSchema.model_validate(cab_type)
        fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
        hourly_rate = pricing_schema.hourly_rate
        max_included_hours = configuration.auxiliary_pricing.common.max_included_hours
        base_hours = min(package.included_hours, max_included_hours)
        base_fare = hourly_rate * base_hours
        driver_allowance_amount =math.ceil(package.driver_allowance) if package.driver_allowance else 0.0
        total_price_before_platform_fee = base_fare  + driver_allowance_amount

        # Platform fee is a sum of a fixed cost(infra cost) to service and a percentage of the total price calculated before adding platform fee/convenience fee
        platform_fee_amount= compute_final_platform_fee(
            total_price=total_price_before_platform_fee,
            fixed_fee=config_store.platform_fee.fixed_platform_fee,
            dynamic_percent=platform_fee_percent,
            min_cap=configuration.auxiliary_pricing.common.min_platform_fee,
            max_cap=configuration.auxiliary_pricing.common.max_platform_fee,
        )

        price_breakdown = LocalPricingBreakdownSchema(
            base_fare=math.ceil(base_fare),
            platform_fee=platform_fee_amount,
            driver_allowance=(
                math.ceil(package.driver_allowance) if package.driver_allowance else 0.0
            ),
        )
        # For local trips, we can't estimate distance in advance since routes are uncertain and hence no est_km is provided.
        # Overage charges will be initially presented as 0.00 and will be calculated only if the customer exceeds the included hours or km, we keep them informed through a disclaimer message that extra charges may apply at the end of the trip.
        overage_amount_per_km = pricing_schema.overage_amount_per_km
        overage_amount_per_hour = pricing_schema.overage_amount_per_hour
        disclaimer_lines = _get_local_trips_disclaimer_lines(
            package_label=package.package_label,
            overage_amount_per_hour=overage_amount_per_hour,
            overage_amount_per_km=overage_amount_per_km,
            applicable_driver_allowance=price_breakdown.driver_allowance,
            currency=currency,
        )

        
        package_label = f"{package_short_label} | AC {cab_type_schema.name}({cab_type_schema.capacity}) - ({fuel_type_schema.name})"
        total_price=math.ceil(
                total_price_before_platform_fee + price_breakdown.platform_fee
            )
        #We are also calculating the rate per minute for local trips to provide better price transparency to customers, as local trips are primarily charged based on time rather than distance. This allows customers to understand how much they are paying for each minute of their trip, which can help them make more informed decisions about their booking and manage their trip duration effectively to avoid overage charges. The rate per minute is calculated by dividing the total price (including platform fee and driver allowance) by the total included minutes in the selected package.
        rate_per_minute = round(total_price / total_included_minutes, 2)
        rate_per_km = round(total_price / package.included_km, 2) 
        
        option = TripSearchOption(
            car_type=CarTypeEnum(cab_type_schema.name),
            car_capacity=VehicleCapacitySchema(
                passenger_capacity=cab_type_schema.passenger_capacity,
                luggage_capacity=cab_type_schema.luggage_capacity,
                capacity_match = search_in.total_passengers <= cab_type_schema.passenger_capacity and search_in.total_luggages <= cab_type_schema.total_luggages if cab_type_schema.passenger_capacity is not None and cab_type_schema.luggage_capacity is not None else False,
                recommended=get_recommended_car_type(search_in.total_passengers, search_in.total_luggages) == CarTypeEnum(cab_type_schema.name),
                rank=get_car_type_rank(CarTypeEnum(cab_type_schema.name)),
            ),
            fuel_type=fuel_type_schema.name,  # Use display name from schema
            total_price=total_price,
            price_breakdown=price_breakdown,
            included_hours=package_included_hours,
            included_kms=package_included_km,
            package=package_label,  # Use package string for display
            package_short_label=package_short_label,
            overages=(
                OveragesSchema(
                    disclaimer=disclaimer_lines,
                    overage_amount_per_hour=overage_amount_per_hour,
                    overage_amount_per_km=overage_amount_per_km,
                ).model_dump(exclude_none=True, exclude_unset=True)
            ),
            currency=Currency(symbol=currency) if currency else Currency(),
            rate_per_min=rate_per_minute,
            rate_per_km=rate_per_km,
        )
        option_dict, preference_dict = generate_trip_field_dictionary(
            search_in, cab_type_schema.name, fuel_type_schema.name, option
        )

        hash = generate_trip_hash(
            option_dict, preference_dict
        )  # Generate hash for the option
        option.hash = hash  # Attach the generated hash to the option
        options.append(option)

    if not options:
        raise CabboException(
            "No local trip options available for the selected region and criteria.",
            status_code=404,
            error_code=GENERIC_EXCEPTION,
        )
    cancelation_refund_policy = get_refund_and_cancellation_policy_by_jurisdiction_code(trip_type=search_in.trip_type, jurisdiction_code=search_in.origin.region_code, config_store=config_store)  # Ensure refund policy exists for local trips in the region
    
    # Intelligent sorting based on user preferences and trip context
    recommended_car_type= get_car_type(search_in)
    eligible_options = [
        option
        for option in options
        if option.car_capacity.capacity_match
    ]
    _options = sorted(
        eligible_options, key=lambda option: derive_trip_sort_priority(recommended_car_type, option)
    )
    metadata = TripSearchAdditionalData(
        inclusions=inclusions,
        exclusions=exclusions,
        in_car_amenities=in_car_amenities,
        total_trip_days=1,
        included_hours=(
            _options[0].included_hours
            if _options and len(_options) > 0 and _options[0].included_hours
            else None
        ),
        included_kms=(
            _options[0].included_kms
            if _options and len(_options) > 0 and _options[0].included_kms
            else None
        ),
        choices=len(_options),  # Total number of options returned
        is_round_trip=True,
    )
    
    return TripSearchResponse(
        options=_options,
        preferences=search_in,
        metadata=metadata.model_dump(exclude_none=True, exclude_unset=True),
        disclaimers=_get_local_trips_common_disclaimer_lines(currency, applicable_driver_allowance=math.ceil(package.driver_allowance) if package and package.driver_allowance else 0.0),
        refund_and_cancellation_policy=get_refund_and_cancellation_policy_lines(policy=cancelation_refund_policy),

    )


def get_kwargs_for_local_hourly_rental(
    trip: Trip,
    currency: str,
    customer: Optional[Union[Customer, CustomerRead]]=None
) -> dict:
    try:
        if not trip or not trip.booking_id:
            print("Invalid trip information.")
            return {}  # Do not proceed if trip info is invalid

        app_name = APP_NAME.capitalize()
        app_url = settings.APP_URL

        # Validate and extract origin
        origin = LocationInfo.model_validate(trip.origin)

        if not origin:
            print("Invalid origin for trip:", trip.booking_id)
            return {}  # Do not proceed if origin is invalid

        if not customer :
            customer_id = trip.creator_id
            if not customer_id:
                print("Invalid customer information for trip:", trip.booking_id)
                return {}  # Do not proceed if customer info is invalid

            # Get customer from customer_id
            customer = trip.customer if trip.creator_id and trip.creator_type == "customer" else None
            customer = CustomerRead.model_validate(customer) if customer else None
            if not customer:
                print("Customer not found for trip:", trip.booking_id)
                return {}  # Do not proceed if customer not found

            customer_name = customer.name or "Valued Customer"
            customer_email = customer.email or None
        else:
            customer_name = customer.name or "Valued Customer"
            customer_email = customer.email or None

        driver = trip.driver if trip.driver_id else None
        driver = DriverReadSchema.model_validate(driver) if driver else None    

        # Prepare inclusions and exclusions
        inclusions, exclusions = _get_inclusions_exclusions_for_local_trip()

        # Prepare in-car amenities
        in_car_amenities =  None
        if driver and driver.cab_amenities:
            in_car_amenities = driver.cab_amenities.model_dump(exclude_none=True, exclude_unset=True)
        else:
            in_car_amenities= trip.in_car_amenities or {}

        in_car_amenities = {key: value for key, value in in_car_amenities.items() if value}

        # Prepare overages disclaimer
        overages = trip.overages or {}
        overages_disclaimer :Optional[List[str]] = overages.get("disclaimer", []) if overages else None
        extra_charges_disclaimers:Optional[str] = overages.get("extra_charges_disclaimers") if overages else None
        passenger = trip.passenger if trip.passenger and trip.passenger_id else None
        passenger =PassengerRequest.model_validate(passenger) if passenger else None
        passenger_name = passenger.name if passenger else None
        # Prepare kwargs for the Jinja template
        kwargs = {
            "customer_email": customer_email,
            "customer_name": customer_name,
            "app_name": app_name,
            "app_url": app_url,
            "pickup_location": origin.address,
            "start_date": format_trip_datetime(trip.start_datetime, trip.timezone).strftime("%d %b %Y, %I:%M %p"),
            "expected_end_date": format_trip_datetime(trip.expected_end_datetime, trip.timezone).strftime("%d %b %Y, %I:%M %p") if trip.expected_end_datetime else None,
            "booking_id": trip.booking_id,
            "package_label": trip.package_label,
            "cab_type": driver.cab_type.value if driver else None,
            "fuel_type": driver.fuel_type.value if driver else None,
            "model": driver.cab_model_and_make if driver else None,
            "driver_name": driver.name if driver else None,
            "driver_contact": driver.phone if driver else None,
            "cab_number": driver.cab_registration_number if driver else None,
            "passenger_name": passenger_name,
            "currency": currency,
            "total_fare": trip.final_price,
            "amount_paid": trip.advance_payment,
            "amount_due": trip.balance_payment,
            "in_car_amenities": in_car_amenities,
            "inclusions": inclusions,
            "exclusions": exclusions,
            "overages": {
                "disclaimer": overages_disclaimer,
                "extra_charges_disclaimers": extra_charges_disclaimers,
            },
            "timezone": trip.timezone,
        }

       
        return kwargs
    except Exception as e:
        print("Error preparing kwargs for local hourly rental service:", str(e))
        return {}  # Return empty dict on error to avoid breaking email notifications


def get_hourly_rental_max_included_km(
    pickup: LocationInfo, config_store: ConfigStore
) -> Optional[float]:
    """
    Returns the maximum included kilometers for an hourly rental trip based on the pickup location's region configuration. 
    The config is picked up from the state of the pickup location and not the drop location because 
    we want to set the maximum included kilometers based on the state from which the trip is starting, 
    as that is where most of the cost is incurred 
    Returns None if state or config entry is unavailable.
    """
    region = get_region_from_location(location=pickup, config_store=config_store)
    if not region:
        return None
    local_hourly_rental_config = config_store.local.get(region.region_code)
    if not local_hourly_rental_config:
        return None
    try:
        return float(local_hourly_rental_config.auxiliary_pricing.common.max_included_km)
    except (AttributeError, TypeError, ValueError):
        return None

def get_car_type(search_in: TripSearchRequest) -> CarTypeEnum:
    total_pax = search_in.total_passengers
    # We do not consider luggage for local rentals as customers typically do not carry large amounts of luggage for local trips, and the focus is more on passenger comfort and space rather than luggage capacity. This allows us to recommend a car type that prioritizes passenger seating and comfort, which is more relevant for local trips.
    return get_recommended_car_type(total_num_people=total_pax, total_num_luggages=0)


def derive_trip_sort_priority(recommended_car_type:CarTypeEnum, option: TripSearchOption):
    minimum_car_type = recommended_car_type
    minimum_rank = get_car_type_rank(minimum_car_type)
    option_rank = get_car_type_rank(option.car_type)

    if option_rank < minimum_rank:
        capacity_score = 1000 + ((minimum_rank - option_rank) * 100)
    else:
        capacity_score = (option_rank - minimum_rank) * 100

    return (capacity_score, option.total_price)

def remove_extra_fields_from_local_hourly_rental_trip(trip_dict: dict):
    keys_to_remove = ["created_at", "creator_id", "creator_type", "estimated_km","final_display_price","indicative_overage_warning", "is_active", "is_interstate", "is_round_trip", "num_backpacks","num_carryons", "num_large_suitcases","num_luggages", "num_other_bags","package_label","package_label_short","parking", "permit_fee","payment_provider_metadata","placard_required","platform_fee","preferred_car_type","preferred_fuel_type", "total_unique_states", "unique_states", "flight_number", "terminal_number","rate_per_km","toll_road_preferred","tolls","total_days","updated_at","utc_offset", "driver_allowance"]
    for key in keys_to_remove:
        trip_dict.pop(key, None)
    return trip_dict
