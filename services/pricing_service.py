# Stub for pricing logic service
from typing import List
from models.cab.pricing_schema import (
    AirportCabPricingSchema,
    AirportPricingBreakdownSchema,
    OverageWarningConfigSchema,
    TollParkingConfigSchema,
    PlatformPricingConfigSchema,
    CabTypeSchema,
    FuelTypeSchema,
)
from models.trip.trip_orm import TripTypeMaster
from models.trip.trip_schema import (
    TripSearchRequest,
    TripSearchOption,
    TripTypeWiseConfig,
)
from sqlalchemy.orm import Session
from models.cab.pricing_orm import (
    CabType,
    FuelType,
    AirportCabPricing,
    PlatformPricingConfig,
)
from models.trip.trip_enums import CarTypeEnum, TripTypeEnum
from core.exceptions import CabboException
from services.location_service import get_distance_km
from models.geography.geo_enums import APP_AIRPORT_LOCATION
from core.constants import APP_HOME_STATE
from models.cab.pricing_orm import OverageWarningConfig, TollParkingConfig
import math


def retrieve_trip_type_wise_common_pricing_config(
    db: Session, trip_type: TripTypeEnum
) -> TripTypeWiseConfig:
    """
    Returns a TripTypeWiseConfig object with warning_config, toll_parking_charge, and platform_fee_config for the given trip_type.
    Handles wildcard logic for airport trip types (pickup/drop).
    """
    is_airport_trip = str(trip_type).startswith(TripTypeEnum.airport_general) or (
        trip_type
        in [
            TripTypeEnum.airport_pickup,
            TripTypeEnum.airport_drop,
        ]
    )
    filter_by = trip_type if not is_airport_trip else TripTypeEnum.airport_general
    wildcard_filter_by = (
        trip_type.value
        if not is_airport_trip
        else f"{TripTypeEnum.airport_general.value}%"
    )
    warning_config_orm = (
        db.query(OverageWarningConfig).filter_by(trip_type=filter_by).first()
    )
    toll_parking_charge_orm = (
        db.query(TollParkingConfig).filter_by(trip_type=filter_by).first()
    )
    platform_fee_config_orm = (
        db.query(PlatformPricingConfig)
        .join(TripTypeMaster, PlatformPricingConfig.trip_type_id == TripTypeMaster.id)
        .filter(TripTypeMaster.trip_type.like(wildcard_filter_by))
        .first()
    )
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
    return TripTypeWiseConfig(
        warning_config=warning_config,
        toll_parking_charge=toll_parking_charge,
        platform_fee_config=platform_fee_config,
    )


def get_trip_search_options(search_in: TripSearchRequest, db: Session) -> list:
    """
    Returns a list of TripSearchOption based on trip type, cab type, fuel type, and all pricing configs in DB.
    Handles all business rules for date/time, location, and placard charge.
    """

    options: List[TripSearchOption] = []
    configs = retrieve_trip_type_wise_common_pricing_config(db, search_in.trip_type)
    warning_config = configs.warning_config
    toll_parking_charge = configs.toll_parking_charge
    platform_fee_config = configs.platform_fee_config

    platform_fee_percent = (
        platform_fee_config.platform_fee_percent if platform_fee_config else 0.0
    )
    toll = toll_parking_charge.toll if toll_parking_charge else 0.0
    parking = toll_parking_charge.parking if toll_parking_charge else 0.0

    if search_in.trip_type == TripTypeEnum.airport_pickup:  # from airport
        if not search_in.origin:
            search_in.origin = APP_AIRPORT_LOCATION.get(APP_HOME_STATE, None)
        if not search_in.origin:
            raise CabboException("Origin is required", status_code=400)

        # Origin is airport, destination is required
        if not search_in.destination:
            raise CabboException("Destination is required", status_code=400)
        est_km = get_distance_km(
            origin=search_in.origin, destination=search_in.destination
        )
        if not est_km:
            raise CabboException(
                "Could not estimate distance between origin and destination",
                status_code=400,
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
            overage_per_km = pricing_schema.overage_per_km
            placard_charge = (
                pricing_schema.placard_charge if search_in.placard_required else 0.0
            )
            base_price = base_fare_per_km * min(est_km, max_included_km)
            overage = max(0, est_km - max_included_km) * overage_per_km
            # Total price includes base fare, toll and parking charges and placard charges (if any)
            # We wont add the overage charge to the total price for airport pickups because overages is an estimation and not a fixed charge
            # Overages will apply if at the end of the trip the actual distance is more than the estimated distance
            # This indicator is to ensure that the customer is aware that overage charges may apply for this route
            total_price_before_platform_fee = math.ceil(
                base_price + toll + parking + placard_charge
            )
            warning_km_threshold = warning_config.warning_km_threshold
            margin = max_included_km - est_km  # Allow negative values for overage
            indicative_overage_warning = margin <= warning_km_threshold
            platform_fee_amount = (
                platform_fee_percent * total_price_before_platform_fee / 100
            )
            price_breakdown = AirportPricingBreakdownSchema(
                base_fare=math.ceil(base_price),
                placard_charge=math.ceil(placard_charge),
                tolls_estimate=math.ceil(toll),
                parking_estimate=math.ceil(parking),
                platform_fee=math.ceil(
                    platform_fee_amount
                ),  # Assuming no platform fee for now
                overage_per_km=overage_per_km,
                overage_estimate=math.ceil(overage),
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
        if not search_in.origin:
            raise CabboException("Origin is required for airport drop", status_code=400)
        if not search_in.destination:
            search_in.destination = APP_AIRPORT_LOCATION.get(APP_HOME_STATE, None)
        if not search_in.destination:
            raise CabboException(
                "Destination is required for airport drop", status_code=400
            )
        est_km = get_distance_km(
            origin=search_in.origin, destination=search_in.destination
        )
        if not est_km:
            raise CabboException(
                "Could not estimate distance between origin and destination",
                status_code=400,
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
            overage_per_km = pricing_schema.overage_per_km
            base_price = base_fare_per_km * min(est_km, max_included_km)
            overage = max(0, est_km - max_included_km) * overage_per_km
            # Total price includes base fare, toll and parking charges (if any)
            # We wont add the overage charge to the total price for airport pickups because overages is an estimation and not a fixed charge
            # Overages will apply if at the end of the trip the actual distance is more than the estimated distance
            # This indicator is to ensure that the customer is aware that overage charges may apply for this route
            total_price_before_platform_fee = math.ceil(base_price + toll + parking)
            warning_km_threshold = warning_config.warning_km_threshold
            margin = max_included_km - est_km  # Allow negative values for overage
            indicative_overage_warning = margin <= warning_km_threshold
            platform_fee_amount = (
                platform_fee_percent * total_price_before_platform_fee / 100
            )
            price_breakdown = AirportPricingBreakdownSchema(
                base_fare=math.ceil(base_price),
                tolls_estimate=math.ceil(toll),
                parking_estimate=math.ceil(parking),
                platform_fee=math.ceil(
                    platform_fee_amount
                ),  # Assuming no platform fee for now
                overage_per_km=overage_per_km,
                overage_estimate=math.ceil(overage),
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

    else:
        # For other trip types, we will implement later
        raise CabboException(
            "Only airport pickup/drop is implemented currently", status_code=501
        )

    # We will do the next trip types later once we finish the airport pickup logic neatly
    # elif search_in.trip_type == airport_drop:
    #     # Destination is airport, origin is required
    #     airport_pricings = db.query(AirportCabPricing).all()
    #     for pricing in airport_pricings:
    #         base_fare_per_km = pricing.airport_fare_per_km
    #         max_included_km = pricing.max_included_km
    #         overage_per_km = pricing.overage_per_km
    #         est_km = 35  # TODO: Replace with real distance calc
    #         base_price = base_fare_per_km * min(est_km, max_included_km)
    #         overage = max(0, est_km - max_included_km) * overage_per_km
    #         total_price = base_price + overage
    #         options.append(
    #             TripSearchOption(
    #                 car_type=pricing.cab_type_id,
    #                 fuel_type=pricing.fuel_type_id,
    #                 price=total_price,
    #                 price_breakdown={"base": base_price, "overage": overage},
    #                 estimated_km=est_km,
    #             )
    #         )
    # elif search_in.trip_type == TripTypeEnum.local:
    #     # Local: duration in hours, pickup required, drop optional
    #     local_pricings = db.query(LocalCabPricing).all()
    #     duration = search_in.duration_hours or 4
    #     for pricing in local_pricings:
    #         hourly_rate = pricing.hourly_rate
    #         min_hours = pricing.min_included_hours
    #         max_hours = pricing.max_included_hours
    #         overage_per_hour = pricing.overage_per_hour
    #         base_hours = min(duration, max_hours)
    #         overage_hours = max(0, duration - max_hours)
    #         base_price = hourly_rate * base_hours
    #         overage = overage_per_hour * overage_hours
    #         total_price = base_price + overage
    #         options.append(
    #             TripSearchOption(
    #                 car_type=pricing.cab_type_id,
    #                 fuel_type=pricing.fuel_type_id,
    #                 price=total_price,
    #                 price_breakdown={"base": base_price, "overage": overage},
    #                 estimated_hours=duration,
    #             )
    #         )
    # elif search_in.trip_type == TripTypeEnum.outstation:
    #     # Outstation: start/end date, pickup required, drop optional
    #     outstation_pricings = db.query(OutstationCabPricing).all()
    #     # Calculate days (end_date - start_date), default 1 if missing
    #     from datetime import datetime, timedelta

    #     start_dt = datetime.fromisoformat(search_in.start_date)
    #     end_dt = (
    #         datetime.fromisoformat(search_in.end_date)
    #         if search_in.end_date
    #         else (start_dt + timedelta(days=1))
    #     )
    #     num_days = (end_dt.date() - start_dt.date()).days or 1
    #     est_km = 300 * num_days  # TODO: Replace with real estimate or user input
    #     for pricing in outstation_pricings:
    #         base_fare_per_km = pricing.base_fare_per_km
    #         min_km_per_day = pricing.min_included_km_per_day
    #         overage_per_km = pricing.overage_per_km
    #         included_km = min_km_per_day * num_days
    #         base_price = base_fare_per_km * min(est_km, included_km)
    #         overage = max(0, est_km - included_km) * overage_per_km
    #         total_price = base_price + overage
    #         options.append(
    #             TripSearchOption(
    #                 car_type=pricing.cab_type_id,
    #                 fuel_type=pricing.fuel_type_id,
    #                 price=total_price,
    #                 price_breakdown={"base": base_price, "overage": overage},
    #                 estimated_km=est_km,
    #             )
    #         )

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
        # 3. Luggage logic
        num_luggages = (
            (search_in.num_large_suitcases or 0)
            + (search_in.num_carryons or 0)
            + (search_in.num_backpacks or 0)
            + (search_in.num_other_bags or 0)
        )
        if num_luggages > 4:
            if option.car_type in [CarTypeEnum.suv, CarTypeEnum.suv_plus]:
                pref_score -= 150
        # 4. Price as a tiebreaker
        return (pref_score, option.total_price)

    _options = sorted(options, key=sort_key)[
        : len(options)
    ]  #  Limit to top 5 options based on user preferences and trip context
    return _options
