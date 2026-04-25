import math
from typing import List, Optional, Union
from core.constants import APP_NAME
from core.exceptions import CabboException
from core.store import ConfigStore
from core.trip_constants import COMMON_EXCLUSIONS, COMMON_INCLUSIONS
from core.trip_helpers import (
    derive_trip_sort_priority,
    generate_trip_field_dictionary,
    generate_trip_hash,
    get_default_trip_amenities,
)
from core.config import settings
from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema
from models.customer.customer_orm import Customer
from models.customer.customer_schema import CustomerRead
from models.customer.passenger_schema import PassengerRequest
from models.driver.driver_schema import DriverReadSchema
from models.map.location_schema import LocationInfo
from models.pricing.pricing_schema import (
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
from services.configuration_service import get_state_from_location_v2
from services.location_service import get_distance_km, get_state_from_location

from services.pricing_service import compute_final_platform_fee
from services.validation_service import validate_outstation_trip_schedule


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
    inclusions = COMMON_INCLUSIONS[:]  # base set
    inclusions.extend(
        [
            "Driver allowance",
            "Water bottles, candies, and tissues",
        ]
    )

    exclusions = COMMON_EXCLUSIONS[:]  # base set
    exclusions.extend(
        [
            "Self sponsored driver accomodation",
            "Night surcharges(if applicable)",
        ]
    )
    if is_interstate:
        inclusions.extend(
            [
                "State entry taxes", # Applicable state entry taxes for interstate trips, we maintain a configuration for state entry taxes per state, and hence it is included here
            ]
        )
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
    prev_state = get_state_from_location(all_locations[0],search_in.session_token)  # Origin location state
    if prev_state:
        unique_states.add(prev_state.lower())
    for loc in all_locations[
        1:
    ]:  # Iterate through all locations including hops and destination except the first one
        curr_state = get_state_from_location(loc,search_in.session_token)
        if curr_state.lower() != prev_state.lower():
            state_borders_crossed += 1
            unique_states.add(curr_state.lower())
        prev_state = curr_state.lower()
    total_unique_states = len(unique_states)
    is_interstate = (
        total_unique_states > 1
    )  # More than one unique state means interstate trip
    return is_interstate, total_unique_states, list(unique_states)


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
            )
        outbound_km += leg_km
    
    # Return leg: destination → origin (direct, not retracing hops)
    return_km = get_distance_km(origin=search_in.destination, destination=search_in.origin)
    if not return_km or return_km <= 0:
        raise CabboException(
            "Could not estimate return distance from destination to origin",
            status_code=500,
        )
    
    min_distance_for_outstation_trip = 70  # in km
    if outbound_km < min_distance_for_outstation_trip:
        raise CabboException(
            f"Outstation trips must have a minimum distance of {min_distance_for_outstation_trip} km, "
            f"the route you have selected is less than {min_distance_for_outstation_trip} km, "
            f"try with a different route or switch to local trip",
            status_code=500,
        )
    
    total_est_km = outbound_km + return_km

    return search_in.origin, search_in.destination, total_est_km


def _get_outstation_trips_disclaimer_lines(
    night_hours_display_label: str, night_surcharge_per_hour: float, 
    included_mileage_km: int,
    overage_amount_per_km: float,
    currency: str,
    extra_day_rate: float,
    total_trip_days: int
):
    """
    Returns the disclaimer lines for outstation trips, including overage charges and parking fees.

    This function provides the standard disclaimer lines that are used in outstation trip pricing
    calculations, ensuring that customers are aware of potential extra charges.

    Returns:
        List[str]: A list of disclaimer lines for outstation trips.
    """
    non_refund_line = "You will be charged the full fare even if your trip is shorter than the booked duration or included mileage."
    
    extra_day_line = (
    f"If you extend the trip beyond the booked {total_trip_days} day(s), "
    f"an additional {currency}{extra_day_rate} per extra day applies — pay the driver directly."
)
    return [
        f"If the driver is required to drive during night hours ({night_hours_display_label}), a night surcharge of {currency}{night_surcharge_per_hour} per hour will be applied on the final fare.",
        non_refund_line,
        extra_day_line,
        f"If you exceed the included mileage of {included_mileage_km} kms, an overage charge of {currency}{overage_amount_per_km} per km will be applied on the final fare - pay the driver directly.",
        "Extra charges apply for tolls, paid parking, and night driving surcharges (if applicable) - pay the driver directly.",
        "If the trip includes hill climbs, the cab AC may be switched off during such climbs."
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

    _, _, total_est_km = _get_trip_origin_destination_distance_outstation(search_in)
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
        cab_type_schema = CabTypeSchema.model_validate(cab_type)
        fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
        # Calculate interstate permit fee if applicable per cab type and fuel type for the unique states crossed
        if is_interstate and unique_states:
            if total_trip_days<=7: #If the trip is less than or equal to 7 days, charge permit fee once as permit fee is configured per week basis
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
        platform_fee_amount = compute_final_platform_fee(
            total_price=total_price_before_platform_fee,
            fixed_fee=config_store.platform_fee.fixed_platform_fee,
            dynamic_percent=platform_fee_percent,
            min_cap=configuration.auxiliary_pricing.common.min_platform_fee,
            max_cap=configuration.auxiliary_pricing.common.max_platform_fee,
        )
        price_breakdown = OutstationPricingBreakdownSchema(
            base_fare=math.ceil(base_price),
            driver_allowance=math.ceil(driver_allowance_amount),
            permit_fee=math.ceil(permit_fee),
            platform_fee=platform_fee_amount,
        )
        extra_day_rate = math.ceil(base_fare_per_km * min_included_km_per_day + driver_allowance_per_day)
        disclaimer_lines = _get_outstation_trips_disclaimer_lines(
            night_hours_display_label=night_hours_display_label,
            night_surcharge_per_hour=night_surcharge_per_hour,
            included_mileage_km=included_km,
            overage_amount_per_km=overage_amount_per_km,
            currency=currency,
            extra_day_rate=extra_day_rate,
            total_trip_days=total_trip_days
        )
        disclaimer_message = "Extra charges may apply:\n - " + "\n - ".join(
            disclaimer_lines
        )
        option = TripSearchOption(
            car_type=cab_type_schema.name,
            fuel_type=fuel_type_schema.name,
            total_price=math.ceil(
                total_price_before_platform_fee + platform_fee_amount
            ),
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
                    extra_charges_disclaimers=disclaimer_message,
                ).model_dump(exclude_none=True, exclude_unset=True)
            ),
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
        )
    # Intelligent sorting based on user preferences and trip context
    _options = sorted(
        options, key=lambda option: derive_trip_sort_priority(search_in, option)
    )[
        : len(options)
    ]  #  Limit to top n options based on user preferences and trip context

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
        preferences=search_in,
        metadata=metadata.model_dump(exclude_none=True, exclude_unset=True),
    )


def get_kwargs_for_outstation_trip(
    trip: Trip,
    currency: str,
    customer:Optional[Union[Customer, CustomerRead]]=None
) -> dict:
    try:
        if not trip or not trip.booking_id:
            print("Invalid trip information.")
            return {}  # Do not proceed if trip info is invalid

        app_name = APP_NAME.capitalize()
        app_url = settings.APP_URL

        # Validate and extract origin and destination
        origin = LocationInfo.model_validate(trip.origin)
        destination = LocationInfo.model_validate(trip.destination)

        if not origin or not destination:
            print("Invalid origin or destination for trip:", trip.booking_id)
            return {}  # Do not proceed if origin or destination is invalid

        if not customer:
            customer_id = trip.creator_id

            if not customer_id or not customer_email:
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
            in_car_amenities = driver.cab_amenities.model_dump(exclude_none=True, exclude_unset=True)
        else:
            # Fallback to trip's in-car amenities itself, if driver's cab amenities are not available
            in_car_amenities = trip.in_car_amenities or {}

        in_car_amenities = {key: value for key, value in in_car_amenities.items() if value}

        # Prepare overages disclaimer
        overages = trip.overages or {}
        overages_disclaimer: Optional[List[str]] = overages.get("disclaimer", []) if overages else None
        extra_charges_disclaimers :Optional[str] = overages.get("extra_charges_disclaimers") if overages else None

        # Prepare kwargs for the Jinja template
        kwargs = {
            "customer_name": customer_name,
            "customer_email": customer_email,
            "app_name": app_name,
            "app_url": app_url,
            "pickup_location": origin.address,
            "hops": trip.hops,
            "drop_location": destination.address,
            "start_date": trip.start_datetime.strftime("%d %b %Y, %I:%M %p"),
            "end_date": trip.end_datetime.strftime("%d %b %Y, %I:%M %p") if trip.end_datetime else None,
            "total_trip_days": trip.total_days or "-",
            "estimated_km": trip.estimated_km,
            "included_km": trip.included_kms,
            "booking_id": trip.booking_id,
            "package_label": trip.package_label,
            "driver_name": driver.name if driver else None,
            "driver_contact": driver.phone if driver else None,
            "cab_number": driver.cab_registration_number if driver else None,
            "cab_type": driver.cab_type if driver else None,
            "model": driver.cab_model_and_make if driver else None,
            "fuel_type": driver.fuel_type if driver else None,
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
           
        }

        return kwargs
    except Exception as e:
        print("Error preparing kwargs for outstation trip:", str(e))
        return {}  # Return empty dict on error to avoid breaking email notifications


def get_outstation_min_distance(
    pickup: LocationInfo, config_store: ConfigStore
) -> Optional[float]:
    """
    Returns the outstation minimum distance threshold (km) for the pickup state
    from config. Returns None if state or config entry is unavailable.
    """
    state = get_state_from_location_v2(location=pickup, config_store=config_store)
    if not state:
        return None
    outstation_config = config_store.outstation.get(state.state_code)
    if not outstation_config:
        return None
    try:
        return outstation_config.auxiliary_pricing.common.min_distance_km
    except AttributeError:
        return None