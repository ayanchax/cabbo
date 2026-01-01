import math
from typing import List, Union
from core.exceptions import CabboException
from core.store import ConfigStore
from core.trip_constants import COMMON_EXCLUSIONS, COMMON_INCLUSIONS
from core.trip_helpers import derive_trip_sort_priority, generate_trip_field_dictionary, generate_trip_hash, get_default_trip_amenities
from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema
from models.pricing.pricing_schema import (
    AirportCabPricingSchema,
    AirportPricingBreakdownSchema,
    OveragesSchema,
)
from models.trip.trip_schema import (
    TripSearchAdditionalData,
    TripSearchOption,
    TripSearchRequest,
    TripSearchResponse,
)
from services.location_service import get_distance_km

from services.validation_service import (
    validate_airport_schedule,
    validate_placard_requirements,
)


def _get_inclusions_exclusions_for_airport_drop(toll_road_preferred: bool = False):
    """
    Returns the inclusions and exclusions for airport drop trips.
    Returns:
        Tuple[List[str], List[str]]:
            - inclusions (List[str]): List of inclusions for the trip.
            - exclusions (List[str]): List of exclusions for the trip.
    """
    inclusions = COMMON_INCLUSIONS[:]  # base set
    if toll_road_preferred:
        inclusions.insert(1, "Toll")  # keep Toll early in the list
    inclusions.extend(["Water bottles and tissues"])

    exclusions = COMMON_EXCLUSIONS[:]
    return inclusions, exclusions


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
        search_in.destination = None

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
        search_in.origin = None
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


def _get_inclusions_exclusions_for_airport_pickup(
    toll_road_preferred: bool = False, placard_required: bool = False
):
    """
    Returns the inclusions and exclusions for airport pickup trips.
    Returns:
        Tuple[List[str], List[str]]:
            - inclusions (List[str]): List of inclusions for the trip.
            - exclusions (List[str]): List of exclusions for the trip.
    """
    inclusions = COMMON_INCLUSIONS[:]  # base set
    if toll_road_preferred:
        inclusions.append("Toll")
    inclusions.append("Parking")
    if placard_required:
        inclusions.append("Placard charges")
    inclusions.append("Water bottles and tissues")
    exclusions = COMMON_EXCLUSIONS[:]  # base set
    return inclusions, exclusions


def _get_airport_toll(toll: float, toll_road_preferred: bool):
    return toll if toll_road_preferred and toll is not None else 0.0


def _get_airport_pickup_pricing_configuration_by_region(
    region_code: str, config_store: ConfigStore
):
    """
    Retrieves airport pickup pricing configuration for a specific region code from the configuration store.
    Args:
        region_code (str): The region code to look up.
        config_store (ConfigStore): The configuration store instance.
    Returns:
        MasterPricingConfiguration: Airport pickup pricing configuration for the specified region code.
    """

    region_code = region_code.upper()
    # Find the airport pickup configuration for the given region code
    print(region_code)
    return config_store.airport_pickup.get(region_code, None)


def _get_airport_trips_disclaimer_lines(
    overage_amount_per_km: float, currency: str, included_kms: Union[int, float] = 0
):
    """
    Returns the disclaimer lines for airport trips, including overage charges and placard fees.

    This function provides the standard disclaimer lines that are used in airport trip pricing
    calculations, ensuring that customers are aware of potential extra charges.

    Returns:
        List[str]: A list of disclaimer lines for airport trips.
    """
    return [
        f"If you exceed the included kilometers({included_kms}) in your airport transfer, {currency}{overage_amount_per_km} per additional kilometer will be charged.",
        "All extra charges are based on actual usage and will be transparently shown in your invoice.",
    ]


def _get_airport_dropoff_pricing_configuration_by_region(
    region_code: str, config_store: ConfigStore
):
    """
    Retrieves airport dropoff pricing configuration for a specific region code from the configuration store.
    Args:
        region_code (str): The region code to look up.
        config_store (ConfigStore): The configuration store instance.
    Returns:
        MasterPricingConfiguration: Airport dropoff pricing configuration for the specified region code.
    """

    region_code = region_code.upper()
    # Find the airport dropoff configuration for the given region code
    return config_store.airport_drop.get(region_code, None)


def get_airport_pickup_trip_options(
    search_in: TripSearchRequest, config_store: ConfigStore
) -> TripSearchResponse:
    """
    Retrieves airport pickup trip options based on the search request and configuration store.
    Args:
        search_in (TripSearchRequest): The trip search request containing origin and preferences.
        config_store (ConfigStore): The configuration store instance.
    Returns:
        TripSearchResponse: The trip search response containing available options.
    """
    # Retrieve airport pickup pricing configuration for the origin region
    configuration = _get_airport_pickup_pricing_configuration_by_region(
        region_code=search_in.origin.region_code, config_store=config_store
    )
    if not configuration:
        raise CabboException(
            f"No airport pickup pricing configuration found for region {search_in.origin.region_code}",
            status_code=404,
        )
    currency = config_store.geographies.country_server.currency_symbol

    validate_airport_schedule(search_in)  # Validate airport pickup schedule
    validate_placard_requirements(search_in)  # Validate placard requirements
    _, _, est_km = _get_trip_origin_destination_distance_airport_pickup(search_in)

    parking = (
        configuration.auxiliary_pricing.common.parking
        if configuration.auxiliary_pricing.common.parking is not None
        else 0.0
    )
    toll = _get_airport_toll(
        configuration.auxiliary_pricing.common.toll, search_in.toll_road_preferred
    )
    inclusions, exclusions = _get_inclusions_exclusions_for_airport_pickup(
        toll_road_preferred=search_in.toll_road_preferred,
        placard_required=search_in.placard_required,
    )

    airport_pricings = configuration.base_pricing
    package_short_label = "Airport Pickup"
    platform_fee_percent = (
        configuration.auxiliary_pricing.common.dynamic_platform_fee_percent
    )
    max_included_km = configuration.auxiliary_pricing.common.max_included_km
    warning_km_threshold = (
        configuration.auxiliary_pricing.common.overage_warning_km_threshold
    )
    options: List[TripSearchOption] = []

    for pricing, cab_type, fuel_type in airport_pricings:
        pricing_schema = AirportCabPricingSchema.model_validate(pricing)
        cab_type_schema = CabTypeSchema.model_validate(cab_type)
        fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
        base_fare_per_km = pricing_schema.fare_per_km

        overage_amount_per_km = pricing_schema.overage_amount_per_km
        placard_charge = (
            configuration.auxiliary_pricing.common.placard_charge
            if search_in.placard_required
            and configuration.auxiliary_pricing.common.placard_charge is not None
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

        margin = max_included_km - est_km  # Allow negative values for overage
        indicative_overage_warning = margin <= warning_km_threshold
        # Platform fee is a sum of a fixed cost(infra cost) to service fee and a percentage of the total price calculated before adding platform fee/convenience fee
        platform_fee_amount = config_store.platform_fee.fixed_platform_fee + (
            platform_fee_percent * total_price_before_platform_fee / 100
        )
        package_label = f"{package_short_label} | AC {cab_type_schema.name}({cab_type_schema.capacity}) - ({fuel_type_schema.name})"

        price_breakdown = AirportPricingBreakdownSchema(
            base_fare=math.ceil(base_price),
            placard_charge=math.ceil(placard_charge),
            toll=math.ceil(toll),
            parking=math.ceil(parking),
            platform_fee=math.ceil(platform_fee_amount),
        )
        disclaimer_lines = _get_airport_trips_disclaimer_lines(
            overage_amount_per_km, currency, max_included_km
        )
        disclaimer_message = (
            "Extra charges may apply: " + "\n - " + "\n - ".join(disclaimer_lines)
        )
        option = TripSearchOption(
            car_type=cab_type_schema.name,  # Use display name from schema
            fuel_type=fuel_type_schema.name,  # Use display name from schema
            total_price=math.ceil(
                total_price_before_platform_fee + price_breakdown.platform_fee
            ),
            included_km=max_included_km,
            price_breakdown=price_breakdown,
            package=package_label,  # Use package string for display
            package_short_label=package_short_label,
            overages=(
                OveragesSchema(
                    indicative_overage_warning=indicative_overage_warning,
                    overage_amount_per_km=(
                        overage_amount_per_km if indicative_overage_warning else 0.0
                    ),
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
            "No airport pickup trip options available for the given configuration",
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
        in_car_amenities=get_default_trip_amenities(),
        total_trip_days=1,
        estimated_km=est_km,
        included_km=(
            _options[0].included_km
            if _options and len(_options) > 0 and _options[0].included_km
            else None
        ),
        choices=len(_options),  # Total number of options returned
    )
     
    return TripSearchResponse(
        options=_options,
        preferences=search_in,
        metadata=metadata.model_dump(exclude_none=True, exclude_unset=True)
    )


def get_airport_dropoff_trip_options(
    search_in: TripSearchRequest, config_store: ConfigStore
) -> TripSearchResponse:
    """
    Retrieves airport dropoff trip options based on the search request and configuration store.
    Args:
        search_in (TripSearchRequest): The trip search request containing origin and preferences.
        config_store (ConfigStore): The configuration store instance.
    Returns:
        TripSearchResponse: The trip search response containing available options.
    """
    # Retrieve airport dropoff pricing configuration for the origin region
    configuration = _get_airport_dropoff_pricing_configuration_by_region(
        region_code=search_in.origin.region_code, config_store=config_store
    )
    if not configuration:
        raise CabboException(
            f"No airport dropoff pricing configuration found for region {search_in.origin.region_code}",
            status_code=404,
        )
    currency = config_store.geographies.country_server.currency_symbol

    validate_airport_schedule(search_in)  # Validate airport drop schedule
    _, _, est_km = _get_trip_origin_destination_distance_airport_drop(search_in)
    toll = _get_airport_toll(
        configuration.auxiliary_pricing.common.toll, search_in.toll_road_preferred
    )
    inclusions, exclusions = _get_inclusions_exclusions_for_airport_drop(
        toll_road_preferred=search_in.toll_road_preferred
    )

    airport_pricings = configuration.base_pricing
    package_short_label = "Airport Drop"
    platform_fee_percent = (
        configuration.auxiliary_pricing.common.dynamic_platform_fee_percent
    )
    max_included_km = configuration.auxiliary_pricing.common.max_included_km
    warning_km_threshold = (
        configuration.auxiliary_pricing.common.overage_warning_km_threshold
    )
    parking = 0.0  # No parking charges for airport drop
    options: List[TripSearchOption] = []
    for pricing, cab_type, fuel_type in airport_pricings:
        pricing_schema = AirportCabPricingSchema.model_validate(pricing)
        cab_type_schema = CabTypeSchema.model_validate(cab_type)
        fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
        base_fare_per_km = pricing_schema.fare_per_km
        overage_amount_per_km = pricing_schema.overage_amount_per_km
        base_price = base_fare_per_km * min(est_km, max_included_km)
        overage_amount = max(0, est_km - max_included_km) * overage_amount_per_km
        # Total price includes base fare, toll and parking charges (if any)
        # We wont add the overage charge to the total price for airport pickups because overages is an estimation and not a fixed charge
        # Overages will apply if at the end of the trip the actual distance is more than the estimated distance
        # This indicator is to ensure that the customer is aware that overage charges may apply for this route
        total_price_before_platform_fee = math.ceil(base_price + toll + parking)
        margin = max_included_km - est_km  # Allow negative values for overage
        indicative_overage_warning = margin <= warning_km_threshold
        # Platform fee is a sum of a fixed cost to service fee and a percentage of the total price calculated before adding platform fee
        platform_fee_amount = config_store.platform_fee.fixed_platform_fee + (
            platform_fee_percent * total_price_before_platform_fee / 100
        )
        package_label = f"{package_short_label} | AC {cab_type_schema.name}({cab_type_schema.capacity}) - ({fuel_type_schema.name})"
        price_breakdown = AirportPricingBreakdownSchema(
            base_fare=math.ceil(base_price),
            toll=math.ceil(toll),
            platform_fee=math.ceil(platform_fee_amount),
        )
        disclaimer_lines = _get_airport_trips_disclaimer_lines(
            overage_amount_per_km, currency, max_included_km
        )
        disclaimer_message = (
            "Extra charges may apply: " + "\n - " + "\n - ".join(disclaimer_lines)
        )
        option = TripSearchOption(
            car_type=cab_type_schema.name,  # Use display name
            fuel_type=fuel_type_schema.name,  # Use display name
            total_price=math.ceil(
                total_price_before_platform_fee + price_breakdown.platform_fee
            ),
            price_breakdown=price_breakdown,
            included_km=max_included_km,
            package=package_label,
            package_short_label=package_short_label,
            overages=(
                OveragesSchema(
                    indicative_overage_warning=indicative_overage_warning,
                    overage_amount_per_km=(
                        overage_amount_per_km if indicative_overage_warning else 0.0
                    ),
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
            "No airport dropoff trip options available for the given configuration",
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
        in_car_amenities=get_default_trip_amenities(),
        total_trip_days=1,
        estimated_km=est_km,
        included_km=(
            _options[0].included_km
            if _options and len(_options) > 0 and _options[0].included_km
            else None
        ),
        choices=len(_options),  # Total number of options returned
    )

    return TripSearchResponse(
        options=_options,
        preferences=search_in,
        metadata=metadata.model_dump(exclude_none=True, exclude_unset=True)
    )
