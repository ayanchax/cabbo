from typing import List
import uuid
from sqlalchemy.orm import Session
from models.cab.pricing_orm import (
    CabType,
    CommonPricingConfiguration,
    FixedPlatformPricing,
    FuelType,
    OutstationCabPricing,
    LocalCabPricing,
    AirportCabPricing,
    FixedNightPricing,
    FixedPlatformPricing,
)
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripTypeEnum
from core.security import RoleEnum
from core.constants import APP_HOME_STATE, APP_HOME_STATE_CODE
from models.geography.state_orm import GeoStateModel
from models.trip.trip_orm import TripPackageConfig
from models.trip.trip_schema import TripPackageConfigSchema
from models.cab.pricing_orm import PermitFeeConfiguration


def seed_pricing_master(session: Session):
    # Cab Types
    cab_types = [
        CabType(
            id=str(uuid.uuid4()),
            name=CarTypeEnum.hatchback,
            description="Compact hatchbacks, ideal for city rides and short trips. Most available cabs in this segment are CNG.",
            cab_names="WagonR, Celerio, Tiago, Santro, i10, Swift",
            inventory_cab_names="WagonR",
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
    # Outstation base fare per km and driver allowance per day by cab type and fuel type
    outstation_base_fares = {
        CarTypeEnum.hatchback: {
            FuelTypeEnum.petrol: 11,
            FuelTypeEnum.diesel: 10,
            FuelTypeEnum.cng: 9,
        },
        CarTypeEnum.sedan: {
            FuelTypeEnum.petrol: 13,
            FuelTypeEnum.diesel: 12,
            FuelTypeEnum.cng: 11,
        },
        CarTypeEnum.sedan_plus: {
            FuelTypeEnum.petrol: 15,
            FuelTypeEnum.diesel: 14,
            FuelTypeEnum.cng: 13,
        },
        CarTypeEnum.suv: {
            FuelTypeEnum.petrol: 18,
            FuelTypeEnum.diesel: 17,
            FuelTypeEnum.cng: 16,
        },
        CarTypeEnum.suv_plus: {
            FuelTypeEnum.petrol: 22,
            FuelTypeEnum.diesel: 20,
            FuelTypeEnum.cng: 18,
        },
    }
    outstation_driver_allowance = {
        CarTypeEnum.hatchback: {
            FuelTypeEnum.petrol: 400,
            FuelTypeEnum.diesel: 400,
            FuelTypeEnum.cng: 400,
        },
        CarTypeEnum.sedan: {
            FuelTypeEnum.petrol: 400,
            FuelTypeEnum.diesel: 400,
            FuelTypeEnum.cng: 400,
        },
        CarTypeEnum.sedan_plus: {
            FuelTypeEnum.petrol: 400,
            FuelTypeEnum.diesel: 400,
            FuelTypeEnum.cng: 400,
        },
        CarTypeEnum.suv: {
            FuelTypeEnum.petrol: 400,
            FuelTypeEnum.diesel: 400,
            FuelTypeEnum.cng: 400,
        },
        CarTypeEnum.suv_plus: {
            FuelTypeEnum.petrol: 400,
            FuelTypeEnum.diesel: 400,
            FuelTypeEnum.cng: 400,
        },
    }
    # Local hourly rates by cab type and fuel type
    local_hourly_rates = {
        CarTypeEnum.hatchback: {
            FuelTypeEnum.petrol: 250,
            FuelTypeEnum.diesel: 250,
            FuelTypeEnum.cng: 250,
        },
        CarTypeEnum.sedan: {
            FuelTypeEnum.petrol: 300,
            FuelTypeEnum.diesel: 280,
            FuelTypeEnum.cng: 270,
        },
        CarTypeEnum.sedan_plus: {
            FuelTypeEnum.petrol: 350,
            FuelTypeEnum.diesel: 340,
            FuelTypeEnum.cng: 330,
        },
        CarTypeEnum.suv: {
            FuelTypeEnum.petrol: 400,
            FuelTypeEnum.diesel: 380,
            FuelTypeEnum.cng: 360,
        },
        CarTypeEnum.suv_plus: {
            FuelTypeEnum.petrol: 450,
            FuelTypeEnum.diesel: 420,
            FuelTypeEnum.cng: 400,
        },
    }
    # Airport fare per km by cab type and fuel type
    airport_fare_per_km = {
        CarTypeEnum.hatchback: {
            FuelTypeEnum.petrol: 20,
            FuelTypeEnum.diesel: 19,
            FuelTypeEnum.cng: 18,
        },
        CarTypeEnum.sedan: {
            FuelTypeEnum.petrol: 25,
            FuelTypeEnum.diesel: 24,
            FuelTypeEnum.cng: 23,
        },
        CarTypeEnum.sedan_plus: {
            FuelTypeEnum.petrol: 26,
            FuelTypeEnum.diesel: 25,
            FuelTypeEnum.cng: 24,
        },
        CarTypeEnum.suv: {
            FuelTypeEnum.petrol: 39,
            FuelTypeEnum.diesel: 38,
            FuelTypeEnum.cng: 37,
        },
        CarTypeEnum.suv_plus: {
            FuelTypeEnum.petrol: 46,
            FuelTypeEnum.diesel: 45,
            FuelTypeEnum.cng: 40,
        },
    }
    # Outstation overage config by cab type and fuel type
    outstation_min_km_per_day = {
        CarTypeEnum.hatchback: 300,
        CarTypeEnum.sedan: 300,
        CarTypeEnum.sedan_plus: 300,
        CarTypeEnum.suv: 300,
        CarTypeEnum.suv_plus: 300,
    }
    outstation_overage_per_km = {
        CarTypeEnum.hatchback: {
            FuelTypeEnum.petrol: 10,
            FuelTypeEnum.diesel: 9,
            FuelTypeEnum.cng: 8,
        },
        CarTypeEnum.sedan: {
            FuelTypeEnum.petrol: 13,
            FuelTypeEnum.diesel: 12,
            FuelTypeEnum.cng: 11,
        },
        CarTypeEnum.sedan_plus: {
            FuelTypeEnum.petrol: 14,
            FuelTypeEnum.diesel: 13,
            FuelTypeEnum.cng: 12,
        },
        CarTypeEnum.suv: {
            FuelTypeEnum.petrol: 22,
            FuelTypeEnum.diesel: 20,
            FuelTypeEnum.cng: 18,
        },
        CarTypeEnum.suv_plus: {
            FuelTypeEnum.petrol: 22,
            FuelTypeEnum.diesel: 20,
            FuelTypeEnum.cng: 17,
        },
    }

    # Local overage config by cab type and fuel type
    local_overage_per_hour = {
        CarTypeEnum.hatchback: {
            FuelTypeEnum.petrol: 250,
            FuelTypeEnum.diesel: 250,
            FuelTypeEnum.cng: 250,
        },
        CarTypeEnum.sedan: {
            FuelTypeEnum.petrol: 300,
            FuelTypeEnum.diesel: 280,
            FuelTypeEnum.cng: 280,
        },
        CarTypeEnum.sedan_plus: {
            FuelTypeEnum.petrol: 350,
            FuelTypeEnum.diesel: 340,
            FuelTypeEnum.cng: 330,
        },
        CarTypeEnum.suv: {
            FuelTypeEnum.petrol: 400,
            FuelTypeEnum.diesel: 380,
            FuelTypeEnum.cng: 360,
        },
        CarTypeEnum.suv_plus: {
            FuelTypeEnum.petrol: 450,
            FuelTypeEnum.diesel: 420,
            FuelTypeEnum.cng: 400,
        },
    }

    local_overage_per_km = {
        CarTypeEnum.hatchback: {
            FuelTypeEnum.petrol: 15,
            FuelTypeEnum.diesel: 15,
            FuelTypeEnum.cng: 15,
        },
        CarTypeEnum.sedan: {
            FuelTypeEnum.petrol: 16,
            FuelTypeEnum.diesel: 15,
            FuelTypeEnum.cng: 14,
        },
        CarTypeEnum.sedan_plus: {
            FuelTypeEnum.petrol: 18,
            FuelTypeEnum.diesel: 17,
            FuelTypeEnum.cng: 16,
        },
        CarTypeEnum.suv: {
            FuelTypeEnum.petrol: 20,
            FuelTypeEnum.diesel: 19,
            FuelTypeEnum.cng: 18,
        },
        CarTypeEnum.suv_plus: {
            FuelTypeEnum.petrol: 22,
            FuelTypeEnum.diesel: 21,
            FuelTypeEnum.cng: 20,
        },
    }

    # Airport overage config by cab type and fuel type
    airport_overage_per_km = {
        CarTypeEnum.hatchback: {
            FuelTypeEnum.petrol: 18,
            FuelTypeEnum.diesel: 17,
            FuelTypeEnum.cng: 17,
        },
        CarTypeEnum.sedan: {
            FuelTypeEnum.petrol: 20,
            FuelTypeEnum.diesel: 19,
            FuelTypeEnum.cng: 18,
        },
        CarTypeEnum.sedan_plus: {
            FuelTypeEnum.petrol: 21,
            FuelTypeEnum.diesel: 20,
            FuelTypeEnum.cng: 19,
        },
        CarTypeEnum.suv: {
            FuelTypeEnum.petrol: 38,
            FuelTypeEnum.diesel: 37,
            FuelTypeEnum.cng: 36,
        },
        CarTypeEnum.suv_plus: {
            FuelTypeEnum.petrol: 43,
            FuelTypeEnum.diesel: 42,
            FuelTypeEnum.cng: 38,
        },
    }

    for cab in cab_types:
        for fuel in fuel_types:
            # Outstation
            outstation_pricing.append(
                OutstationCabPricing(
                    id=str(uuid.uuid4()),
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    base_fare_per_km=outstation_base_fares[cab.name][fuel.name],
                    driver_allowance_per_day=outstation_driver_allowance[cab.name][
                        fuel.name
                    ],
                    min_included_km_per_day=outstation_min_km_per_day[cab.name],
                    overage_amount_per_km=outstation_overage_per_km[cab.name][
                        fuel.name
                    ],
                    created_by=RoleEnum.system,
                )
            )
            # Local
            local_pricing.append(
                LocalCabPricing(
                    id=str(uuid.uuid4()),
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    hourly_rate=local_hourly_rates[cab.name][fuel.name],
                    overage_amount_per_hour=local_overage_per_hour[cab.name][fuel.name],
                    overage_amount_per_km=local_overage_per_km[cab.name][fuel.name],
                    created_by=RoleEnum.system,
                )
            )
            # Airport
            airport_pricing.append(
                AirportCabPricing(
                    id=str(uuid.uuid4()),
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    airport_fare_per_km=airport_fare_per_km[cab.name][fuel.name],
                    overage_amount_per_km=airport_overage_per_km[cab.name][fuel.name],
                    created_by=RoleEnum.system,
                )
            )

    # Add and commit cab_types and fuel_types first to satisfy FK constraints
    session.add_all(cab_types + fuel_types)
    session.commit()

    # Trip Type Master seed (exclude airport_general, which is backend-only)
    from models.trip.trip_orm import TripTypeMaster

    trip_type_master = [
        {
            "trip_type": TripTypeEnum.local,
            "display_name": "Local City Ride",
            "description": "Hourly rental for city travel. Flexible for errands, meetings, and sightseeing within city limits.",
        },
        {
            "trip_type": TripTypeEnum.outstation,
            "display_name": "Outstation Trip",
            "description": "Multi-day intercity travel. Ideal for business, leisure, or family trips outside your city.",
        },
        {
            "trip_type": TripTypeEnum.airport_pickup,
            "display_name": "Airport Pickup",
            "description": "Pickup from airport to your destination. Includes flight tracking and driver meet & greet.",
        },
        {
            "trip_type": TripTypeEnum.airport_drop,
            "display_name": "Airport Drop",
            "description": "Drop to airport from your location. Timely service for stress-free departures.",
        },
    ]
    trip_type_master_objs = [
        TripTypeMaster(
            id=str(uuid.uuid4()),
            trip_type=entry["trip_type"],
            display_name=entry["display_name"],
            description=entry["description"],
            created_by=RoleEnum.system,
        )
        for entry in trip_type_master
    ]
    session.add_all(trip_type_master_objs)
    session.commit()

    # Now query TripTypeMaster for trip_type_id mapping
    trip_type_master_objs = session.query(TripTypeMaster).all()
    trip_type_id_map = {obj.trip_type: obj.id for obj in trip_type_master_objs}
    common_pricing_configs = [
        CommonPricingConfiguration(
            id=str(uuid.uuid4()),
            trip_type_id=trip_type_id_map[TripTypeEnum.airport_pickup],
            dynamic_platform_fee_percent=0.5,  # platform fee
            placard_charge=50.0,  # Fixed charge for airport pickup if customer opts for it
            max_included_km=42,  # 42 km included for airport trips is a common standard
            overage_warning_km_threshold=2,  # Warning threshold for overages
            toll=120,  # toll for airport pickup set to 120 if customer opts for it
            parking=100,  # parking charge for airport pickup
            created_by=RoleEnum.system,
        ),
        CommonPricingConfiguration(
            id=str(uuid.uuid4()),
            trip_type_id=trip_type_id_map[TripTypeEnum.airport_drop],
            dynamic_platform_fee_percent=1.0,  # platform fee
            max_included_km=42,  # 42 km included for airport trips is a standard
            overage_warning_km_threshold=2,  # Warning threshold for overages
            toll=120,  # toll for airport drop set to 120 if customer opts for it
            parking=0,  # no parking charge for airport drop
            created_by=RoleEnum.system,
        ),
        CommonPricingConfiguration(
            id=str(uuid.uuid4()),
            trip_type_id=trip_type_id_map[TripTypeEnum.local],
            dynamic_platform_fee_percent=1.5,  # platform fee
            min_included_hours=4,  # Minimum 4 hours for local trips
            max_included_hours=12,  # Maximum 12 hours for local trips
            min_included_km=40,  # Minimum 40 km included for local trips
            max_included_km=120,  # Maximum 120 km included for local trips
            minimum_parking_wallet=80,  #  minimum parking 80 for local trips
            created_by=RoleEnum.system,
        ),
        CommonPricingConfiguration(
            id=str(uuid.uuid4()),
            trip_type_id=trip_type_id_map[TripTypeEnum.outstation],
            dynamic_platform_fee_percent=6.0,  # 6% platform fee
            overage_warning_km_threshold=50,  # Warning threshold for overages
            minimum_toll_wallet=500,  # minimum toll 500 for outstation trips
            minimum_parking_wallet=150,  # minimum parking 150 for outstation trips
            created_by=RoleEnum.system,
        ),
    ]
    # Maintain a collection for duration and included km for local packages

    hourly_rental_packages = [
        TripPackageConfigSchema(
            included_hours=4,
            included_km=40,
            package_label="4Hours / 40KM",
        ),
        TripPackageConfigSchema(
            included_hours=6,
            included_km=60,
            package_label="6Hours / 60KM",
        ),
        TripPackageConfigSchema(
            included_hours=8,
            included_km=80,
            package_label="8Hours / 80KM",
        ),
        TripPackageConfigSchema(
            included_hours=10,
            included_km=100,
            package_label="10Hours / 100KM",
        ),
        TripPackageConfigSchema(
            included_hours=12,
            included_km=120,
            package_label="12Hours / 120KM",
            driver_allowance=400.0,  # Driver allowance for 12 hours
        ),
    ]
    trip_wise_packages: List[TripPackageConfigSchema] = []
    trip_wise_packages.extend(hourly_rental_packages)
    trip_package_configs = []
    for package in trip_wise_packages:
        trip_package_configs.append(
            TripPackageConfig(
                id=str(uuid.uuid4()),
                trip_type_id=trip_type_id_map[TripTypeEnum.local],
                included_hours=package.included_hours,
                included_km=package.included_km,
                package_label=package.package_label,
                driver_allowance=package.driver_allowance
                or 0.0,  # Default to 0 if not set
                created_by=RoleEnum.system,
            )
        )

    # Fixed platform fee for all trips
    fixed_platform_fee_config = FixedPlatformPricing(
        id=str(uuid.uuid4()), fixed_platform_fee=3.0
    )

    # Night charge config seed
    night_charge_config = FixedNightPricing(
        id=str(uuid.uuid4()),
        night_start_hour=20,  # 8PM
        night_end_hour=6,  # 6AM
        created_by=RoleEnum.system,
    )

    # Here create a permit fee config per state_id per cab_type_id by iterating over cab_types and states
    weekly_permit_fees_mapping_by_state_and_cab = {
        "TN": {
            CarTypeEnum.hatchback: {
                FuelTypeEnum.petrol: 500,
                FuelTypeEnum.diesel: 500,
                FuelTypeEnum.cng: 500,
            },
            CarTypeEnum.sedan: {
                FuelTypeEnum.petrol: 500,
                FuelTypeEnum.diesel: 500,
                FuelTypeEnum.cng: 500,
            },
            CarTypeEnum.sedan_plus: {
                FuelTypeEnum.petrol: 570,
                FuelTypeEnum.diesel: 570,
                FuelTypeEnum.cng: 570,
            },
            CarTypeEnum.suv: {
                FuelTypeEnum.petrol: 800,
                FuelTypeEnum.diesel: 800,
                FuelTypeEnum.cng: 800,
            },
            CarTypeEnum.suv_plus: {
                FuelTypeEnum.petrol: 1200,
                FuelTypeEnum.diesel: 1200,
                FuelTypeEnum.cng: 1200,
            },
        },
        "KL": {
            CarTypeEnum.hatchback: {
                FuelTypeEnum.petrol: 500,
                FuelTypeEnum.diesel: 500,
                FuelTypeEnum.cng: 500,
            },
            CarTypeEnum.sedan: {
                FuelTypeEnum.petrol: 800,
                FuelTypeEnum.diesel: 800,
                FuelTypeEnum.cng: 800,
            },
            CarTypeEnum.sedan_plus: {
                FuelTypeEnum.petrol: 800,
                FuelTypeEnum.diesel: 800,
                FuelTypeEnum.cng: 800,
            },
            CarTypeEnum.suv: {
                FuelTypeEnum.petrol: 2700,
                FuelTypeEnum.diesel: 2700,
                FuelTypeEnum.cng: 2700,
            },
            CarTypeEnum.suv_plus: {
                FuelTypeEnum.petrol: 2700,
                FuelTypeEnum.diesel: 2700,
                FuelTypeEnum.cng: 2700,
            },
        },
        "AP": {
            CarTypeEnum.hatchback: {
                FuelTypeEnum.petrol: 500,
                FuelTypeEnum.diesel: 500,
                FuelTypeEnum.cng: 500,
            },
            CarTypeEnum.sedan: {
                FuelTypeEnum.petrol: 800,
                FuelTypeEnum.diesel: 800,
                FuelTypeEnum.cng: 800,
            },
            CarTypeEnum.sedan_plus: {
                FuelTypeEnum.petrol: 800,
                FuelTypeEnum.diesel: 800,
                FuelTypeEnum.cng: 800,
            },
            CarTypeEnum.suv: {
                FuelTypeEnum.petrol: 2200,
                FuelTypeEnum.diesel: 2200,
                FuelTypeEnum.cng: 2200,
            },
            CarTypeEnum.suv_plus: {
                FuelTypeEnum.petrol: 2200,
                FuelTypeEnum.diesel: 2200,
                FuelTypeEnum.cng: 2200,
            },
        },
        # Add more states as needed
    }
    states = session.query(GeoStateModel).filter(GeoStateModel.is_home_state != 1).all()
    permit_fee_configs = []
    for state in states:
        state_code = getattr(state, "state_code", None)
        state_mapping = weekly_permit_fees_mapping_by_state_and_cab.get(state_code)
        if not state_mapping:
            continue  # Skip states not in mapping
        for cab in cab_types:
            cab_mapping = state_mapping.get(cab.name)
            if not cab_mapping:
                continue  # Skip cab types not in mapping
            for fuel in fuel_types:
                permit_fee = cab_mapping.get(fuel.name)
                if permit_fee is None:
                    continue  # Skip if no permit fee defined
                try:
                    permit_fee_configs.append(
                        PermitFeeConfiguration(
                            id=str(uuid.uuid4()),
                            state_id=state.id,
                            cab_type_id=cab.id,
                            fuel_type_id=fuel.id,
                            permit_fee=permit_fee,
                            created_by=RoleEnum.system,
                        )
                    )
                except Exception:
                    # Silently skip any errors in config creation
                    continue

    # Now add and commit pricing and toll configs
    session.add_all(
        outstation_pricing
        + local_pricing
        + airport_pricing
        + [night_charge_config]
        + common_pricing_configs
        + trip_package_configs
        + [fixed_platform_fee_config]
        + permit_fee_configs
    )
    session.commit()


def seed_states(session: Session):
    states = [
        GeoStateModel(
            state_name=APP_HOME_STATE,
            state_code=APP_HOME_STATE_CODE,
            is_home_state=1,
        ),
        GeoStateModel(
            state_name="Tamil Nadu",
            state_code="TN",
            is_home_state=0,
        ),
        GeoStateModel(
            state_name="Kerala",
            state_code="KL",
            is_home_state=0,
        ),
        GeoStateModel(
            state_name="Andhra Pradesh",
            state_code="AP",
            is_home_state=0,
        ),
    ]
    session.add_all(states)
    session.commit()
