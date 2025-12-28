from datetime import timedelta
import math
from typing import List
from core.exceptions import CabboException
from core.store import ConfigStore
from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema
from models.pricing.pricing_schema import (
    LocalCabPricingSchema,
    LocalPricingBreakdownSchema,
    OveragesSchema,
    TripPackageConfigSchema,
)
from models.trip.trip_schema import (
    TripSearchAdditionalData,
    TripSearchOption,
    TripSearchRequest,
    TripSearchResponse,
)
from services.pricing_service import get_preauthorized_minimum_wallet_amount
from services.trips.trip_service import (
    COMMON_EXCLUSIONS,
    COMMON_INCLUSIONS,
    derive_trip_sort_priority,
    generate_trip_field_dictionary,
    generate_trip_hash,
    get_default_trip_amenities,
)
from services.validation_service import validate_local_trip_schedule
from utils.utility import validate_date_time


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
            "Minimum parking allowance",
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
    if applicable_driver_allowance == 0.0:
        return [
            f"If you exceed the included hours and/or kilometers in your selected package ({package_label}), {currency}{overage_amount_per_hour} per additional hour and/or {currency}{overage_amount_per_km} per additional km will be charged.",
            "If any tolls are incurred during your trip, they will be billed based on actual usage.",
            "If parking costs exceed the included wallet amount, the extra will be charged. If you use less, the unused balance will be refunded at the end of your trip by adjusting the final fare.",
            "All extra charges are based on actual usage and will be transparently shown in your invoice.",
        ]
    return [
        f"If you exceed the included hours and/or kilometers in your selected package ({package_label}), {currency}{overage_amount_per_hour} per additional hour and/or {currency}{overage_amount_per_km} per additional km will be charged.",
        f"If you exceed the included hours in your selected package ({package_label}), an additional driver allowance of {currency}{applicable_driver_allowance} will be charged.",
        "If any tolls are incurred during your trip, they will be billed based on actual usage.",
        "If parking costs exceed the included wallet amount, the extra will be charged. If you use less, the unused balance will be refunded at the end of your trip by adjusting the final fare.",
        "All extra charges are based on actual usage and will be transparently shown in your invoice.",
    ]


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
    # Minimum parking wallet amount is configured to 80 for local trips, if the total cost of the parking goes above the minimum parking amount, then the surplus amount will be charged to the customer accordingly, otherwise the left/unused amount will be refunded(deducted from final bill) to the customer.

    minimum_parking_wallet = get_preauthorized_minimum_wallet_amount(
        configuration.auxiliary_pricing.common.minimum_parking_wallet
    )
    # Get the package ID if provided, otherwise use configs.min_included_hours for duration

    package = _get_trip_package_by_id(
        package_id=search_in.package_id,
        packages=configuration.auxiliary_pricing.trip_packages,
    )

    package_short_label = package.package_label
    package_included_hours = package.included_hours
    package_included_km = package.included_km

    expected_end_date = validate_date_time(search_in.start_date) + timedelta(
        hours=package_included_hours
    )
    search_in.expected_end_date = str(
        expected_end_date
    )  # Ensure expected end date is set for local trips

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
        # No tolls are added for local trips as for local trips toll cannot be estimated or walleted in advance, if any tolls are incurred, they will be charged accordingly to the customer once the trip is completed
        total_price_before_platform_fee = base_fare + minimum_parking_wallet

        # Platform fee is a sum of a fixed cost(infra cost) to service and a percentage of the total price calculated before adding platform fee/convenience fee

        platform_fee_amount = config_store.platform_fee.fixed_platform_fee + (
            platform_fee_percent * total_price_before_platform_fee / 100
        )

        price_breakdown = LocalPricingBreakdownSchema(
            base_fare=math.ceil(base_fare),
            minimum_parking_wallet=math.ceil(minimum_parking_wallet),
            platform_fee=math.ceil(platform_fee_amount),
            driver_allowance=(
                math.ceil(package.driver_allowance) if package.driver_allowance else 0.0
            ),
        )
        # For local trips, we can't estimate distance in advance since routes are uncertain and hence no est_km is provided.
        # Overage charges will be initially presented as 0.00 and will be calculated only if the customer exceeds the included hours or km, to keep them informed through a disclaimer message that extra charges may apply at the end of the trip.
        overage_amount_per_km = pricing_schema.overage_amount_per_km
        overage_amount_per_hour = pricing_schema.overage_amount_per_hour
        disclaimer_lines = _get_local_trips_disclaimer_lines(
            package_label=package.package_label,
            overage_amount_per_hour=overage_amount_per_hour,
            overage_amount_per_km=overage_amount_per_km,
            applicable_driver_allowance=price_breakdown.driver_allowance,
            currency=currency,
        )

        disclaimer_message = (
            "Extra charges may apply: " + "\n - " + "\n - ".join(disclaimer_lines)
        )
        package_label = f"{package_short_label} | AC {cab_type_schema.name}({cab_type_schema.capacity}) - ({fuel_type_schema.name})"
        option = TripSearchOption(
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
                    disclaimer=disclaimer_lines,
                    extra_charges_disclaimers=disclaimer_message,
                )
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
            "No local trip options available for the selected region and criteria.",
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
        total_trip_days=1,
        included_hours=(
            _options[0].included_hours
            if _options and len(_options) > 0 and _options[0].included_hours
            else None
        ),
        included_km=(
            _options[0].included_km
            if _options and len(_options) > 0 and _options[0].included_km
            else None
        ),
        choices=len(_options),  # Total number of options returned
        is_round_trip=True,
    )

    return TripSearchResponse(
        options=_options,
        preferences=search_in,
        metadata=metadata,
    )
