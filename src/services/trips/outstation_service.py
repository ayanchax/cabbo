import math
from typing import List, Optional, Union
from core.constants import APP_NAME
from core.exceptions import (
    CabboException,
    OUTSTATION_TRIP_ORIGIN_REQUIRED,
    OUTSTATION_TRIP_DESTINATION_REQUIRED,
    DISTANCE_NOT_DETERMINED,
    DISTANCE_BELOW_MINIMUM_THRESHOLD,
    GENERIC_EXCEPTION,
)
from core.store import ConfigStore
from core.trip_constants import (
    COMMON_EXCLUSIONS,
    COMMON_INCLUSIONS,
    build_exclusion_items,
    build_inclusion_items,
)
from core.trip_helpers import (
    generate_trip_field_dictionary,
    generate_trip_hash,
    get_default_trip_amenities,
)
from core.config import settings
from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema, VehicleCapacitySchema
from models.customer.customer_orm import Customer
from models.customer.customer_schema import CustomerRead
from models.customer.passenger_schema import PassengerRequest
from models.driver.driver_schema import DriverReadSchema
from models.map.location_schema import LocationInfo
from models.pricing.pricing_schema import (
    Currency,
    OutstationCabPricingSchema,
    OutstationPricingBreakdownSchema,
    OveragesSchema,
)
from models.trip.trip_orm import Trip
from models.trip.trip_schema import (
    TripSearchAdditionalData,
    TripSearchOption,
    TripSearchRequest,
    TripSearchResponse,
)
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum
from services.cab_service import get_car_type_rank, get_recommended_car_type
from services.configuration_service import get_state_from_location_v2
from services.location_service import get_distance_km

from services.policy_service import get_refund_and_cancellation_policy_by_jurisdiction_code, get_refund_and_cancellation_policy_lines
from services.pricing_service import compute_base_platform_fee, compute_platform_fee_with_tax
from services.validation_service import validate_outstation_trip_schedule
from utils.utility import format_trip_datetime
import logging
log = logging.getLogger(__name__)

def _get_inclusions_exclusions_for_outstation_trip(is_interstate: bool):
    """
    Returns the inclusions and exclusions for outstation trips based on whether it is interstate or not.
    Args:
        is_interstate (bool): True if the trip is interstate, False otherwise.
    Returns:
        Tuple[List[str], List[str]]:
            - inclusions (List[str]): List of inclusions for the trip.
            - exclusions (List[str]): List of exclusions for the trip.
    """
    inclusion_labels = COMMON_INCLUSIONS[:]  # base set
    inclusion_labels.extend(
        [
            "Driver allowance",
            "Water bottles, candies, and tissues",
        ]
    )

    exclusion_labels = COMMON_EXCLUSIONS[:]  # base set
    exclusion_labels.extend(
        [
            "Self sponsored driver accommodation",
            "Night surcharges (if applicable)",
        ]
    )
    if is_interstate:
        inclusion_labels.extend(
            [
                "State entry taxes",  # Applicable state entry taxes for interstate trips, we maintain a configuration for state entry taxes per state, and hence it is included here
            ]
        )
    return build_inclusion_items(inclusion_labels), build_exclusion_items(
        exclusion_labels
    )


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
    prev_state = all_locations[0].state  # Origin location state
    if prev_state:
        unique_states.add(prev_state.lower())
    for loc in all_locations[
        1:
    ]:  # Iterate through all locations including hops and destination except the first one
        curr_state = loc.state
        if (curr_state or "").lower() != (prev_state or "").lower():
            state_borders_crossed += 1
            unique_states.add(curr_state.lower())
        prev_state = curr_state.lower()
    total_unique_states = len(unique_states)
    is_interstate = (
        total_unique_states > 1
    )  # More than one unique state means interstate trip
    return is_interstate, total_unique_states, list(unique_states)


def _get_trip_origin_destination_distance_outstation(
    search_in: TripSearchRequest, min_distance: Optional[float] = 300.0
):
    """
    Validates and retrieves the origin, destination, and estimated distance for outstation trips.
    Args:
        search_in (TripSearchRequest): The trip search request containing origin and destination.
        min_distance (Optional[float]): The minimum distance required for an outstation trip. Defaults to 300.0 km.

        Returns:
            Tuple[LocationInfo, LocationInfo, float]: A tuple containing the origin, destination, and estimated distance in kilometers.
        Raises:
            CabboException: If origin or destination is not provided, or if the estimated distance cannot be calculated.

    """

    if (
        not search_in.origin
    ):  # Initial origin for outstation trip, final origin will be the first hop(origin)
        raise CabboException(
            "Origin is required for outstation trip",
            status_code=400,
            error_code=OUTSTATION_TRIP_ORIGIN_REQUIRED,
        )

    if (
        not search_in.destination
    ):  # Initial destination for outstation trip, final destination will be the first hop(origin)
        raise CabboException(
            "Destination is required for outstation trip",
            status_code=400,
            error_code=OUTSTATION_TRIP_DESTINATION_REQUIRED,
        )

    # Build ordered waypoints for the outbound route
    waypoints = [search_in.origin]
    if search_in.hops:
        waypoints.extend(search_in.hops)
    waypoints.append(search_in.destination)

    # Sum outbound leg distances: origin → hop1 → hop2 → ... → destination
    outbound_km = 0.0
    for i in range(len(waypoints) - 1):
        leg_km = get_distance_km(origin=waypoints[i], destination=waypoints[i + 1])
        if not leg_km or leg_km <= 0:
            raise CabboException(
                f"Could not estimate distance between waypoints {i} and {i + 1}",
                status_code=500,
                error_code=DISTANCE_NOT_DETERMINED,
            )
        outbound_km += leg_km

    min_distance_for_outstation_trip = min_distance  # in km
    if outbound_km < min_distance_for_outstation_trip:
        raise CabboException(
            f"Outstation trips must have a minimum distance of {min_distance_for_outstation_trip} km, "
            f"the route you have selected is less than {min_distance_for_outstation_trip} km, "
            f"try with a different route or switch to local trip",
            status_code=500,
            error_code=DISTANCE_BELOW_MINIMUM_THRESHOLD,
        )

    # Return leg: destination → origin (direct, not retracing hops)
    return_km = get_distance_km(
        origin=search_in.destination, destination=search_in.origin
    )
    if not return_km or return_km <= 0:
        raise CabboException(
            "Could not estimate return distance from destination to origin",
            status_code=500,
            error_code=DISTANCE_NOT_DETERMINED,
        )

    total_est_km = outbound_km + return_km

    return search_in.origin, search_in.destination, total_est_km


def _get_outstation_common_disclaimer_lines():
    non_refund_line = "You will be charged the full fare even if your trip is shorter than the booked duration or included mileage."

    return [
        non_refund_line,
        "Extra charges apply for tolls, paid parking, night driving surcharges and exceeding included days or mileage (if applicable) - pay the driver directly.",
        "If the trip includes hill climbs, the cab AC may be switched off during such climbs.",
    ]


def _get_outstation_trips_disclaimer_lines(
    night_hours_display_label: str,
    night_surcharge_per_hour: float,
    min_included_mileage_km_per_day: int,
    included_mileage_km: int,
    overage_amount_per_km: float,
    currency: str,
    extra_day_rate: float,
    total_trip_days: int,
    indicative_overage_warning: bool = False
):
    """
    Returns the disclaimer lines for outstation trips, including overage charges and parking fees.

    This function provides the standard disclaimer lines that are used in outstation trip pricing
    calculations, ensuring that customers are aware of potential extra charges.

    Returns:
        List[str]: A list of disclaimer lines for outstation trips.
    """
    non_refund_line = "You will be charged the full fare even if your trip is shorter than the booked duration or included mileage."

    rounded_overage_amount_per_km = int(math.ceil(overage_amount_per_km)) if overage_amount_per_km is not None else 0

    rounded_extra_day_rate = int(math.ceil(extra_day_rate)) if extra_day_rate is not None else 0

     

    extra_day_line = (
    f"If you extend the trip beyond the booked {total_trip_days} day(s), "
    f"an additional {currency}{rounded_extra_day_rate} per extra day will apply, "
    f"that includes {min_included_mileage_km_per_day} kms and driver allowance for one day - pay the driver directly."
)
    
    exceed_mileage_line= f"If you exceed the included mileage of {included_mileage_km} kms, an overage charge of {currency}{rounded_overage_amount_per_km} per km will apply - pay the driver directly."
    if indicative_overage_warning:
        if rounded_overage_amount_per_km > 0:
               exceed_mileage_line= f"This route is close to or may exceed the {included_mileage_km} km included with this trip. If the final trip distance exceeds {included_mileage_km} km, an additional charge of {currency}{rounded_overage_amount_per_km} per km will apply - pay the driver directly."
            
    return [
        non_refund_line,
        extra_day_line,
        exceed_mileage_line,
        f"If the driver is required to drive during night hours ({night_hours_display_label}), a night surcharge of {currency}{night_surcharge_per_hour} per hour will apply - pay the driver directly.",
        "Extra charges apply for tolls, paid parking, night driving surcharges, extra days, and extra mileage, if applicable - pay the driver directly.",
        "If the trip includes hill climbs, the cab AC may be switched off during such climbs.",
    ]


def _get_outstation_pricing_configuration_by_state(
    state_code: str, config_store: ConfigStore
):
    """
    Retrieves outstation trip pricing configuration for a specific state code from the configuration store.
    Args:
        state_code (str): The state code to look up.
        config_store (ConfigStore): The configuration store instance.
    Returns:
        MasterPricingConfiguration: Outstation trip pricing configuration for the specified state code.
    """

    state_code = state_code.upper()
    # Find the outstation configuration for the given state code
    return config_store.outstation.get(state_code, None)


def get_allowed_outstation_states(config_store: ConfigStore) -> set:
    """
    Returns a set of state codes that are allowed for outstation trips.
    """

    allowed_states = set()
    for state_code, _ in config_store.outstation.items():
        allowed_states.add(state_code.upper())
    return allowed_states


def get_outstation_trip_options(
    search_in: TripSearchRequest, config_store: ConfigStore
) -> TripSearchResponse:
    """
    Retrieves outstation trip options based on the search request and configuration store.
    Args:
        search_in (TripSearchRequest): The trip search request containing origin and destination details.
        config_store (ConfigStore): The configuration store instance.
    Returns:
        TripSearchResponse: The trip search response containing available outstation trip options.
    """

    # Retrieve outstation pricing configuration for the origin state
    configuration = _get_outstation_pricing_configuration_by_state(
        state_code=search_in.origin.state_code, config_store=config_store
    )

    if not configuration:
        return TripSearchResponse(
            trip_options=[],
            message=f"No outstation pricing configuration found for state code: {search_in.origin.state_code}",
        )

    currency = config_store.geographies.country_server.currency_symbol
    currency_code = config_store.geographies.country_server.currency
    
    _, _, total_est_km = _get_trip_origin_destination_distance_outstation(
        search_in,
        min_distance=configuration.auxiliary_pricing.common.min_outbound_distance_km,
    )
    total_trip_days = validate_outstation_trip_schedule(search_in)

    # Identify unique state borders crossed (including between hops)
    is_interstate, total_unique_states, unique_states = _track_state_transitions(
        search_in
    )
    inclusions, exclusions = _get_inclusions_exclusions_for_outstation_trip(
        is_interstate
    )
    
    in_car_amenities = get_default_trip_amenities()

    in_car_amenities.candies = True  # Candies are included for outstation trips
    in_car_amenities.phone_charger = (
        True  # Always include phone charger for outstation trips
    )
    in_car_amenities.aux_cable = True  # Always include aux cable for outstation trips
    in_car_amenities.bluetooth = True  # Always include bluetooth for outstation trips
    permit_fee = 0.0
    night_surcharge_per_hour = (
        configuration.auxiliary_pricing.night.night_overage_amount_per_block
    )
    night_hours_display_label = configuration.auxiliary_pricing.night.night_hours_label
    search_in.expected_end_date = search_in.end_date
    platform_fee_percent = (
        configuration.auxiliary_pricing.common.dynamic_platform_fee_percent
    )
    # Fetch all outstation cab pricings
    outstation_pricings = configuration.base_pricing
    options: List[TripSearchOption] = []
    for pricing, cab_type, fuel_type in outstation_pricings:
        pricing_schema = OutstationCabPricingSchema.model_validate(pricing)
        #Despite picking only available pricings in network that pairs with active cab types and fuel types from the configuration store at app startup, we are adding an additional check here to ensure that only active and available cab-fuel pairs are considered for pricing. This is a safeguard against any potential misconfigurations or changes in the configuration that might introduce inactive or unavailable options. By skipping any inactive or unavailable cab-fuel pairs, we ensure that customers are only presented with valid and bookable options, enhancing the user experience and preventing potential booking issues.
        if not pricing_schema.is_available_in_network:
                    continue  # Skip pricings for cab-fuel pairs not available in the network
        cab_type_schema = CabTypeSchema.model_validate(cab_type)
        if not cab_type_schema.is_active:
            continue  # Skip inactive cab types
        
        fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
        if not fuel_type_schema.is_active:
            continue  # Skip inactive fuel types
        # Calculate interstate permit fee if applicable per cab type and fuel type for the unique states crossed
        if is_interstate and unique_states:
            if (
                total_trip_days <= 7
            ):  # If the trip is less than or equal to 7 days, charge permit fee once as permit fee is configured per week basis
                permit_fee = configuration.auxiliary_pricing.permit.permit_fee
            else:
                weekly_fee = configuration.auxiliary_pricing.permit.permit_fee
                # Calculate pro-rata fee for days beyond the first week
                permit_fee = weekly_fee + ((total_trip_days - 7) * (weekly_fee / 7))

        base_fare_per_km = pricing_schema.base_fare_per_km
        min_included_km_per_day = pricing_schema.min_included_km_per_day
        overage_amount_per_km = pricing_schema.overage_amount_per_km
        driver_allowance_per_day = pricing_schema.driver_allowance_per_day

        included_km = min_included_km_per_day * total_trip_days
        base_price = base_fare_per_km * included_km
        overage_km = max(0, total_est_km - included_km)
        overage_amount = overage_km * overage_amount_per_km
        driver_allowance_amount = driver_allowance_per_day * total_trip_days

        warning_km_threshold = (
            configuration.auxiliary_pricing.common.overage_warning_km_threshold
        )
        margin = included_km - total_est_km  # Allow negative values for overage
        indicative_overage_warning = margin <= warning_km_threshold
        package_short_label = (
            f"{included_km} km | Round trip | ({total_trip_days} days)"
        )
        package_label = f"{package_short_label} - AC {cab_type_schema.name}({cab_type_schema.capacity}) - ({fuel_type_schema.name})"

        # Total before platform fee/convenience fee
        total_price_before_platform_fee = (
            base_price
            + driver_allowance_amount
            + permit_fee
            # + overage_amount # We do not include overage amount in the price shown to customer until they actually incur the overage, and that is why we have a disclaimer for overage charges in the UI, we will charge the overage amount directly on the trip fare when the trip is completed and customer has incurred the overage
        )
        # Platform fee is a sum of a fixed cost(infra cost) to service fee and a percentage of the total price calculated before adding platform fee/convenience fee
        platform_fee_base = compute_base_platform_fee(
            total_price=total_price_before_platform_fee,
            fixed_fee=config_store.platform_fee.fixed_platform_fee,
            dynamic_percent=platform_fee_percent,
            min_cap=configuration.auxiliary_pricing.common.min_platform_fee,
            max_cap=configuration.auxiliary_pricing.common.max_platform_fee,
        )
        platform_fee_components = compute_platform_fee_with_tax(
            platform_fee_base=platform_fee_base,
            tax_config=config_store.platform_fee_tax,
        )
        price_breakdown = OutstationPricingBreakdownSchema(
            base_fare=math.ceil(base_price),
            driver_allowance=math.ceil(driver_allowance_amount),
            permit_fee=math.ceil(permit_fee),
            **platform_fee_components,
        )
        extra_day_rate = math.ceil(
            overage_amount_per_km  * min_included_km_per_day + driver_allowance_per_day
        )
        disclaimer_lines = _get_outstation_trips_disclaimer_lines(
            night_hours_display_label=night_hours_display_label,
            night_surcharge_per_hour=night_surcharge_per_hour,
            min_included_mileage_km_per_day=min_included_km_per_day,
            included_mileage_km=included_km,
            overage_amount_per_km=overage_amount_per_km,
            currency=currency,
            extra_day_rate=extra_day_rate,
            total_trip_days=total_trip_days,
            indicative_overage_warning=indicative_overage_warning
        )

        total_price = math.ceil(
                total_price_before_platform_fee + price_breakdown.platform_fee
            )
        rate_per_km = round(price_breakdown.base_fare / included_km)

        option = TripSearchOption(
            car_type=CarTypeEnum(cab_type_schema.name),
            car_capacity=VehicleCapacitySchema(
                passenger_capacity=cab_type_schema.passenger_capacity,
                luggage_capacity=cab_type_schema.total_luggages,
                capacity_match = search_in.total_passengers <= cab_type_schema.passenger_capacity and search_in.total_luggages <= cab_type_schema.total_luggages if cab_type_schema.passenger_capacity is not None and cab_type_schema.luggage_capacity is not None else False,
                rank=get_car_type_rank(CarTypeEnum(cab_type_schema.name)),
                roof_carrier=cab_type_schema.roof_carrier
            ),
            fuel_type=fuel_type_schema.name,
            total_price=total_price,
            price_breakdown=price_breakdown,
            included_kms=included_km,
            package=package_label,
            package_short_label=package_short_label,
            overages=(
                OveragesSchema(
                    indicative_overage_warning=indicative_overage_warning,
                    overage_amount_per_km=overage_amount_per_km,
                    overage_estimate_amount=(
                        math.ceil(overage_amount) if indicative_overage_warning else 0.0
                    ),
                    disclaimer=disclaimer_lines,
                ).model_dump(exclude_none=True, exclude_unset=True)
            ),
            currency=Currency(symbol=currency, code = currency_code) if currency else Currency(),
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
            "No outstation trip options available for the selected route and preferences",
            status_code=404,
            error_code=GENERIC_EXCEPTION,
        )
    cancelation_refund_policy = get_refund_and_cancellation_policy_by_jurisdiction_code(trip_type=search_in.trip_type, jurisdiction_code=search_in.origin.state_code, config_store=config_store)  # Ensure refund policy exists for local trips in the region

    # Intelligent sorting based on user preferences and trip context
    recommended_car_type = get_car_type(search_in)

    eligible_options = [
        option
        for option in options
        if option.car_capacity.capacity_match
    ]
    _options = populate_best_choice_recommendation(
        eligible_options=eligible_options,
        recommended_car_type=recommended_car_type,
    )
    metadata = TripSearchAdditionalData(
        inclusions=inclusions,
        exclusions=exclusions,
        in_car_amenities=in_car_amenities,
        total_trip_days=total_trip_days,
        estimated_km=total_est_km,
        included_kms=(
            _options[0].included_kms
            if _options and len(_options) > 0 and _options[0].included_kms
            else None
        ),
        choices=len(_options),  # Total number of options returned
        is_round_trip=True,
        is_interstate=is_interstate,
        total_unique_states=total_unique_states,
        unique_states=unique_states if is_interstate else None,
    )

    return TripSearchResponse(
        options=_options,
        preferences=remove_extra_fields_from_outstation_trip(search_in.model_dump(exclude_none=True, exclude_unset=True)),
        metadata=metadata.model_dump(exclude_none=True, exclude_unset=True),
        disclaimers=_get_outstation_common_disclaimer_lines(),
        refund_and_cancellation_policy=get_refund_and_cancellation_policy_lines(policy=cancelation_refund_policy, trip_startdate_time=search_in.start_date, trip_timezone=search_in.timezone),
    )


def get_kwargs_for_outstation_trip(
    trip: Trip, currency: str, customer: Optional[Union[Customer, CustomerRead]] = None
) -> dict:
    try:
        if not trip or not trip.booking_id:
            log.error("Invalid trip information.")
            return {}  # Do not proceed if trip info is invalid

        app_name = APP_NAME.capitalize()
        app_url = settings.APP_URL

        # Validate and extract origin and destination
        origin = LocationInfo.model_validate(trip.origin)
        destination = LocationInfo.model_validate(trip.destination)

        if not origin or not destination:
            log.error("Invalid origin or destination for trip:", trip.booking_id)
            return {}  # Do not proceed if origin or destination is invalid

        if not customer:
            customer_id = trip.creator_id

            if not customer_id or not customer_email:
                log.error("Invalid customer information for trip:", trip.booking_id)
                return {}  # Do not proceed if customer info is invalid

            # Get customer from customer_id
            customer = (
                trip.customer
                if trip.creator_id and trip.creator_type == "customer"
                else None
            )
            customer = CustomerRead.model_validate(customer) if customer else None

            if not customer:
                log.error("Customer not found for trip:", trip.booking_id)
                return {}  # Do not proceed if customer not found

            customer_name = customer.name or "Valued Customer"
            customer_email = customer.email or None
        else:
            customer_name = customer.name or "Valued Customer"
            customer_email = customer.email or None

        driver = trip.driver if trip.driver_id else None
        driver = DriverReadSchema.model_validate(driver) if driver else None

        passenger = trip.passenger if trip.passenger_id else None
        passenger = PassengerRequest.model_validate(passenger) if passenger else None
        passenger_name = passenger.name if passenger else None

        # Prepare inclusions and exclusions
        inclusions, exclusions = _get_inclusions_exclusions_for_outstation_trip(
            is_interstate=trip.is_interstate
        )

        # Prepare in-car amenities
        in_car_amenities = None
        if driver and driver.cab_amenities:
            in_car_amenities = driver.cab_amenities.model_dump(
                exclude_none=True, exclude_unset=True
            )
        else:
            # Fallback to trip's in-car amenities itself, if driver's cab amenities are not available
            in_car_amenities = trip.in_car_amenities or {}

        in_car_amenities = {
            key: value for key, value in in_car_amenities.items() if value
        }

        # Prepare overages disclaimer
        overages = trip.overages or {}
        overages_disclaimer: Optional[List[str]] = (
            overages.get("disclaimer", []) if overages else None
        )
        extra_charges_disclaimers: Optional[str] = (
            overages.get("extra_charges_disclaimers") if overages else None
        )

        # Prepare kwargs for the Jinja template
        kwargs = {
            "customer_name": customer_name,
            "customer_email": customer_email,
            "app_name": app_name,
            "app_url": app_url,
            "pickup_location": origin.address,
            "hops": trip.hops,
            "drop_location": destination.address,
            "start_date": format_trip_datetime(trip.start_datetime, trip.timezone).strftime("%d %b %Y, %I:%M %p"),
            "end_date": (
                format_trip_datetime(trip.end_datetime, trip.timezone).strftime("%d %b %Y, %I:%M %p")
                if trip.end_datetime
                else None
            ),
            "total_trip_days": trip.total_days or "-",
            "estimated_km": trip.estimated_km,
            "included_km": trip.included_kms,
            "booking_id": trip.booking_id,
            "package_label": trip.package_label,
            "driver_name": driver.name if driver else None,
            "driver_contact": driver.phone if driver else None,
            "cab_number": driver.cab_registration_number if driver else None,
            "cab_type": driver.cab_type.value if driver else None,
            "model": driver.cab_model_and_make if driver else None,
            "fuel_type": driver.fuel_type.value if driver else None,
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
        log.error("Error preparing kwargs for outstation trip:", str(e))
        return {}  # Return empty dict on error to avoid breaking email notifications


def get_outstation_min_outbound_distance(
    pickup: LocationInfo, config_store: ConfigStore
) -> Optional[float]:
    """
    Returns the outstation minimum outbound distance threshold (km) for the pickup state
    from config.
    The config is picked up from the state of the pickup location and not the drop location because
    we want to set the minimum outbound distance based on the state from which the trip is starting,
    as that is where most of the cost is incurred
    Returns None if state or config entry is unavailable.
    """
    state = get_state_from_location_v2(location=pickup, config_store=config_store)
    if not state:
        return None
    outstation_config = config_store.outstation.get(state.state_code)
    if not outstation_config:
        return None
    try:
        return outstation_config.auxiliary_pricing.common.min_outbound_distance_km
    except AttributeError:
        return None


def get_car_type(search_in: TripSearchRequest) -> CarTypeEnum:
    total_pax = search_in.total_passengers
    return get_recommended_car_type(
        total_num_people=total_pax,
        total_num_luggages=search_in.total_luggages,
    )


def derive_trip_sort_priority(
    recommended_car_type: CarTypeEnum,
    option: TripSearchOption,
):
    minimum_rank = get_car_type_rank(recommended_car_type)
    option_rank = get_car_type_rank(option.car_type)

    if option_rank < minimum_rank:
        capacity_score = 1000 + ((minimum_rank - option_rank) * 100)
    else:
        capacity_score = (option_rank - minimum_rank) * 100

    return (capacity_score, option.total_price)


def populate_best_choice_recommendation(
    eligible_options: List[TripSearchOption],
    recommended_car_type: CarTypeEnum,
) -> List[TripSearchOption]:
    sorted_options = sorted(
        eligible_options,
        key=lambda option: derive_trip_sort_priority(recommended_car_type, option),
    )

    
    recommended_candidates = [
        option
        for option in sorted_options
        if option.car_type == recommended_car_type
        and option.fuel_type == FuelTypeEnum.hybrid
    ]

    if not recommended_candidates:
        #If no hybrid options are available, we will look for diesel options as the next best choice. Diesel cars are often preferred for outstation trips due to their fuel efficiency and performance over long distances. This ensures that we still provide a recommendation that aligns with the user's preferences and trip requirements.
        recommended_candidates = [
            option
            for option in sorted_options
            if option.car_type == recommended_car_type
            and option.fuel_type == FuelTypeEnum.diesel
        ]

    if not recommended_candidates:
        # If no hybrid or diesel options are available, we will look for petrol or any other options as the next best choice. Petrol cars are commonly used and widely available, making them a suitable alternative when other fuel types are not present. This ensures that we still provide a recommendation that aligns with the user's preferences and trip requirements.
        recommended_candidates = [
            option
            for option in sorted_options
            if option.car_type == recommended_car_type
        ]

    #Minimum price recommendation: Among the recommended candidates, we will select the option with the lowest total price as the best choice for the user. This ensures that we provide a cost-effective recommendation while still considering the user's preferred car type and fuel type. If no recommended candidates are available, we will default to the first option in the sorted list (if any) to ensure that the user still receives a recommendation.
    recommended_option = min(
        recommended_candidates,
        key=lambda option: option.total_price,
        default=sorted_options[0] if sorted_options else None,
    )

    if recommended_option:
        recommended_option.car_capacity.recommended = True

    return sorted(
        sorted_options,
        key=lambda option: (
            not option.car_capacity.recommended,
            derive_trip_sort_priority(recommended_car_type, option),
        ),
    )


def remove_extra_fields_from_outstation_trip(trip_dict: dict):
    keys_to_remove = ["created_at", "creator_id", "creator_type", "driver_allowance","final_display_price","indicative_overage_warning", "is_active","package_label","package_label_short","parking", "permit_fee","payment_provider_metadata","placard_required","platform_fee","preferred_car_type","preferred_fuel_type","updated_at","utc_offset", "driver_allowance", "rate_per_min","toll_road_preferred","tolls"]
    for key in keys_to_remove:
        trip_dict.pop(key, None)
    return trip_dict
