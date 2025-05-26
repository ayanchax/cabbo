# Stub for pricing logic service
from typing import List
from models.cab.pricing_schema import AirportPricingBreakdownSchema
from models.trip.trip_schema import TripSearchRequest, TripSearchOption
from sqlalchemy.orm import Session
from models.cab.pricing_orm import (
    CabType,
    FuelType,
    AirportCabPricing,
    LocalCabPricing,
    OutstationCabPricing,
)
from models.trip.trip_enums import CarTypeEnum, TripTypeEnum
from core.exceptions import CabboException
from services.location_service import get_distance_km, get_state_from_location
from models.geography.geo_enums import APP_AIRPORT_LOCATION
from core.constants import APP_HOME_STATE
from models.cab.pricing_orm import OverageWarningConfig, TollParkingConfig
import math


def get_trip_search_options(search_in: TripSearchRequest, db: Session) -> list:
    """
    Returns a list of TripSearchOption based on trip type, cab type, fuel type, and all pricing configs in DB.
    Handles all business rules for date/time, location, and placard charge.
    """

    options: List[TripSearchOption] = []
    is_airport_trip = search_in.trip_type in [
        TripTypeEnum.airport_pickup,
        TripTypeEnum.airport_drop,
    ]
    if is_airport_trip:
        warning_config = (
            db.query(OverageWarningConfig)
            .filter_by(trip_type=TripTypeEnum.airport_general)
            .first()
        )
        toll_parking_charge = (
            db.query(TollParkingConfig)
            .filter_by(trip_type=TripTypeEnum.airport_general)
            .first()
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
                base_fare_per_km = pricing.airport_fare_per_km
                max_included_km = pricing.max_included_km
                overage_per_km = pricing.overage_per_km
                placard_charge = (
                    pricing.placard_charge if search_in.placard_required else 0.0
                )
                base_price = base_fare_per_km * min(est_km, max_included_km)
                overage = max(0, est_km - max_included_km) * overage_per_km
                # Total price includes base fare, toll and parking charges and placard charges (if any)
                # We wont add the overage charge to the total price for airport pickups because overages is an estimation and not a fixed charge
                # Overages will apply if at the end of the trip the actual distance is more than the estimated distance
                # This indicator is to ensure that the customer is aware that overage charges may apply for this route
                total_price = math.ceil(base_price + toll + parking + placard_charge)
                warning_km_threshold = warning_config.warning_km_threshold
                margin = max_included_km - est_km  # Allow negative values for overage
                indicative_overage_warning = margin <= warning_km_threshold
                price_breakdown = AirportPricingBreakdownSchema(
                    base_fare=math.ceil(base_price),
                    platform_fee=math.ceil(0.0),  # Assuming no platform fee for now
                    final_price=math.ceil(total_price),
                    placard_charge=math.ceil(placard_charge),
                    tolls_estimate=math.ceil(toll),
                    parking_estimate=math.ceil(parking),
                    overage_per_km=overage_per_km,
                    overage_estimate=math.ceil(overage),
                )
                options.append(
                    TripSearchOption(
                        car_type=cab_type.name,  # Use display name
                        fuel_type=fuel_type.name,  # Use display name
                        price=total_price,
                        price_breakdown=price_breakdown,
                        estimated_km=est_km,
                        indicative_overage_warning=indicative_overage_warning,
                    )
                )

        elif search_in.trip_type == TripTypeEnum.airport_drop:  # to airport
            if not search_in.origin:
                raise CabboException(
                    "Origin is required for airport drop", status_code=400
                )
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
                base_fare_per_km = pricing.airport_fare_per_km
                max_included_km = pricing.max_included_km
                overage_per_km = pricing.overage_per_km
                base_price = base_fare_per_km * min(est_km, max_included_km)
                overage = max(0, est_km - max_included_km) * overage_per_km
                # Total price includes base fare, toll and parking charges (if any)
                # We wont add the overage charge to the total price for airport pickups because overages is an estimation and not a fixed charge
                # Overages will apply if at the end of the trip the actual distance is more than the estimated distance
                # This indicator is to ensure that the customer is aware that overage charges may apply for this route
                total_price = math.ceil(base_price + toll + parking)
                warning_km_threshold = warning_config.warning_km_threshold
                margin = max_included_km - est_km  # Allow negative values for overage
                indicative_overage_warning = margin <= warning_km_threshold
                price_breakdown = AirportPricingBreakdownSchema(
                    base_fare=math.ceil(base_price),
                    platform_fee=math.ceil(0.0),  # Assuming no platform fee for now
                    final_price=math.ceil(total_price),
                    tolls_estimate=math.ceil(toll),
                    parking_estimate=math.ceil(parking),
                    overage_per_km=overage_per_km,
                    overage_estimate=math.ceil(overage),
                )
                options.append(
                    TripSearchOption(
                        car_type=cab_type.name,  # Use display name
                        fuel_type=fuel_type.name,  # Use display name
                        price=total_price,
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
    # elif search_in.trip_type == TripTypeEnum.airport_drop:
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
        return (pref_score, option.price)

    _options = sorted(options, key=sort_key)[:5]
    return _options
