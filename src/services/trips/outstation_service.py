import json
import math
from typing import List
from core.exceptions import CabboException
from core.store import ConfigStore
from core.trip_constants import COMMON_EXCLUSIONS, COMMON_INCLUSIONS
from core.trip_helpers import derive_trip_sort_priority, generate_trip_field_dictionary, generate_trip_hash, get_default_trip_amenities
from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema
from models.pricing.pricing_schema import (
    OutstationCabPricingSchema,
    OutstationPricingBreakdownSchema,
    OveragesSchema,
)
from models.trip.trip_schema import (
    TripSearchAdditionalData,
    TripSearchOption,
    TripSearchRequest,
    TripSearchResponse,
)
from services.location_service import get_distance_km, get_state_from_location
from services.pricing_service import get_preauthorized_minimum_wallet_amount

from services.validation_service import validate_outstation_trip_schedule
from utils.utility import remove_none_recursive


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
            "Minimum parking and toll allowance",
            "Water bottles, candies, and tissues",
        ]
    )

    exclusions = COMMON_EXCLUSIONS[:]  # base set
    exclusions.extend(
        [
            "Self sponsored driver accomodation",
            "Night surcharges(if applicable)",
            "Extra tolls(if any)",
        ]
    )
    if is_interstate:
        inclusions.extend(
            [
                "State entry taxes",
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
    prev_state = get_state_from_location(all_locations[0])  # Origin location state
    if prev_state:
        unique_states.add(prev_state.lower())
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
    if est_km < 100:
        # Ensure that the estimated distance is at least 100 km for outstation trips
        raise CabboException(
            "Outstation trips must have a minimum distance of 100 km, the route you have selected is less than 100 km, try with a different route or switch to local trip",
            status_code=400,
        )

    return search_in.origin, search_in.destination, est_km


def _get_outstation_trips_disclaimer_lines(
    night_hours_display_label: str, night_surcharge_per_hour: float, currency: str
):
    """
    Returns the disclaimer lines for outstation trips, including overage charges and parking fees.

    This function provides the standard disclaimer lines that are used in outstation trip pricing
    calculations, ensuring that customers are aware of potential extra charges.

    Returns:
        List[str]: A list of disclaimer lines for outstation trips.
    """
    non_refund_line = (
        "If you do not utilise the full included days for your outstation package, the full package amount will still be charged; unused days/kilometres are non‑refundable."
    )
    return [
        f"If the driver is required to drive during night hours ({night_hours_display_label}), a night surcharge of {currency}{night_surcharge_per_hour} per hour will be applied on the final fare.",
        non_refund_line,
        "If total tolls and/or parking costs exceed the included wallet amount, the excess will be charged. If you use less, the unused balance will be refunded at trip end by adjusting the final fare.",
        "All extra charges are based on actual usage and will be clearly shown on your invoice.",
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
)->TripSearchResponse:
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

    _, _, est_km = _get_trip_origin_destination_distance_outstation(search_in)
    total_trip_days = validate_outstation_trip_schedule(search_in)
    # Minumum toll wallet amount is configured to 500.00 for outstation trips, if the total cost of the toll goes above the minimum toll amount during the trip, then the surplus amount will be charged to the customer accordingly, otherwise the left/unused amount will be refunded(deducted from final bill) to the customer.
    minimum_toll_wallet = get_preauthorized_minimum_wallet_amount(
        configuration.auxiliary_pricing.common.minimum_toll_wallet
    )

    # Minimum parking wallet amount is configured to 150 for outstation trips, if the total cost of the parking goes above the minimum parking amount, then the surplus amount will be charged to the customer accordingly, otherwise the left/unused amount will be refunded(deducted from final bill) to the customer.
    minimum_parking_wallet = get_preauthorized_minimum_wallet_amount(
        configuration.auxiliary_pricing.common.minimum_parking_wallet
    )

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
    est_km = (
        2 * est_km
    )  # Always Round trip distance for outstation, therefore multiply by 2
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
            permit_fee = configuration.auxiliary_pricing.permit.permit_fee
        base_fare_per_km = pricing_schema.base_fare_per_km
        min_included_km_per_day = pricing_schema.min_included_km_per_day
        overage_amount_per_km = pricing_schema.overage_amount_per_km
        driver_allowance_per_day = pricing_schema.driver_allowance_per_day

        included_km = min_included_km_per_day * total_trip_days
        base_price = base_fare_per_km * included_km
        overage_km = max(0, est_km - included_km)
        overage_amount = overage_km * overage_amount_per_km
        driver_allowance_amount = driver_allowance_per_day * total_trip_days

        warning_km_threshold = (
            configuration.auxiliary_pricing.common.overage_warning_km_threshold
        )
        margin = included_km - est_km  # Allow negative values for overage
        indicative_overage_warning = margin <= warning_km_threshold
        package_short_label = (
            f"{max(est_km, included_km)} km | Round trip | ({total_trip_days} days)"
        )
        package_label = f"{package_short_label} - AC {cab_type_schema.name}({cab_type_schema.capacity}) - ({fuel_type_schema.name})"

        # Total before platform fee/convenience fee
        total_price_before_platform_fee = (
            base_price
            + driver_allowance_amount
            + minimum_toll_wallet
            + minimum_parking_wallet
            + permit_fee
            + overage_amount
        )
        # Platform fee is a sum of a fixed cost(infra cost) to service fee and a percentage of the total price calculated before adding platform fee/convenience fee
        platform_fee_amount = config_store.platform_fee.fixed_platform_fee + (
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
        disclaimer_lines = _get_outstation_trips_disclaimer_lines(
            night_hours_display_label=night_hours_display_label,
            night_surcharge_per_hour=night_surcharge_per_hour,
            currency=currency,
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
            included_km=included_km,
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
        estimated_km=est_km,
        included_km=(
            _options[0].included_km
            if _options and len(_options) > 0 and _options[0].included_km
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
        metadata=metadata.model_dump(exclude_none=True, exclude_unset=True)
    )
   
