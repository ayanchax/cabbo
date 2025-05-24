import uuid
from sqlalchemy.orm import Session
from models.cab.pricing_orm import (
    CabType,
    FuelType,
    OutstationCabPricing,
    LocalCabPricing,
    AirportCabPricing,
    TollParkingConfig,
)
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripTypeEnum
from core.security import RoleEnum
from sqlalchemy.sql import func
from models.geography.state_orm import GeoStateModel


def seed_pricing_master(session: Session):
    # Cab Types
    cab_types = [
        CabType(
            id=str(uuid.uuid4()), name=CarTypeEnum.hatchback, created_by=RoleEnum.system
        ),
        CabType(
            id=str(uuid.uuid4()), name=CarTypeEnum.sedan, created_by=RoleEnum.system
        ),
        CabType(id=str(uuid.uuid4()), name=CarTypeEnum.suv, created_by=RoleEnum.system),
        CabType(
            id=str(uuid.uuid4()), name=CarTypeEnum.suv_plus, created_by=RoleEnum.system
        ),
    ]
    # Fuel Types
    fuel_types = [
        FuelType(
            id=str(uuid.uuid4()), name=FuelTypeEnum.petrol, created_by=RoleEnum.system
        ),
        FuelType(
            id=str(uuid.uuid4()), name=FuelTypeEnum.diesel, created_by=RoleEnum.system
        ),
        FuelType(
            id=str(uuid.uuid4()), name=FuelTypeEnum.cng, created_by=RoleEnum.system
        ),
    ]
    # Pricing (example values, adjust as needed)
    outstation_pricing = []
    local_pricing = []
    airport_pricing = []
    for cab in cab_types:
        for fuel in fuel_types:
            # Outstation
            outstation_pricing.append(
                OutstationCabPricing(
                    id=str(uuid.uuid4()),
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    base_fare_per_km=10 + 2 * list(cab_types).index(cab),
                    driver_allowance_per_day=250 + 50 * list(cab_types).index(cab),
                    created_by=RoleEnum.system,
                )
            )
            # Local
            local_pricing.append(
                LocalCabPricing(
                    id=str(uuid.uuid4()),
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    hourly_rate=120 + 20 * list(cab_types).index(cab),
                    created_by=RoleEnum.system,
                )
            )
            # Airport
            airport_pricing.append(
                AirportCabPricing(
                    id=str(uuid.uuid4()),
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    airport_fare_per_km=15 + 3 * list(cab_types).index(cab),
                    created_by=RoleEnum.system,
                )
            )
    # Toll/Parking Config
    toll_configs = [
        TollParkingConfig(
            id=str(uuid.uuid4()),
            trip_type=TripTypeEnum.local,
            toll=80,
            parking=60,
            created_by=RoleEnum.system,
        ),
        TollParkingConfig(
            id=str(uuid.uuid4()),
            trip_type=TripTypeEnum.airport_general,
            toll=120,
            parking=100,
            created_by=RoleEnum.system,
        ),
        TollParkingConfig(
            id=str(uuid.uuid4()),
            trip_type=TripTypeEnum.outstation,
            toll_per_block=500,
            parking_per_block=150,
            block_days=3,
            created_by=RoleEnum.system,
        ),
    ]
    # Add and commit cab_types and fuel_types first to satisfy FK constraints
    session.add_all(cab_types + fuel_types)
    session.commit()

    # Now add and commit pricing and toll configs
    session.add_all(
        outstation_pricing
        + local_pricing
        + airport_pricing
        + toll_configs
    )
    session.commit()


def seed_states(session: Session):
    states = [
        GeoStateModel(
            state_name="Karnataka", state_code="KA", permit_fee=0.0, is_home_state=1
        ),
        GeoStateModel(
            state_name="Tamil Nadu", state_code="TN", permit_fee=700.0, is_home_state=0
        ),
    ]
    session.add_all(states)
    session.commit()
