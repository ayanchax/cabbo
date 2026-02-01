from datetime import timedelta
import math
from typing import List

from core.constants import APP_NAME
from core.config import settings
from core.exceptions import CabboException
from core.store import ConfigStore
from core.trip_constants import COMMON_EXCLUSIONS, COMMON_INCLUSIONS
from core.trip_helpers import (
    derive_trip_sort_priority,
    generate_trip_field_dictionary,
    generate_trip_hash,
    get_default_trip_amenities,
)
from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema
from models.map.location_schema import LocationInfo
from models.pricing.pricing_schema import (
    LocalCabPricingSchema,
    LocalPricingBreakdownSchema,
    OveragesSchema,
    TripPackageConfigSchema,
)
from models.trip.trip_orm import Trip
from models.trip.trip_schema import (
    TripSearchAdditionalData,
    TripSearchOption,
    TripSearchRequest,
    TripSearchResponse,
)
from services.customer_service import get_customer_by_id
from services.driver_service import get_driver_by_id
from services.passenger_service import get_passenger_by_id

from services.validation_service import validate_local_trip_schedule
from utils.utility import validate_date_time
from sqlalchemy.orm import Session


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
    non_refund_line = "If you do not utilise your full package hours and/or kilometres, the full package amount will still be charged; unused hours/kilometres are non-refundable."
    if applicable_driver_allowance == 0.0:
        return [
            f"If you exceed the included hours and/or kilometres in your selected package ({package_label}), an additional charge of {currency}{overage_amount_per_hour} per hour and/or {currency}{overage_amount_per_km} per km will apply.",
            non_refund_line,
            "Any tolls incurred during the trip will be billed based on actual usage.",
            "If parking costs exceed the included wallet amount, the excess will be charged. If you use less, the unused balance will be refunded at trip end by adjusting the final fare.",
            "All extra charges are based on actual usage and will be clearly shown on your invoice.",
        ]
    return [
        f"If you exceed the included hours and/or kilometres in your selected package ({package_label}), an additional charge of {currency}{overage_amount_per_hour} per hour and/or {currency}{overage_amount_per_km} per km will apply.",
        f"If you exceed the included hours in your selected package ({package_label}), an additional driver allowance of {currency}{applicable_driver_allowance} will be charged.",
        non_refund_line,
        "Any tolls incurred during the trip will be billed based on actual toll charges.",
        "If parking costs exceed the included wallet amount, the excess will be charged. If you use less, the unused balance will be refunded at trip end by adjusting the final fare.",
        "All extra charges are based on actual usage and will be clearly shown on your invoice.",
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
        driver_allowance_amount =math.ceil(package.driver_allowance) if package.driver_allowance else 0.0
        total_price_before_platform_fee = base_fare  + driver_allowance_amount

        # Platform fee is a sum of a fixed cost(infra cost) to service and a percentage of the total price calculated before adding platform fee/convenience fee

        platform_fee_amount = config_store.platform_fee.fixed_platform_fee + (
            platform_fee_percent * total_price_before_platform_fee / 100
        )

        price_breakdown = LocalPricingBreakdownSchema(
            base_fare=math.ceil(base_fare),
            platform_fee=math.ceil(platform_fee_amount),
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
            included_kms=package_included_km,
            package=package_label,  # Use package string for display
            package_short_label=package_short_label,
            overages=(
                OveragesSchema(
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
    )


def get_kwargs_for_local_hourly_rental(
    customer_email: str,
    trip: Trip,
    currency: str,
    db: Session,
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

        customer_id = trip.creator_id

        if not customer_id or not customer_email:
            print("Invalid customer information for trip:", trip.booking_id)
            return {}  # Do not proceed if customer info is invalid

        # Get customer from customer_id
        customer = get_customer_by_id(customer_id, db)

        if not customer:
            print("Customer not found for trip:", trip.booking_id)
            return {}  # Do not proceed if customer not found

        customer_name = customer.name or customer_email.split("@")[0] or "Valued Customer"

        driver = get_driver_by_id(trip.driver_id, db) if trip.driver_id else None

        # Prepare inclusions and exclusions
        inclusions, exclusions = _get_inclusions_exclusions_for_local_trip()

        # Prepare in-car amenities
        in_car_amenities =  None
        if driver and driver.cab_amenities:
            in_car_amenities = driver.cab_amenities
        else:
            in_car_amenities= trip.in_car_amenities or {}

        in_car_amenities = {key: value for key, value in in_car_amenities.items() if value}

        # Prepare overages disclaimer
        overages = trip.overages or {}
        overages_disclaimer = overages.get("disclaimer") if overages else None
        extra_charges_disclaimers = overages.get("extra_charges_disclaimers") if overages else None
        passenger =get_passenger_by_id(trip.passenger_id, db) if trip.passenger_id else None
        passenger_name = passenger.name if passenger else None
        # Prepare kwargs for the Jinja template
        kwargs = {
            "customer_name": customer_name,
            "app_name": app_name,
            "app_url": app_url,
            "pickup_location": origin.address,
            "start_date": trip.start_datetime.strftime("%d %b %Y, %I:%M %p"),
            "expected_end_date": trip.expected_end_datetime.strftime("%d %b %Y, %I:%M %p") if trip.expected_end_datetime else None,
            "booking_id": trip.booking_id,
            "package_label": trip.package_label,
            "cab_type": driver.cab_type if driver else None,
            "fuel_type": driver.fuel_type if driver else None,
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
        }

       
        return kwargs
    except Exception as e:
        print("Error preparing kwargs for local hourly rental service:", str(e))
        return {}  # Return empty dict on error to avoid breaking email notifications
