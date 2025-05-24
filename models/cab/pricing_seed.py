# Seed data for cab types, fuel types, cab pricing, and toll/parking config
from models.cab.pricing_orm import (
    CabType,
    FuelType,
    CabPricingMaster,
    TollParkingConfig,
)


def get_seed_data():
    cab_types = [
        CabType(id=1, name="Hatchback"),
        CabType(id=2, name="Sedan"),
        CabType(id=3, name="SUV"),
        CabType(id=4, name="SUV+"),
    ]
    fuel_types = [
        FuelType(id=1, name="petrol"),
        FuelType(id=2, name="diesel"),
        FuelType(id=3, name="cng"),
    ]
    cab_pricing = [
        # Hatchback
        CabPricingMaster(
            cab_type_id=1,
            fuel_type_id=1,
            base_fare_per_km=10,
            hourly_rate=120,
            driver_allowance_per_day=250,
            airport_fare_per_km=15,
        ),
        CabPricingMaster(
            cab_type_id=1,
            fuel_type_id=2,
            base_fare_per_km=9,
            hourly_rate=110,
            driver_allowance_per_day=240,
            airport_fare_per_km=14,
        ),
        CabPricingMaster(
            cab_type_id=1,
            fuel_type_id=3,
            base_fare_per_km=8,
            hourly_rate=100,
            driver_allowance_per_day=230,
            airport_fare_per_km=13,
        ),
        # Sedan
        CabPricingMaster(
            cab_type_id=2,
            fuel_type_id=1,
            base_fare_per_km=12,
            hourly_rate=150,
            driver_allowance_per_day=300,
            airport_fare_per_km=18,
        ),
        CabPricingMaster(
            cab_type_id=2,
            fuel_type_id=2,
            base_fare_per_km=11,
            hourly_rate=140,
            driver_allowance_per_day=290,
            airport_fare_per_km=17,
        ),
        CabPricingMaster(
            cab_type_id=2,
            fuel_type_id=3,
            base_fare_per_km=10,
            hourly_rate=130,
            driver_allowance_per_day=280,
            airport_fare_per_km=16,
        ),
        # SUV
        CabPricingMaster(
            cab_type_id=3,
            fuel_type_id=1,
            base_fare_per_km=15,
            hourly_rate=200,
            driver_allowance_per_day=400,
            airport_fare_per_km=22,
        ),
        CabPricingMaster(
            cab_type_id=3,
            fuel_type_id=2,
            base_fare_per_km=14,
            hourly_rate=190,
            driver_allowance_per_day=390,
            airport_fare_per_km=21,
        ),
        CabPricingMaster(
            cab_type_id=3,
            fuel_type_id=3,
            base_fare_per_km=13,
            hourly_rate=180,
            driver_allowance_per_day=380,
            airport_fare_per_km=20,
        ),
        # SUV+
        CabPricingMaster(
            cab_type_id=4,
            fuel_type_id=1,
            base_fare_per_km=18,
            hourly_rate=250,
            driver_allowance_per_day=500,
            airport_fare_per_km=28,
        ),
        CabPricingMaster(
            cab_type_id=4,
            fuel_type_id=2,
            base_fare_per_km=17,
            hourly_rate=240,
            driver_allowance_per_day=490,
            airport_fare_per_km=27,
        ),
        CabPricingMaster(
            cab_type_id=4,
            fuel_type_id=3,
            base_fare_per_km=16,
            hourly_rate=230,
            driver_allowance_per_day=480,
            airport_fare_per_km=26,
        ),
    ]
    toll_parking = [
        TollParkingConfig(trip_type="local", toll=80, parking=60),
        TollParkingConfig(trip_type="airport", toll=120, parking=100),
        TollParkingConfig(
            trip_type="outstation",
            toll_per_block=500,
            parking_per_block=150,
            block_days=3,
        ),
    ]
    return cab_types, fuel_types, cab_pricing, toll_parking
