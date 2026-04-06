from typing import List
from sqlalchemy.orm import Session
from core.trip_helpers import create_trip_types, get_all_trip_types
from models.geography.country_schema import CountrySchema
from models.geography.region_schema import RegionSchema
from models.geography.state_schema import StateSchema
from models.policies.cancelation_schema import CancelationPolicySchema
from models.pricing.pricing_schema import (
    AirportCabPricingSchema,
    CommonPricingConfigurationSchema,
    FixedPlatformFeeConfigurationSchema,
    LocalCabPricingSchema,
    NightPricingConfigurationSchema,
    OutstationCabPricingSchema,
    PermitFeeConfigurationSchema,
    TripPackageConfigSchema,
)
from models.seed.seed_enum import SeedKeyEnum
from models.seed.seed_orm import SeedMetaData
from models.seed.seed_schema import SeedRegistryEntry
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripTypeEnum
from models.trip.trip_orm import TripTypeMaster
from services.airport_service import create_master_airports_data, get_all_airports
from services.cab_service import create_cabs, get_all_cabs
from services.kyc_service import create_master_kyc_data
from services.fuel_service import create_fuel_types, get_all_fuel_types
from services.geography_service import (
    add_region,
    add_state,
    create_countries,
    get_all_countries,
    get_all_regions,
    get_all_states,
    get_region_by_code,
    get_state_by_state_code,
    get_state_by_state_code_and_country_id,
)
from services.pricing_service import (
    create_airport_cab_pricing,
    create_cancellation_policy_pricing,
    create_common_pricing_configuration,
    create_fixed_platform_fee,
    create_local_cab_pricing,
    create_night_pricing_configuration,
    create_outstation_cab_pricing,
    create_permit_fee_configuration,
    create_trip_package_pricing_configuration,
)
from services.user_service import create_super_admin_user


SEED_COUNTRIES = [
    {
        "country_name": "India",
        "country_code": "IN",
        "currency": "INR",
        "currency_symbol": "₹",
        "flag": "🇮🇳",
        "time_zone": "Asia/Kolkata",
        "locale": "en_IN",
        "phone_code": "+91",
        "phone_number_regex": r"^[6-9]\d{9}$",
        "postal_code_regex": r"^\d{6}$",
        "is_default": True,
    },
]

SEED_STATES = [
    # Seeding states for India with (name, code)
    # This is seed data and can be updated later via admin interface
    # If we need to add more states under a country, we can do that via admin interface later
    ("Karnataka", "KA"),
    ("Tamil Nadu", "TN"),
    ("Kerala", "KL"),
    ("Andhra Pradesh", "AP"),
]

SEED_REGIONS = [
    # Return list of seed regions with (name, code, alt_names, alt_codes, state_code)
    # This is seed data and can be updated later via admin interface
    # Alt region codes are added to support multiple region codes returned by different location service providers, we will use these codes to verify service availability in a region if primary region code is not found in the LocationInfo response.
    ("Bangalore", "BLR", ["Bengaluru", "Bangalore City"], ["BEN"], "KA"),
    ("Mysore", "MYS", ["Mysuru"], [], "KA"),
]

TRIP_TYPE_SEED_DATA = [
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

CAB_TYPES_SEED_DATA = {
    CarTypeEnum.hatchback: {
        "description": "Compact hatchbacks, ideal for city rides and short trips. Most available cabs in this segment are CNG.",
        "cab_names": ["WagonR", "Celerio", "Tiago", "Santro", "i10", "Swift"],
        "inventory_cab_names": ["WagonR"],
        "capacity": "4+1",
    },
    CarTypeEnum.sedan: {
        "description": "Comfortable sedans, suitable for city and outstation travel.",
        "cab_names": ["Dzire", "Amaze", "Indigo"],
        "inventory_cab_names": ["Dzire"],
        "capacity": "4+1",
    },
    CarTypeEnum.sedan_plus: {
        "description": "Premium sedans for extra comfort and luxury.",
        "cab_names": [
            "Honda City",
            "Etios",
            "Dzire Plus",
            "Aura",
            "Xcent",
            "Verna",
            "Ciaz",
            "Yaris",
            "Slavia",
        ],
        "inventory_cab_names": ["Etios", "Dzire Plus", "Xcent", "Aura"],
        "capacity": "4+1",
    },
    CarTypeEnum.suv: {
        "description": "Spacious SUVs, good for family/group travel and rough roads.",
        "cab_names": ["Ertiga", "Innova", "Marazzo", "XL6", "Mobilio"],
        "inventory_cab_names": ["Ertiga", "Innova"],
        "capacity": "6+1",
    },
    CarTypeEnum.suv_plus: {
        "description": "Premium SUVs with extra comfort and luggage space.",
        "cab_names": ["Innova Crysta", "Hexa", "Fortuner", "XUV500", "Alcazar"],
        "inventory_cab_names": ["Innova Crysta"],
        "capacity": "7+1",
    },
}

FUEL_TYPES_SEED_DATA = [
    FuelTypeEnum.petrol,
    FuelTypeEnum.diesel,
    FuelTypeEnum.cng,
]

HOURLY_RENTAL_PACKAGES_SEED_DATA = {
    "BLR": [  # Hourly rental packages for Bangalore region
        # This is seed data and can be updated later via admin interface, where region-specific packages can be configured
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
            driver_allowance=400.0,  # Driver allowance applies for 12 hours
        ),
    ]
}

PLATFORM_FEE_BY_COUNTRY = {
    # These are fixed platform fees per booking per country
    # The fees are in local currency of the country
    # These are seed data and can be updated later via admin interface
    "IN": 3.0,  # 3 for India
    # Future countries:
    # "US": 2.5,  # $2.5 for USA
    # "AE": 10.0, # AED 10 for UAE
}


# Geo data seeding - countries, states, regions
def _seed_countries_and_states(session: Session):
    _seed_countries(session)
    _seed_states(session)


def _seed_countries(session: Session):
    # Seed countries
    countries_schema = [
        CountrySchema.model_validate(country) for country in SEED_COUNTRIES
    ]
    create_countries(countries_schema, session)


def _seed_states(session: Session):
    # Seed states
    country_states = {"IN": SEED_STATES}
    countries = get_all_countries(session)
    for country in countries:
        code = (country.country_code or "").upper()
        states_list = country_states.get(code)
        if not states_list:
            continue
        for name, scode in states_list:
            exists = get_state_by_state_code_and_country_id(
                scode.upper(), country.id, session
            )
            if exists:
                continue
            payload: StateSchema = StateSchema.model_validate(
                {
                    "state_name": name,
                    "state_code": scode.upper(),
                    "country_id": country.id,
                    "country_code": country.country_code,
                }
            )
            add_state(payload=payload, db=session)


def _seed_regions(session: Session):
    # Seed regions from states like Blr from Karnataka etc, Mysore from Karnataka etc
    supported_trip_types = []
    supported_fuel_types = []
    supported_car_types = []
    supported_airport_locations = []

    # Use the TripTypeMaster, FuelType and CabType Models to get supported types
    trip_types = get_all_trip_types(session)
    for trip_type in trip_types:
        supported_trip_types.append(trip_type.id)
    fuel_types = get_all_fuel_types(session)
    for fuel_type in fuel_types:
        supported_fuel_types.append(fuel_type.id)
    car_types = get_all_cabs(session)
    for car_type in car_types:
        supported_car_types.append(car_type.id)
    for airport in get_all_airports(session):
        supported_airport_locations.append((airport.id, airport.region_code))

    regions = SEED_REGIONS

    for name, code, alt_names, alt_codes, state_code in regions:

        state = get_state_by_state_code(state_code.upper(), session)
        if not state:
            continue
        airport_loc_ids = []
        for airport_data in supported_airport_locations:
            id, region_code = airport_data
            if region_code == code.upper():
                # This airport belongs to this region
                airport_loc_ids.append(id)

        region_schema = RegionSchema(
            region_name=name,
            region_code=code,
            alt_region_names=alt_names,
            alt_region_codes=alt_codes,
            country_id=state.country_id,
            country_code=state.country_code,
            state_id=state.id,
            state_code=state.state_code,
            trip_types=supported_trip_types,
            fuel_types=supported_fuel_types,
            car_types=supported_car_types,
            airport_locations=airport_loc_ids,
        )
        add_region(payload=region_schema, db=session)


# End of geo data seeding


# Seed master data seeding - trip types, cab types, fuel types etc
def _seed_master_data(session: Session):
    # Seed core data like trip types, cab types, fuel types
    _seed_super_admin(session)
    _seed_trip_types(session)
    _seed_cab_types(session)
    _seed_fuel_types(session)
    _seed_kyc_document_types(session)
    _seed_airports(session)


def _seed_super_admin(session: Session):
    # Create a super admin user with a secure password hash
    create_super_admin_user(session)


def _seed_trip_types(session: Session):
    # Seed trip types master data
    create_trip_types(TRIP_TYPE_SEED_DATA, session)


def _seed_cab_types(session: Session):
    # Seed cab types master data
    create_cabs(CAB_TYPES_SEED_DATA, session)


def _seed_fuel_types(session: Session):
    # Seed fuel types master data
    create_fuel_types(FUEL_TYPES_SEED_DATA, session)


def _seed_kyc_document_types(session: Session):
    # Seed KYC Document Types Master table for drivers' KYC verification
    create_master_kyc_data(session)


def _seed_airports(session: Session):
    # Seed Airports Master table
    create_master_airports_data(session=session)


# End of master data seeding


# Seed pricing data for local, airport and outstation trips
def _get_region_wise_price_map(trip_type: TripTypeEnum) -> dict:
    """Return region-wise price map for the given trip type."""
    # We will define pricing for Bangalore (BLR) region for local and airport trips
    # and Karnataka (KA) for outstation trips
    # The official seed pricing is done only for Bangalore region and Karnataka state, as we are launching there first.
    # We will manage pricing per cab type per fuel type per region and state from a dedicated super admin interface later
    if trip_type == TripTypeEnum.local:
        region_wise_price_map = {
            "BLR": {
                "hourly_rates": {
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
                },
                "overage_amount_per_hour": {
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
                },
                "overage_amount_per_km": {
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
                },
            },
            "MYS": {
                "hourly_rates": {
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
                },
                "overage_amount_per_hour": {
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
                },
                "overage_amount_per_km": {
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
                },
            },
        }
        return region_wise_price_map

    if trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        region_wise_price_map = {
            "BLR": {
                "fare_per_km": {
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
                },
                "overage_amount_per_km": {
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
                },
            }
        }
        return region_wise_price_map
    if trip_type == TripTypeEnum.outstation:
        region_wise_price_map = {
            "KA": {
                "base_fare": {
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
                },
                "driver_allowance_per_day": {
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
                },
                "min_km_per_day": {
                    CarTypeEnum.hatchback: 300,
                    CarTypeEnum.sedan: 300,
                    CarTypeEnum.sedan_plus: 300,
                    CarTypeEnum.suv: 300,
                    CarTypeEnum.suv_plus: 300,
                },
                "overage_amount_per_km": {
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
                },
            },
            "TN": {
                "base_fare": {
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
                },
                "driver_allowance_per_day": {
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
                },
                "min_km_per_day": {
                    CarTypeEnum.hatchback: 300,
                    CarTypeEnum.sedan: 300,
                    CarTypeEnum.sedan_plus: 300,
                    CarTypeEnum.suv: 300,
                    CarTypeEnum.suv_plus: 300,
                },
                "overage_amount_per_km": {
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
                },
            },
            "KL": {
                "base_fare": {
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
                },
                "driver_allowance_per_day": {
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
                },
                "min_km_per_day": {
                    CarTypeEnum.hatchback: 300,
                    CarTypeEnum.sedan: 300,
                    CarTypeEnum.sedan_plus: 300,
                    CarTypeEnum.suv: 300,
                    CarTypeEnum.suv_plus: 300,
                },
                "overage_amount_per_km": {
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
                },
            },
            "AP": {
                "base_fare": {
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
                },
                "driver_allowance_per_day": {
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
                },
                "min_km_per_day": {
                    CarTypeEnum.hatchback: 300,
                    CarTypeEnum.sedan: 300,
                    CarTypeEnum.sedan_plus: 300,
                    CarTypeEnum.suv: 300,
                    CarTypeEnum.suv_plus: 300,
                },
                "overage_amount_per_km": {
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
                },
            },
        }
        return region_wise_price_map
    return {}


def _seed_local_cab_pricing(session: Session):
    # Seed local cab pricing data per cab type and fuel type and region
    price_map = _get_region_wise_price_map(TripTypeEnum.local)
    cab_types = get_all_cabs(session)
    fuel_types = get_all_fuel_types(session)
    is_available_in_network = True
    trip_type_master_objs = get_all_trip_types(session)
    trip_type_id_map = {obj.trip_type: obj.id for obj in trip_type_master_objs}

    for region_code, region_data in price_map.items():
        region = get_region_by_code(region_code.upper(), session)
        if not region:
            continue
        region_id = region.id
        for cab in cab_types:
            for fuel in fuel_types:
                # Local
                if cab.name == CarTypeEnum.hatchback and fuel.name in [
                    FuelTypeEnum.petrol,
                    FuelTypeEnum.diesel,
                ]:
                    is_available_in_network = False
                elif cab.name == CarTypeEnum.suv and fuel.name in [
                    FuelTypeEnum.diesel,
                    FuelTypeEnum.cng,
                ]:
                    is_available_in_network = False
                elif cab.name == CarTypeEnum.suv_plus and fuel.name in [
                    FuelTypeEnum.cng
                ]:
                    is_available_in_network = False
                else:
                    is_available_in_network = True
                payload: LocalCabPricingSchema = LocalCabPricingSchema(
                    is_available_in_network=is_available_in_network,
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    hourly_rate=region_data["hourly_rates"][cab.name][fuel.name],
                    overage_amount_per_hour=region_data["overage_amount_per_hour"][
                        cab.name
                    ][fuel.name],
                    overage_amount_per_km=region_data["overage_amount_per_km"][
                        cab.name
                    ][fuel.name],
                    region_id=region_id,
                )
                create_local_cab_pricing(payload, session)

        # Keeping a separate tripwise pricing configuration for local trips as these will be redundant if kept within LocalCabPricing table.
        # Hence to preserve normalization of DB, we are keeping a separate table for tripwise pricing configuration
        # For seeding the data, we are assuming some standard values for local trips across regions
        # These can be updated later via admin interface as needed
        common_payload: CommonPricingConfigurationSchema = (
            CommonPricingConfigurationSchema(
                trip_type_id=trip_type_id_map[TripTypeEnum.local],
                dynamic_platform_fee_percent=4,  # platform fee
                min_included_hours=4,  # Minimum 4 hours for local trips
                max_included_hours=12,  # Maximum 12 hours for local trips
                min_included_km=40,  # Minimum 40 km included for local trips
                max_included_km=120,  # Maximum 120 km included for local trips
                region_id=region_id,
            )
        )
        create_common_pricing_configuration(common_payload, session)

    _seed_local_trip_packages(session)


def _seed_outstation_cab_pricing(session: Session):
    # Seed outstation cab pricing data per cab type and fuel type
    price_map = _get_region_wise_price_map(TripTypeEnum.outstation)
    cab_types = get_all_cabs(session)
    fuel_types = get_all_fuel_types(session)
    is_available_in_network = True
    trip_type_master_objs = get_all_trip_types(session)
    trip_type_id_map = {obj.trip_type: obj.id for obj in trip_type_master_objs}

    for state_code, state_data in price_map.items():
        state = get_state_by_state_code(state_code.upper(), session)
        if not state:
            continue  # if seed data for state is not found in StateModel, skip to next
        state_id = state.id
        for cab in cab_types:
            for fuel in fuel_types:
                # Outstation
                if cab.name == CarTypeEnum.hatchback and fuel.name in [
                    FuelTypeEnum.petrol,
                    FuelTypeEnum.diesel,
                    FuelTypeEnum.cng,
                ]:
                    is_available_in_network = False
                elif cab.name == CarTypeEnum.suv and fuel.name in [
                    FuelTypeEnum.diesel,
                    FuelTypeEnum.cng,
                ]:
                    is_available_in_network = False
                elif cab.name == CarTypeEnum.suv_plus and fuel.name in [
                    FuelTypeEnum.cng
                ]:
                    is_available_in_network = False
                else:
                    is_available_in_network = True
                payload: OutstationCabPricingSchema = OutstationCabPricingSchema(
                    is_available_in_network=is_available_in_network,
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    base_fare_per_km=state_data["base_fare"][cab.name][fuel.name],
                    driver_allowance_per_day=state_data["driver_allowance_per_day"][
                        cab.name
                    ][fuel.name],
                    min_included_km_per_day=state_data["min_km_per_day"][cab.name],
                    overage_amount_per_km=state_data["overage_amount_per_km"][cab.name][
                        fuel.name
                    ],
                    state_id=state_id,
                )
                create_outstation_cab_pricing(payload, session)

                # Keeping a separate tripwise pricing configuration for outstation trips as these will be redundant if kept within OutstationCabPricing table.
                # Hence to preserve normalization of DB, we are keeping a separate table for tripwise pricing
                # For seeding the data, we are assuming some standard values for outstation trips across states
                # These can be updated later via admin interface as needed
        common_payload: CommonPricingConfigurationSchema = (
            CommonPricingConfigurationSchema(
                trip_type_id=trip_type_id_map[TripTypeEnum.outstation],
                dynamic_platform_fee_percent=3,  # 3% platform fee/convenience fee
                overage_warning_km_threshold=50,  # Warning threshold for overages
                state_id=state_id,
            )
        )
        create_common_pricing_configuration(common_payload, session)


def _seed_airport_cab_pricing(session: Session):
    # Seed airport cab pricing data per cab type and fuel type
    price_map = _get_region_wise_price_map(TripTypeEnum.airport_pickup)
    cab_types = get_all_cabs(session)
    fuel_types = get_all_fuel_types(session)
    is_available_in_network = True
    trip_type_master_objs = get_all_trip_types(session)
    trip_type_id_map = {obj.trip_type: obj.id for obj in trip_type_master_objs}
    for region_code, region_data in price_map.items():
        region = get_region_by_code(region_code.upper(), session)
        if not region:
            continue
        region_id = region.id
        for cab in cab_types:
            for fuel in fuel_types:
                # Airport
                if cab.name == CarTypeEnum.hatchback and fuel.name in [
                    FuelTypeEnum.petrol,
                    FuelTypeEnum.diesel,
                ]:
                    is_available_in_network = False
                elif cab.name == CarTypeEnum.suv and fuel.name in [FuelTypeEnum.diesel]:
                    is_available_in_network = False
                elif cab.name == CarTypeEnum.suv_plus and fuel.name in [
                    FuelTypeEnum.cng
                ]:
                    is_available_in_network = False
                else:
                    is_available_in_network = True
                payload: AirportCabPricingSchema = AirportCabPricingSchema(
                    is_available_in_network=is_available_in_network,
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    fare_per_km=region_data["fare_per_km"][cab.name][fuel.name],
                    overage_amount_per_km=region_data["overage_amount_per_km"][
                        cab.name
                    ][fuel.name],
                    region_id=region_id,
                )
                create_airport_cab_pricing(payload, session)

                # Keeping a separate tripwise pricing configuration for airport trips as these will be redundant if kept within AirportCabPricing table.
                # Hence to preserve normalization of DB, we are keeping a separate table for tripwise pricing
        common_payload: List[CommonPricingConfigurationSchema] = [
            CommonPricingConfigurationSchema(
                trip_type_id=trip_type_id_map[TripTypeEnum.airport_pickup],
                dynamic_platform_fee_percent=3,  # platform fee/convenience fee
                placard_charge=50.0,  # Fixed charge for airport pickup if customer opts for it
                max_included_km=42,  # 42 km included for airport trips is a common standard
                overage_warning_km_threshold=2,  # Warning threshold for overages
                toll=120,  # toll for airport pickup set to 120 if customer opts for it
                parking=100,  # parking charge for airport pickup
                region_id=region_id,
            ),
            CommonPricingConfigurationSchema(
                trip_type_id=trip_type_id_map[TripTypeEnum.airport_drop],
                dynamic_platform_fee_percent=3,  # platform fee/convenience fee
                max_included_km=42,  # 42 km included for airport trips is a standard
                overage_warning_km_threshold=2,  # Warning threshold for overages
                toll=120,  # toll for airport drop set to 120 if customer opts for it
                parking=0,  # no parking charge for airport drop
                region_id=region_id,
            ),
        ]
        for common_payload in common_payload:
            create_common_pricing_configuration(common_payload, session)


def _seed_local_trip_packages(session: Session):
    # Seed local rental package configurations
    trip_type_master_objs = session.query(TripTypeMaster).all()
    trip_type_id_map = {obj.trip_type: obj.id for obj in trip_type_master_objs}
    local_trip_type_id = trip_type_id_map.get(TripTypeEnum.local)

    if not local_trip_type_id:
        print("Local trip type not found. Skipping package seeding.")
        return

    for region_code, packages in HOURLY_RENTAL_PACKAGES_SEED_DATA.items():
        region = get_region_by_code(region_code.upper(), session)
        if not region:
            print(f"Region {region_code} not found. Skipping packages.")
            continue

        for package_data in packages:
            payload = TripPackageConfigSchema(
                trip_type_id=local_trip_type_id,
                region_id=region.id,  # ✅ Now region-specific
                included_hours=package_data.included_hours,
                included_km=package_data.included_km,
                driver_allowance=package_data.driver_allowance,
                package_label=package_data.package_label,
            )
            create_trip_package_pricing_configuration(payload, session)


def _seed_cancelation_policy_pricing(session: Session):
    # Seed cancellation policy pricing configurations
    # Insert into CancellationPolicy based on region for local and airport trips and state for outstation trips
    trip_type_master_objs = get_all_trip_types(session)
    trip_type_id_map = {obj.trip_type: obj.id for obj in trip_type_master_objs}
    regions = get_all_regions(session)
    states = get_all_states(session)
    for region in regions:
        for trip_type in [
            TripTypeEnum.local,
            TripTypeEnum.airport_pickup,
            TripTypeEnum.airport_drop,
        ]:
            payload = None
            # For seeding the data, we are assuming some standard values for cancellation policies across regions
            # These can be updated later via admin interface per region and trip type as needed
            if trip_type in [
                TripTypeEnum.airport_pickup,
                TripTypeEnum.airport_drop,
            ]:
                payload: CancelationPolicySchema = CancelationPolicySchema(
                    trip_type_id=trip_type_id_map[trip_type],
                    region_id=region.id,
                    free_cutoff_minutes=30,  # Free cancellation within 30 minutes
                    free_cutoff_time_label="30 minutes before trip start",
                    refund_percentage=20,  # No refund if cancelled after free period for airport trips considering the short notice and potential driver inconvenience
                )

            elif trip_type == TripTypeEnum.local:
                payload: CancelationPolicySchema = CancelationPolicySchema(
                    trip_type_id=trip_type_id_map[trip_type],
                    region_id=region.id,
                    free_cutoff_minutes=60,  # Free cancellation within 60 minutes/1h
                    free_cutoff_time_label="1 hour before trip start",
                    refund_percentage=50.0,  # Refund 50% of the fare if cancelled after free period for local trips considering the short notice and potential driver inconvenience
                )
            if payload:
                create_cancellation_policy_pricing(payload, session)

    for state in states:
        # For seeding the data, we are assuming some standard values for cancellation policies across states
        # This can be updated later via admin interface per state as needed
        trip_type = TripTypeEnum.outstation
        payload: CancelationPolicySchema = CancelationPolicySchema(
            trip_type_id=trip_type_id_map[trip_type],
            state_id=state.id,
            free_cutoff_minutes=1440,  # Free cancellation within 1440 minutes/24h
            free_cutoff_time_label="1 day before trip start",
            refund_percentage=80.0,  # Refund 80% of the fare if cancelled after free period for outstation trips considering the short notice and potential driver inconvenience
        )
        create_cancellation_policy_pricing(payload, session)
        # Full refund policy For cancellation before free cutoff time, we are doing 100% refund across all trip types and regions/states considering the cancellation is done well in advance and allows for better driver re-allocation and customer satisfaction. This can be updated later via admin interface as needed. No questions asked.


def _seed_fixed_platform_pricing(session: Session):
    # Seed fixed platform pricing configurations
    # Fixed platform fee/infrastructure fee for all trips
    countries = get_all_countries(session)
    for country in countries:
        country_code = country.country_code
        platform_fee = PLATFORM_FEE_BY_COUNTRY.get(country_code)

        if platform_fee is None:
            print(f"No platform fee configured for {country_code}. Skipping.")
            continue

        payload = FixedPlatformFeeConfigurationSchema(
            fixed_platform_fee=platform_fee, country_id=country.id
        )
        create_fixed_platform_fee(payload, session)


def _seed_night_pricing(session: Session):
    regions = get_all_regions(session)
    states = get_all_states(session)
    for region in regions:
        payload: NightPricingConfigurationSchema = NightPricingConfigurationSchema(
            night_start_hour=20,  # 8PM
            night_end_hour=6,  # 6AM
            region_id=region.id,
            night_hours_label="8PM to 6AM",
        )
        create_night_pricing_configuration(payload, session)

    for state in states:
        payload: NightPricingConfigurationSchema = NightPricingConfigurationSchema(
            night_start_hour=20,  # 8PM
            night_end_hour=6,  # 6AM
            state_id=state.id,
            night_hours_label="8PM to 6AM",
        )
        create_night_pricing_configuration(payload, session)


def _get_weekly_permit_fee_per_state():
    # Return weekly permit fee mapping per state per car type per fuel type for mainly outstation trips
    # This is seed data and can be updated later via admin interface
    # Currently we support KA, TN, KL, AP states for outstation trips
    weekly_permit_fees_mapping = {
        "KA": {
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
    return weekly_permit_fees_mapping


def _seed_permit_fee_pricing(session: Session):
    permit_fee_config_per_state = _get_weekly_permit_fee_per_state()
    states = get_all_states(session)
    cab_types = get_all_cabs(session)
    fuel_types = get_all_fuel_types(session)
    for state in states:
        state_code = state.state_code.upper()
        fee_map = permit_fee_config_per_state.get(state_code, None)
        if not fee_map:
            continue
        for cab in cab_types:
            for fuel in fuel_types:
                weekly_fee = fee_map.get(cab.name, {}).get(fuel.name, None)
                if not weekly_fee:
                    continue
                payload: PermitFeeConfigurationSchema = PermitFeeConfigurationSchema(
                    state_id=state.id,
                    cab_type_id=cab.id,
                    fuel_type_id=fuel.id,
                    permit_fee=weekly_fee,
                )
                create_permit_fee_configuration(payload, session)


# End of pricing data seeding


def is_seed_completed(
    db: Session,
    key: SeedKeyEnum = SeedKeyEnum.INITIAL_SEED_COMPLETED,
    value: str = "true",
) -> bool:
    try:
        record = db.query(SeedMetaData).filter(SeedMetaData.key == key).first()

        return record is not None and record.value == value
    except Exception as e:
        print(f"Error checking seed completion for {key} with value {value}: {e}")
        return False


def mark_seed_completed(
    db: Session,
    key: SeedKeyEnum = SeedKeyEnum.INITIAL_SEED_COMPLETED,
    value: str = "true",
):
    try:
        record = db.query(SeedMetaData).filter(SeedMetaData.key == key).first()

        if record:
            record.value = value
        else:
            db.add(
                SeedMetaData(
                    key=key,
                    value=value,
                )
            )

        db.flush()
    except Exception as e:
        print(f"Error marking seed as completed: {e}")
        raise e


def run_seed_registry(session: Session):
    registry = SEED_REGISTRY
    try:
        session.begin()
        for seed in registry:
            key = seed.key
            func = seed.func
            dependencies = seed.depends_on
            # ✅ Dependency validation
            for dep in dependencies:
                if not is_seed_completed(session, dep):
                    raise Exception(f"Dependency {dep} not completed for {key}")
            # Fail fast
            if is_seed_completed(session, key):
                print(f"Seed already completed for key: {key}. Skipping.")
                continue
            print(f"Running seed function for key: {key}")
            func(session)
            mark_seed_completed(session, key)
            print(f"Completed seed function for key: {key}")

        session.commit()
        print("All seed functions in registry have been processed.")
    except Exception as e:
        session.rollback()
        print(f"Error during seed registry execution: {e}")
        raise e




SEED_REGISTRY: list[SeedRegistryEntry] = [
    SeedRegistryEntry(
        key=SeedKeyEnum.SEED_MASTER_DATA_V1,
        func=_seed_master_data,
        depends_on=[],
    ),
    SeedRegistryEntry(
        key=SeedKeyEnum.SEED_GEO_CORE_V1,
        func=_seed_countries_and_states,
        depends_on=[SeedKeyEnum.SEED_MASTER_DATA_V1],
    ),
    SeedRegistryEntry(
        key=SeedKeyEnum.SEED_GEO_REGIONS_V1,
        func=_seed_regions,
        depends_on=[SeedKeyEnum.SEED_GEO_CORE_V1],
    ),
    SeedRegistryEntry(
        key=SeedKeyEnum.SEED_PRICING_LOCAL_V1,
        func=_seed_local_cab_pricing,
        depends_on=[
            SeedKeyEnum.SEED_MASTER_DATA_V1,
            SeedKeyEnum.SEED_GEO_REGIONS_V1,
        ],
    ),
    SeedRegistryEntry(
        key=SeedKeyEnum.SEED_PRICING_OUTSTATION_V1,
        func=_seed_outstation_cab_pricing,
        depends_on=[
            SeedKeyEnum.SEED_MASTER_DATA_V1,
            SeedKeyEnum.SEED_GEO_CORE_V1,
        ],
    ),
    SeedRegistryEntry(
        key=SeedKeyEnum.SEED_PRICING_AIRPORT_V1,
        func=_seed_airport_cab_pricing,
        depends_on=[
            SeedKeyEnum.SEED_MASTER_DATA_V1,
            SeedKeyEnum.SEED_GEO_REGIONS_V1,
        ],
    ),
    SeedRegistryEntry(
        key=SeedKeyEnum.SEED_PRICING_PLATFORM_V1,
        func=_seed_fixed_platform_pricing,
        depends_on=[SeedKeyEnum.SEED_GEO_CORE_V1],
    ),
    SeedRegistryEntry(
        key=SeedKeyEnum.SEED_PRICING_NIGHT_V1,
        func=_seed_night_pricing,
        depends_on=[
            SeedKeyEnum.SEED_GEO_CORE_V1,
            SeedKeyEnum.SEED_GEO_REGIONS_V1,
        ],
    ),
    SeedRegistryEntry(
        key=SeedKeyEnum.SEED_PRICING_PERMIT_V1,
        func=_seed_permit_fee_pricing,
        depends_on=[SeedKeyEnum.SEED_GEO_CORE_V1],
    ),
    SeedRegistryEntry(
        key=SeedKeyEnum.SEED_PRICING_CANCELLATION_POLICY_V1,
        func=_seed_cancelation_policy_pricing,
        depends_on=[
            SeedKeyEnum.SEED_GEO_CORE_V1,
            SeedKeyEnum.SEED_GEO_REGIONS_V1,
        ],
    ),
]
