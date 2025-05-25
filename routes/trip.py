from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from models.trip.trip_schema import TripCreate, TripOut
from models.trip.trip_orm import Trip, TripStatusAudit, CreatorTypeEnum
from services.pricing_service import calculate_price
from models.trip.trip_enums import TripStatusEnum
import json

router = APIRouter(prefix="/trip", tags=["Trip"])

# Placeholder for geocoding API to detect state
# In production, replace with Google Maps API call


def get_state_from_location(location):
    # Dummy: returns 'Karnataka' for all locations
    # In production, use Google Maps Geocoding API to extract state
    return location.get("state", "Karnataka")


@router.post("/create", response_model=TripOut)
def create_trip(trip_in: TripCreate, db: Session = Depends(get_db)):
    # 1. Dynamic field handling (hops, airport info, etc.)
    # Build the full route: origin -> hops (if any) -> destination
    route_points = [trip_in.origin]
    if trip_in.hops:
        route_points.extend(trip_in.hops)
    route_points.append(trip_in.destination)

    # Extract state for each point (simulate with dummy for now)
    states = []
    for point in route_points:
        # If point is a dict with display_name, lat, lng, etc.
        # For hops, if only display_name is given, wrap as dict
        if isinstance(point, str):
            point = {"display_name": point}
        state = get_state_from_location(point)
        states.append(state)

    # Determine interstate and multi-state hops
    unique_states = set(states)
    is_interstate = (
        len(unique_states) > 1
    )  # Indicates crossing state borders, if more than one state
    multi_state_hops = 0
    for i in range(1, len(states)):
        if states[i] != states[i - 1]:
            multi_state_hops += 1
    # Permit fee logic: charge per state border crossed
    permit_fee = 0
    PER_STATE_PERMIT_FEE = 700  # Example, can be config-driven
    if multi_state_hops > 0:
        permit_fee = multi_state_hops * PER_STATE_PERMIT_FEE

    # 2. Pricing logic
    price_components = calculate_price(
        origin=trip_in.origin,
        destination=trip_in.destination,
        start_date=trip_in.start_date,
        end_date=trip_in.end_date,
        car_type=trip_in.preferred_car_type,
        fuel_type=trip_in.preferred_fuel_type,
        hops=trip_in.hops,
        is_interstate=is_interstate,
        is_round_trip=trip_in.is_round_trip,
        num_adults=trip_in.num_adults,
        num_children=trip_in.num_children,
        num_luggages=trip_in.num_luggages,
        permit_fee=permit_fee,
    )
    indicative_overage_warning = False
    # 3. Create Trip ORM object
    trip = Trip(
        creator_id=1,  # TODO: Replace with actual user from auth
        creator_type=CreatorTypeEnum.customer,
        trip_type=trip_in.trip_type,
        origin_display_name=trip_in.origin.display_name,
        origin_lat=trip_in.origin.lat,
        origin_lng=trip_in.origin.lng,
        origin_place_id=trip_in.origin.place_id,
        origin_address=trip_in.origin.address,
        destination_display_name=trip_in.destination.display_name,
        destination_lat=trip_in.destination.lat,
        destination_lng=trip_in.destination.lng,
        destination_place_id=trip_in.destination.place_id,
        destination_address=trip_in.destination.address,
        hops=json.dumps(trip_in.hops) if trip_in.hops else None,
        is_interstate=is_interstate,
        permit_fee=permit_fee,
        is_round_trip=trip_in.is_round_trip,
        start_date=trip_in.start_date,
        end_date=trip_in.end_date,
        num_adults=trip_in.num_adults,
        num_children=trip_in.num_children,
        num_luggages=trip_in.num_luggages,
        num_large_suitcases=trip_in.num_large_suitcases,
        num_carryons=trip_in.num_carryons,
        num_backpacks=trip_in.num_backpacks,
        num_other_bags=trip_in.num_other_bags,
        preferred_car_type=trip_in.preferred_car_type,
        preferred_fuel_type=trip_in.preferred_fuel_type,
        driver_name=trip_in.driver_name,
        driver_phone=trip_in.driver_phone,
        car_model=trip_in.car_model,
        car_registration_number=trip_in.car_registration_number,
        payment_mode=trip_in.payment_mode,
        payment_number=trip_in.payment_number,
        flight_number=trip_in.flight_number,
        terminal_number=trip_in.terminal_number,
        status=TripStatusEnum.created,
        base_fare=price_components.get("base_fare"),
        driver_allowance=price_components.get("allowance"),
        tolls_estimate=price_components.get("tolls_estimate"),
        parking_estimate=price_components.get("parking_estimate"),
        platform_fee=price_components.get("platform_fee"),
        quoted_price=None,
        final_price=price_components.get("total_price"),
        final_display_price=price_components.get("total_price"),
        indicative_overage_warning=indicative_overage_warning,
    )
    db.add(trip)
    db.flush()  # To get trip.id
    # 4. Create audit trail
    audit = TripStatusAudit(
        trip_id=trip.id,
        status=TripStatusEnum.created,
        changed_by="customer",
        reason="Trip created",
    )
    db.add(audit)
    db.commit()
    db.refresh(trip)
    return trip
