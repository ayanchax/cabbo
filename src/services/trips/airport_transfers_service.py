import math
from typing import List, Optional, Union

from core.constants import APP_NAME
from core.exceptions import CabboException
from core.store import ConfigStore
from core.trip_constants import COMMON_EXCLUSIONS, COMMON_INCLUSIONS
from core.trip_helpers import derive_trip_sort_priority, generate_trip_field_dictionary, generate_trip_hash, get_default_trip_amenities
from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema
from models.customer.customer_orm import Customer
from models.map.location_schema import LocationInfo
from models.pricing.pricing_schema import (
    AirportCabPricingSchema,
    AirportPricingBreakdownSchema,
    OveragesSchema,
)
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_orm import Trip
from models.trip.trip_schema import (
    TripSearchAdditionalData,
    TripSearchOption,
    TripSearchRequest,
    TripSearchResponse,
)
from services.customer_service import get_customer_by_id
from services.driver_service import get_driver_by_id
from services.location_service import get_distance_km
from core.config import settings
from services.passenger_service import get_passenger_by_id
from services.validation_service import (
    validate_airport_schedule,
    validate_placard_requirements,
)
from sqlalchemy.orm import Session


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
        f"If you exceed the included kilometres ({included_kms}) for this airport transfer, an additional charge of {currency}{overage_amount_per_km} per kilometre will apply.",
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
            included_kms=max_included_km,
            price_breakdown=price_breakdown,
            package=package_label,  # Use package string for display
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
        included_kms=(
            _options[0].included_kms
            if _options and len(_options) > 0 and _options[0].included_kms
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
            included_kms=max_included_km,
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
        included_kms=(
            _options[0].included_kms
            if _options and len(_options) > 0 and _options[0].included_kms
            else None
        ),
        choices=len(_options),  # Total number of options returned
    )

    return TripSearchResponse(
        options=_options,
        preferences=search_in,
        metadata=metadata.model_dump(exclude_none=True, exclude_unset=True)
    )

def get_kwargs_for_airport_transfer(
    trip_type: TripTypeEnum, 
    trip: Trip, 
    currency: str,
    db: Session,
    customer:Optional[Customer]=None
) -> dict:
    try:
        if not trip or not trip.booking_id:
            print("Invalid trip information.")
            return {} # Do not proceed if trip info is invalid, do not raise exception here as this is used for email notifications that will mostly fail silently
        
        app_name = APP_NAME.capitalize()
        app_url = settings.APP_URL

        # Validate and extract origin and destination
        origin = LocationInfo.model_validate(trip.origin)
        destination = LocationInfo.model_validate(trip.destination)

        if not origin or not destination:
            print("Invalid origin or destination for trip:", trip.booking_id)
            return {} # Do not proceed if origin or destination is invalid, do not raise exception here as this is used for email notifications that will mostly fail silently

        if not customer:
            customer_id = trip.creator_id 
            
            if not customer_id:
                print("Invalid customer information for trip:", trip.booking_id)
                return {} # Do not proceed if customer info is invalid, do not raise exception here as this is used for email notifications that will mostly fail silently
            
            #Get customer from customer_id
            customer = get_customer_by_id(customer_id, db)
            
            if not customer:
                print("Customer not found for trip:", trip.booking_id)
                return {} # Do not proceed if customer not found, do not raise exception here as this is used for email notifications that will mostly fail silently
            
            customer_name = customer.name or "Valued Customer"
            
            customer_email = customer.email or None
        else:
            customer_name = customer.name or "Valued Customer"
            customer_email = customer.email or None
            
        driver= get_driver_by_id(trip.driver_id, db) if trip.driver_id else None
        

        # Prepare luggage information
        luggage_info = None
        if trip.num_luggages and trip.num_luggages > 0:  # Only include luggage info if num_luggages > 0
            luggage_parts = []
            if trip.num_large_suitcases and trip.num_large_suitcases > 0:
                luggage_parts.append(f"{trip.num_large_suitcases} large suitcases")
            if trip.num_carryons and trip.num_carryons > 0:
                luggage_parts.append(f"{trip.num_carryons} carry-ons")
            if trip.num_backpacks and trip.num_backpacks > 0:
                luggage_parts.append(f"{trip.num_backpacks} backpacks")
            luggage_info = ", ".join(luggage_parts) if luggage_parts else None

        # Prepare special requests
        special_requests = trip.special_needs_requests if trip.special_needs_requests else None
        passenger =get_passenger_by_id(trip.passenger_id, db) if trip.passenger_id else None
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
            "trip_date": trip.start_datetime.strftime("%d %b %Y"),  # Format date
            "trip_time": trip.start_datetime.strftime("%I:%M %p"),  # Format time
            "luggage_info": luggage_info,
            "placard_name": trip.placard_name if trip.placard_required and trip.placard_name else None,
            "flight_number": trip.flight_number if trip.flight_number else None,
            "special_requests": special_requests,
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
        }

        return kwargs
    except Exception as e:
        print("Error preparing kwargs for airport transfer:", str(e))
        return {}  # Return empty dict on error to avoid breaking email notifications