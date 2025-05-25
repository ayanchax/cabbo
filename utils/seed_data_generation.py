import uuid
from sqlalchemy.orm import Session
from models.cab.pricing_orm import (
    CabType,
    FuelType,
    OutstationCabPricing,
    LocalCabPricing,
    AirportCabPricing,
    TollParkingConfig,
    OverageWarningConfig,
)
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripTypeEnum
from core.security import RoleEnum
from sqlalchemy.sql import func
from models.geography.state_orm import GeoStateModel


def seed_pricing_master(session: Session):
    # Cab Types
    cab_types = [
        CabType(
            id=str(uuid.uuid4()),
            name=CarTypeEnum.hatchback,
            description="Compact hatchbacks, ideal for city rides and short trips. Most available cabs in this segment are CNG.",
            cab_names="WagonR, Celerio, Tiago, Santro, i10, Swift",
            inventory_cab_names="WagonR (CNG)",
            created_by=RoleEnum.system,
        ),
        CabType(
            id=str(uuid.uuid4()),
            name=CarTypeEnum.sedan,
            description="Comfortable sedans, suitable for city and outstation travel.",
            cab_names="Dzire, Amaze, Indigo",
            inventory_cab_names="Dzire",
            created_by=RoleEnum.system,
        ),
        CabType(
            id=str(uuid.uuid4()),
            name=CarTypeEnum.sedan_plus,
            description="Premium sedans for extra comfort and luxury.",
            cab_names="Honda City, Etios, Dzire Plus, Aura, Xcent, Verna, Ciaz, Yaris, Slavia",
            inventory_cab_names="Etios, Dzire Plus, Xcent, Aura",
            created_by=RoleEnum.system,
        ),
        CabType(
            id=str(uuid.uuid4()),
            name=CarTypeEnum.suv,
            description="Spacious SUVs, good for family/group travel and rough roads.",
            cab_names="Ertiga, Innova, Marazzo, XL6, Mobilio",
            inventory_cab_names="Ertiga, Innova",
            created_by=RoleEnum.system,
        ),
        CabType(
            id=str(uuid.uuid4()),
            name=CarTypeEnum.suv_plus,
            description="Premium SUVs with extra comfort and luggage space.",
            cab_names="Innova Crysta, Hexa, Fortuner, XUV500, Alcazar",
            inventory_cab_names="Innova Crysta",
            created_by=RoleEnum.system,
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
    # Example realistic values based on industry standards (approximate, can be admin-edited later)
    # Outstation base fare per km and driver allowance per day by cab type
    outstation_base_fares = {
        CarTypeEnum.hatchback: 11,
        CarTypeEnum.sedan: 12,
        CarTypeEnum.sedan_plus: 14,
        CarTypeEnum.suv: 15,
        CarTypeEnum.suv_plus: 18,
    }
    outstation_driver_allowance = {
        CarTypeEnum.hatchback: 250,
        CarTypeEnum.sedan: 300,
        CarTypeEnum.sedan_plus: 320,
        CarTypeEnum.suv: 350,
        CarTypeEnum.suv_plus: 400,
    }
    # Local hourly rates by cab type
    local_hourly_rates = {
        CarTypeEnum.hatchback: 180,
        CarTypeEnum.sedan: 220,
        CarTypeEnum.sedan_plus: 300,
        CarTypeEnum.suv: 300,
        CarTypeEnum.suv_plus: 400,
    }
    # Airport fare per km by cab type
    airport_fare_per_km = {
        CarTypeEnum.hatchback: 16,
        CarTypeEnum.sedan: 18,
        CarTypeEnum.sedan_plus: 20,
        CarTypeEnum.suv: 22,
        CarTypeEnum.suv_plus: 25,
    }
    # Outstation overage config by cab type
    outstation_min_km_per_day = {
        CarTypeEnum.hatchback: 200,
        CarTypeEnum.sedan: 300,
        CarTypeEnum.sedan_plus: 300,
        CarTypeEnum.suv: 300,
        CarTypeEnum.suv_plus: 300,
    }
    outstation_overage_per_km = {
        CarTypeEnum.hatchback: 10,
        CarTypeEnum.sedan: 11,
        CarTypeEnum.sedan_plus: 13,
        CarTypeEnum.suv: 13,
        CarTypeEnum.suv_plus: 16,
    }
    outstation_night_overage_per_block = {
        CarTypeEnum.hatchback: 100,
        CarTypeEnum.sedan: 100,
        CarTypeEnum.sedan_plus: 100,
        CarTypeEnum.suv: 100,
        CarTypeEnum.suv_plus: 100,
    }
    outstation_night_block_hours = 3

    # Local overage config by cab type
    local_min_hours = 4
    local_max_hours = 12
    local_overage_per_hour = {
        CarTypeEnum.hatchback: 180,
        CarTypeEnum.sedan: 220,
        CarTypeEnum.sedan_plus: 300,
        CarTypeEnum.suv: 300,
        CarTypeEnum.suv_plus: 400,
    }

    # Airport overage config by cab type
    airport_max_included_km = 42
    airport_overage_per_km = {
        CarTypeEnum.hatchback: 14,
        CarTypeEnum.sedan: 16,
        CarTypeEnum.sedan_plus: 18,
        CarTypeEnum.suv: 19,
        CarTypeEnum.suv_plus: 22,
    }

    for cab in cab_types:
        for fuel in fuel_types:
            # No fuel type restriction logic, allow all combinations
            # Outstation
            outstation_pricing.append(
                OutstationCabPricing(
                    id=str(uuid.uuid4()),
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    base_fare_per_km=outstation_base_fares[cab.name],
                    driver_allowance_per_day=outstation_driver_allowance[cab.name],
                    min_included_km_per_day=outstation_min_km_per_day[cab.name],
                    overage_per_km=outstation_overage_per_km[cab.name],
                    night_overage_per_block=outstation_night_overage_per_block[
                        cab.name
                    ],
                    night_block_hours=outstation_night_block_hours,
                    created_by=RoleEnum.system,
                )
            )
            # Local
            local_pricing.append(
                LocalCabPricing(
                    id=str(uuid.uuid4()),
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    hourly_rate=local_hourly_rates[cab.name],
                    min_included_hours=local_min_hours,
                    max_included_hours=local_max_hours,
                    overage_per_hour=local_overage_per_hour[cab.name],
                    created_by=RoleEnum.system,
                )
            )
            # Airport
            airport_pricing.append(
                AirportCabPricing(
                    id=str(uuid.uuid4()),
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    airport_fare_per_km=airport_fare_per_km[cab.name],
                    max_included_km=airport_max_included_km,
                    overage_per_km=airport_overage_per_km[cab.name],
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
    # Overage warning config seed
    overage_warning_configs = [
        OverageWarningConfig(
            id=str(uuid.uuid4()),
            trip_type=TripTypeEnum.airport_general,
            warning_factor=2,
            created_by=RoleEnum.system,
        ),
        OverageWarningConfig(
            id=str(uuid.uuid4()),
            trip_type=TripTypeEnum.outstation,
            warning_factor=50,
            created_by=RoleEnum.system,
        ),
        OverageWarningConfig(
            id=str(uuid.uuid4()),
            trip_type=TripTypeEnum.local,
            warning_factor=0,
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
        + overage_warning_configs
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
