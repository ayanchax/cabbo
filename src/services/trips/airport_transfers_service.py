import math
from typing import List, Optional, Union

from core.constants import APP_NAME
from core.exceptions import (
    CabboException,
    AIRPORT_PICKUP_DESTINATION_REQUIRED,
    GENERIC_EXCEPTION,
    DISTANCE_NOT_DETERMINED,
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
from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema, VehicleCapacitySchema
from models.customer.customer_orm import Customer
from models.customer.customer_schema import CustomerRead
from models.customer.passenger_schema import PassengerRequest
from models.driver.driver_schema import DriverReadSchema
from models.map.location_schema import LocationInfo
from models.pricing.pricing_schema import (
    AirportCabPricingSchema,
    AirportPricingBreakdownSchema,
    Currency,
    OveragesSchema,
)
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripTypeEnum
from models.trip.trip_orm import Trip
from models.trip.trip_schema import (
    TripSearchAdditionalData,
    TripSearchOption,
    TripSearchRequest,
    TripSearchResponse,
)
from services.cab_service import get_car_type_rank, get_recommended_car_type
from services.location_service import get_distance_km
from core.config import settings
from services.policy_service import (
    get_refund_and_cancellation_policy_by_jurisdiction_code,
    get_refund_and_cancellation_policy_lines,
)
from services.pricing_service import compute_base_platform_fee, compute_platform_fee_with_tax
from services.validation_service import (
    validate_airport_schedule,
    validate_placard_requirements,
)
from utils.utility import format_trip_datetime
import logging
log = logging.getLogger(__name__)

def _get_inclusions_exclusions_for_airport_drop(toll_road_preferred: bool = False):
    """
    Returns the inclusions and exclusions for airport drop trips.
    Returns:
        Tuple[List[str], List[str]]:
            - inclusions (List[str]): List of inclusions for the trip.
            - exclusions (List[str]): List of exclusions for the trip.
    """
    inclusion_labels = COMMON_INCLUSIONS[:]  # base set
    if toll_road_preferred:
        inclusion_labels.insert(1, "Toll")  # keep Toll early in the list
    inclusion_labels.extend(["Water bottles and tissues"])

    exclusion_labels = COMMON_EXCLUSIONS[:]
    return build_inclusion_items(inclusion_labels), build_exclusion_items(
        exclusion_labels
    )


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
        raise CabboException(
            "Origin is required for airport drop",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )

    if not search_in.destination:
        search_in.destination = None

    if not search_in.destination:
        raise CabboException(
            "Destination is required for airport drop",
            status_code=400,
            error_code=AIRPORT_PICKUP_DESTINATION_REQUIRED,
        )
    est_km = get_distance_km(origin=search_in.origin, destination=search_in.destination)
    if not est_km or est_km <= 0:
        raise CabboException(
            "Could not estimate distance between origin and destination",
            status_code=400,
            error_code=DISTANCE_NOT_DETERMINED,
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
        raise CabboException(
            "Origin is required", status_code=400, error_code=GENERIC_EXCEPTION
        )

        # Origin is airport, destination is required
    if not search_in.destination:
        raise CabboException(
            "Destination is required",
            status_code=400,
            error_code=AIRPORT_PICKUP_DESTINATION_REQUIRED,
        )
    est_km = get_distance_km(origin=search_in.origin, destination=search_in.destination)
    if not est_km or est_km <= 0:
        raise CabboException(
            "Could not estimate distance between origin and destination",
            status_code=400,
            error_code=DISTANCE_NOT_DETERMINED,
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
    inclusion_labels = COMMON_INCLUSIONS[:]  # base set
    if toll_road_preferred:
        inclusion_labels.append("Toll")
    inclusion_labels.append("Parking")
    if placard_required:
        inclusion_labels.append("Placard charges")
    inclusion_labels.append("Water bottles and tissues")
    exclusion_labels = COMMON_EXCLUSIONS[:]  # base set
    return build_inclusion_items(inclusion_labels), build_exclusion_items(
        exclusion_labels
    )


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
    return config_store.airport_pickup.get(region_code, None)


def _get_airport_trips_disclaimer_lines(
    includes_placard: bool = False,
    includes_parking: bool = False,
    includes_tolls: bool = False,
) -> List[str]:
    """
    Returns the disclaimer lines for airport trips.

    Airport transfers are priced upfront from the estimated route distance, so the
    standard disclaimer should not ask drivers to collect route-distance overages.

    Returns:
        List[str]: A list of disclaimer lines for airport trips.
    """
    return _get_airport_trips_common_disclaimer_lines(
        includes_tolls=includes_tolls,
        includes_parking=includes_parking,
        includes_placard=includes_placard,
    )


def _get_airport_trips_common_disclaimer_lines(
    includes_tolls: bool = False,
    includes_parking: bool = False,
    includes_placard: bool = False,
) -> List[str]:
    """
    Returns the common disclaimer lines for airport trips.

    The caller passes in fare inclusions so the customer-facing copy stays definite:
    pickup parking is included for airport pickup, and tolls are included only when the
    customer selected the toll-road route.

    Returns:
        List[str]: A list of common disclaimer lines for airport trips.
    """
    included_charges = []
    if includes_tolls:
        included_charges.append("standard airport toll-road charge")
    if includes_parking:
        included_charges.append("airport parking")
    if includes_placard:
        included_charges.append("placard charges")

    included_charges_text = ""
    if included_charges:
        if len(included_charges) == 1:
            included_charges_label = included_charges[0]
        elif len(included_charges) == 2:
            included_charges_label = " and ".join(included_charges)
        else:
            included_charges_label = (
                f"{', '.join(included_charges[:-1])} and {included_charges[-1]}"
            )
        included_charges_text = f" This fare includes {included_charges_label}."

    disclaimer_lines = [
        f"Fare applies to the selected airport transfer route.{included_charges_text}"
    ]

    if includes_tolls:
        disclaimer_lines.append(
            "The included toll-road charge covers the standard airport toll for this route only. If your journey crosses any other toll gates, please pay any extra tolls directly to the driver."
        )
        disclaimer_lines.append(
                    "Extra charges may apply for customer-requested route changes, detours, additional stops, waiting, paid parking or charges outside the selected fare."
                )
    else:
        disclaimer_lines.append(
            "Extra charges may apply for tolls, customer-requested route changes, detours, additional stops, waiting, paid parking or charges outside the selected fare."
        )

    return disclaimer_lines


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
    currency_code = config_store.geographies.country_server.currency

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
    min_included_km = configuration.auxiliary_pricing.common.min_included_km or 0
    options: List[TripSearchOption] = []

    for pricing, cab_type, fuel_type in airport_pricings:
        pricing_schema = AirportCabPricingSchema.model_validate(pricing)
        if not pricing_schema.is_available_in_network:
            continue  # Skip pricings for cab-fuel pairs not available in the network
        cab_type_schema = CabTypeSchema.model_validate(cab_type)
        #Despite picking only available pricings in network that pairs with active cab types and fuel types from the configuration store at app startup, we are adding an additional check here to ensure that only active and available cab-fuel pairs are considered for pricing. This is a safeguard against any potential misconfigurations or changes in the configuration that might introduce inactive or unavailable options. By skipping any inactive or unavailable cab-fuel pairs, we ensure that customers are only presented with valid and bookable options, enhancing the user experience and preventing potential booking issues.
        if not cab_type_schema.is_active:
                continue  # Skip inactive cab types
                
        fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
        if not fuel_type_schema.is_active:
                continue  # Skip inactive fuel types
        base_fare_per_km = pricing_schema.fare_per_km

        placard_charge = (
            configuration.auxiliary_pricing.common.placard_charge
            if search_in.placard_required
            and configuration.auxiliary_pricing.common.placard_charge is not None
            else 0.0
        )
        billable_km = max(est_km, min_included_km)
        base_price = base_fare_per_km * billable_km
        # Airport transfers are deterministic route fares. Extreme distances are
        # routed to the correct domain during trip-type classification, so
        # max_included_km is not used as a billing cap here.
        total_price_before_platform_fee = math.ceil(
            base_price + toll + parking + placard_charge
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

        package_label = f"{package_short_label} | AC {cab_type_schema.name}({cab_type_schema.capacity}) - ({fuel_type_schema.name})"

        price_breakdown = AirportPricingBreakdownSchema(
            base_fare=math.ceil(base_price),
            placard_charge=math.ceil(placard_charge),
            toll=math.ceil(toll),
            parking=math.ceil(parking),
            **platform_fee_components,
        )
        disclaimer_lines = _get_airport_trips_disclaimer_lines(
            includes_placard=search_in.placard_required,
            includes_parking=True,
            includes_tolls=search_in.toll_road_preferred,
        )

        total_price = math.ceil(
            total_price_before_platform_fee + price_breakdown.platform_fee
        )

        rate_per_km = round(price_breakdown.base_fare / billable_km)

        option = TripSearchOption(
            car_type=CarTypeEnum(cab_type_schema.name),  # Use display name
            car_capacity=VehicleCapacitySchema(
                passenger_capacity=cab_type_schema.passenger_capacity,
                luggage_capacity=cab_type_schema.total_luggages,
                capacity_match=(
                    search_in.total_passengers <= cab_type_schema.passenger_capacity
                    and search_in.total_luggages <= cab_type_schema.total_luggages
                    if cab_type_schema.passenger_capacity is not None
                    and cab_type_schema.luggage_capacity is not None
                    else False
                ),
                
                rank=get_car_type_rank(CarTypeEnum(cab_type_schema.name)),
                roof_carrier=cab_type_schema.roof_carrier
            ),
            fuel_type=fuel_type_schema.name,  # Use display name from schema
            total_price=total_price,
            included_kms=billable_km,
            price_breakdown=price_breakdown,
            package=package_label,  # Use package string for display
            package_short_label=package_short_label,
            overages=(
                OveragesSchema(
                    indicative_overage_warning=False,
                    disclaimer=disclaimer_lines,
                ).model_dump(exclude_none=True, exclude_unset=True)
            ),
            currency=Currency(symbol=currency, code = currency_code ) if currency else Currency(),
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
            "No airport pickup trip options available for the given configuration",
            status_code=404,
        )
    cancelation_refund_policy = get_refund_and_cancellation_policy_by_jurisdiction_code(
        trip_type=search_in.trip_type,
        jurisdiction_code=search_in.origin.region_code,
        config_store=config_store,
    )  # Ensure refund policy exists for local trips in the region

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
        in_car_amenities=get_default_trip_amenities(),
        total_trip_days=1,
        estimated_km=est_km,
        included_kms=(
            _options[0].included_kms
            if _options and len(_options) > 0 and _options[0].included_kms
            else None
        ),
        choices=len(_options),  # Total number of options returned
    )

    return TripSearchResponse(
        options=_options,
        preferences=remove_extra_fields_from_airport_transfer_trip(search_in.model_dump(exclude_none=True, exclude_unset=True), trip_type=TripTypeEnum.airport_pickup),
        metadata=metadata.model_dump(exclude_none=True, exclude_unset=True),
        disclaimers=_get_airport_trips_common_disclaimer_lines(
            includes_tolls=search_in.toll_road_preferred,
            includes_parking=True,
            includes_placard=search_in.placard_required,
        ),
        refund_and_cancellation_policy=get_refund_and_cancellation_policy_lines(
            policy=cancelation_refund_policy, trip_startdate_time=search_in.start_date, trip_timezone=search_in.timezone
        ),
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
    currency_code = config_store.geographies.country_server.currency
    
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
    min_included_km = configuration.auxiliary_pricing.common.min_included_km or 0
    parking = 0.0  # No parking charges for airport drop
    options: List[TripSearchOption] = []
    for pricing, cab_type, fuel_type in airport_pricings:
        pricing_schema = AirportCabPricingSchema.model_validate(pricing)
        #Despite picking only available pricings in network that pairs with active cab types and fuel types from the configuration store at app startup, we are adding an additional check here to ensure that only active and available cab-fuel pairs are considered for pricing. This is a safeguard against any potential misconfigurations or changes in the configuration that might introduce inactive or unavailable options. By skipping any inactive or unavailable cab-fuel pairs, we ensure that customers are only presented with valid and bookable options, enhancing the user experience and preventing potential booking issues.
        if not pricing_schema.is_available_in_network:
            continue  # Skip pricings for cab-fuel pairs not available in the network
        cab_type_schema = CabTypeSchema.model_validate(cab_type)
        if not cab_type_schema.is_active:
            continue  # Skip inactive cab types
        fuel_type_schema = FuelTypeSchema.model_validate(fuel_type)
        if not fuel_type_schema.is_active:
            continue  # Skip inactive fuel types
        base_fare_per_km = pricing_schema.fare_per_km
        billable_km = max(est_km, min_included_km)
        base_price = base_fare_per_km * billable_km
        # Airport transfers are deterministic route fares. Extreme distances are
        # routed to the correct domain during trip-type classification, so
        # max_included_km is not used as a billing cap here.
        total_price_before_platform_fee = math.ceil(base_price + toll + parking)
        # Platform fee is a sum of a fixed cost to service fee and a percentage of the total price calculated before adding platform fee
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

        package_label = f"{package_short_label} | AC {cab_type_schema.name}({cab_type_schema.capacity}) - ({fuel_type_schema.name})"
        price_breakdown = AirportPricingBreakdownSchema(
            base_fare=math.ceil(base_price),
            toll=math.ceil(toll),
            **platform_fee_components,
        )
        disclaimer_lines = _get_airport_trips_disclaimer_lines(
            includes_tolls=search_in.toll_road_preferred,
        )

        total_price = math.ceil(
            total_price_before_platform_fee + price_breakdown.platform_fee
        )
        rate_per_km = round(price_breakdown.base_fare / billable_km)

        option = TripSearchOption(
            car_type=CarTypeEnum(cab_type_schema.name),  # Use display name
            car_capacity=VehicleCapacitySchema(
                passenger_capacity=cab_type_schema.passenger_capacity,
                luggage_capacity=cab_type_schema.total_luggages,
                capacity_match=(
                    search_in.total_passengers <= cab_type_schema.passenger_capacity
                    and search_in.total_luggages <= cab_type_schema.total_luggages
                    if cab_type_schema.passenger_capacity is not None
                    and cab_type_schema.luggage_capacity is not None
                    else False
                ),
                rank=get_car_type_rank(CarTypeEnum(cab_type_schema.name)),
                roof_carrier=cab_type_schema.roof_carrier
            ),
            fuel_type=fuel_type_schema.name,  # Use display name
            total_price=total_price,
            price_breakdown=price_breakdown,
            included_kms=billable_km,
            package=package_label,
            package_short_label=package_short_label,
            overages=(
                OveragesSchema(
                    indicative_overage_warning=False,
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
            "No airport dropoff trip options available for the given configuration",
            status_code=404,
        )
    cancelation_refund_policy = get_refund_and_cancellation_policy_by_jurisdiction_code(
        trip_type=search_in.trip_type,
        jurisdiction_code=search_in.origin.region_code,
        config_store=config_store,
    )  # Ensure refund policy exists for local trips in the region

    # Intelligent sorting based on user preferences and trip context
    recommended_car_type = get_car_type(search_in)
    eligible_options = [
        option for option in options if option.car_capacity.capacity_match
    ]
    _options = populate_best_choice_recommendation(
        eligible_options=eligible_options,
        recommended_car_type=recommended_car_type,
    )
    metadata = TripSearchAdditionalData(
        inclusions=inclusions,
        exclusions=exclusions,
        in_car_amenities=get_default_trip_amenities(),
        total_trip_days=1,
        estimated_km=est_km,
        included_kms=(
            _options[0].included_kms
            if _options and len(_options) > 0 and _options[0].included_kms
            else None
        ),
        choices=len(_options),  # Total number of options returned
    )

    return TripSearchResponse(
        options=_options,
        preferences=remove_extra_fields_from_airport_transfer_trip(search_in.model_dump(exclude_none=True, exclude_unset=True), trip_type=TripTypeEnum.airport_drop),
        metadata=metadata.model_dump(exclude_none=True, exclude_unset=True),
        disclaimers=_get_airport_trips_common_disclaimer_lines(
            includes_tolls=search_in.toll_road_preferred,
        ),
        refund_and_cancellation_policy=get_refund_and_cancellation_policy_lines(
            policy=cancelation_refund_policy, trip_startdate_time=search_in.start_date, trip_timezone=search_in.timezone
        ),
    )


def get_kwargs_for_airport_transfer(
    trip_type: TripTypeEnum,
    trip: Trip,
    currency: str,
    customer: Optional[Union[Customer, CustomerRead]] = None,
) -> dict:
    try:
        if not trip or not trip.booking_id:
            log.error("Invalid trip information.")
            return (
                {}
            )  # Do not proceed if trip info is invalid, do not raise exception here as this is used for email notifications that will mostly fail silently

        app_name = APP_NAME.capitalize()
        app_url = settings.APP_URL

        # Validate and extract origin and destination
        origin = LocationInfo.model_validate(trip.origin)
        destination = LocationInfo.model_validate(trip.destination)

        if not origin or not destination:
            log.error("Invalid origin or destination for trip:", trip.booking_id)
            return (
                {}
            )  # Do not proceed if origin or destination is invalid, do not raise exception here as this is used for email notifications that will mostly fail silently

        if not customer:
            customer_id = trip.creator_id

            if not customer_id:
                log.error("Invalid customer information for trip:", trip.booking_id)
                return (
                    {}
                )  # Do not proceed if customer info is invalid, do not raise exception here as this is used for email notifications that will mostly fail silently

            # Get customer from customer_id
            customer = (
                trip.customer
                if trip.creator_id and trip.creator_type == "customer"
                else None
            )
            customer = CustomerRead.model_validate(customer) if customer else None

            if not customer:
                log.error("Customer not found for trip:", trip.booking_id)
                return (
                    {}
                )  # Do not proceed if customer not found, do not raise exception here as this is used for email notifications that will mostly fail silently

            customer_name = customer.name or "Valued Customer"

            customer_email = customer.email or None
        else:
            customer_name = customer.name or "Valued Customer"
            customer_email = customer.email or None

        driver = trip.driver if trip.driver_id else None
        driver = DriverReadSchema.model_validate(driver) if driver else None

        # Prepare luggage information
        luggage_info = None
        if (
            trip.num_luggages and trip.num_luggages > 0
        ):  # Only include luggage info if num_luggages > 0
            luggage_parts = []
            if trip.num_large_suitcases and trip.num_large_suitcases > 0:
                luggage_parts.append(f"{trip.num_large_suitcases} large suitcases")
            if trip.num_carryons and trip.num_carryons > 0:
                luggage_parts.append(f"{trip.num_carryons} carry-ons")
            if trip.num_backpacks and trip.num_backpacks > 0:
                luggage_parts.append(f"{trip.num_backpacks} backpacks")
            luggage_info = ", ".join(luggage_parts) if luggage_parts else None

        # Prepare special requests
        special_requests = (
            trip.special_needs_requests if trip.special_needs_requests else None
        )
        passenger = trip.passenger if trip.passenger_id else None
        passenger = PassengerRequest.model_validate(passenger) if passenger else None
        passenger_name = passenger.name if passenger else None
        # Prepare kwargs for the Jinja template
        kwargs = {
            "customer_email": customer_email,
            "customer_name": customer_name,
            "app_name": app_name,
            "app_url": app_url,
            "trip_type": trip_type.value,
            "pickup_location": origin.address,
            "drop_location": destination.address,
            "booking_id": trip.booking_id,
            "trip_date": format_trip_datetime(
                trip.start_datetime, trip.timezone
            ).strftime(
                "%d %b %Y"
            ),  # Format date
            "trip_time": format_trip_datetime(
                trip.start_datetime, trip.timezone
            ).strftime(
                "%I:%M %p"
            ),  # Format time
            "luggage_info": luggage_info,
            "placard_name": (
                trip.placard_name
                if trip.placard_required and trip.placard_name
                else None
            ),
            "flight_number": trip.flight_number if trip.flight_number else None,
            "special_requests": special_requests,
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
            "timezone": trip.timezone,
        }

        return kwargs
    except Exception as e:
        log.error("Error preparing kwargs for airport transfer:", str(e))
        return {}  # Return empty dict on error to avoid breaking email notifications


def get_car_type(search_in: TripSearchRequest) -> CarTypeEnum:
    total_pax = search_in.total_passengers

    return get_recommended_car_type(
        total_num_people=total_pax, total_num_luggages=search_in.total_luggages
    )


def derive_trip_sort_priority(
    recommended_car_type: CarTypeEnum, option: TripSearchOption
):
    minimum_car_type = recommended_car_type
    minimum_rank = get_car_type_rank(minimum_car_type)
    option_rank = get_car_type_rank(option.car_type)

    if option_rank < minimum_rank:
        capacity_score = 1000 + ((minimum_rank - option_rank) * 100)
    else:
        capacity_score = (option_rank - minimum_rank) * 100

    return (capacity_score, option.total_price)


def remove_extra_fields_from_airport_transfer_trip(
    trip_dict: dict, trip_type: TripTypeEnum
) -> dict:
    keys_to_remove = [
        "created_at",
        "creator_id",
        "creator_type",
        "estimated_km",
        "final_display_price",
        "indicative_overage_warning",
        "is_active",
        "is_interstate",
        "is_round_trip",
        "package_label",
        "package_label_short",
        "parking",
        "permit_fee",
        "payment_provider_metadata",
        "platform_fee",
        "preferred_car_type",
        "preferred_fuel_type",
        "total_unique_states",
        "unique_states",
        "rate_per_km",
        "rate_per_min",
        "tolls",
        "total_days",
        "updated_at",
        "utc_offset",
        "driver_allowance",
        "expected_end_datetime",
        "included_kms",
    ]
    if trip_type == TripTypeEnum.airport_drop:
        # We do not need these fields for airport drop trips, but they are required for airport pickup trips, so we will only remove them for airport drop trips
        keys_to_remove.extend(
            ["placard_required", "flight_number", "terminal_number", "placard_name"]
        )

    # Toll is only relevant for airport pickup and drop trips when the customer has selected the toll road preference, so we can remove it for all airport drop trips and for airport pickup trips where toll road is not preferred
    if trip_dict.get("toll_road_preferred", False) == False:
        keys_to_remove.append("toll_road_preferred")
    for key in keys_to_remove:
        trip_dict.pop(key, None)
    return trip_dict

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
        recommended_candidates = [
            option
            for option in sorted_options
            if option.car_type == recommended_car_type
            and option.fuel_type == FuelTypeEnum.diesel
        ]

    if not recommended_candidates:
        recommended_candidates = [
            option
            for option in sorted_options
            if option.car_type == recommended_car_type
        ]

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

