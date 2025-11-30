import json
from typing import List
import uuid
from sqlalchemy.orm import Session
from models.cab.cab_orm import CabType, FuelType
from models.geography.country_orm import CountryModel
from models.geography.country_schema import CountrySchema
from models.map.location_schema import LocationInfo
from models.geography.state_orm import StateModel
from models.policies.cancelation_orm import CancellationPolicy
from models.pricing.pricing_orm import (
    CommonPricingConfiguration,
    FixedPlatformPricingConfiguration,
    OutstationCabPricing,
    LocalCabPricing,
    AirportCabPricing,
    NightPricingConfiguration,
    FixedPlatformPricingConfiguration,
)
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripTypeEnum
from core.security import RoleEnum
from models.geography.region_orm import RegionModel
from models.trip.trip_orm import TripPackageConfig, TripTypeMaster
from models.trip.trip_schema import TripPackageConfigSchema
from models.pricing.pricing_orm import PermitFeeConfiguration
from services.cab_service import create_cabs
from services.document_service import create_master_kyc_data
from services.file_service import is_file_exists, is_file_exists, save_file
from services.fuel_service import create_fuel_types
from services.geography_service import create_countries, get_all_countries
from services.trip_service import create_trip_types
from services.user_service import create_super_admin_user

SEED_DATA_COMPLETION_FILE = "seed_data_completed.chk"

SEED_COUNTRIES=[
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

# Airport data for seed data initialization
SEED_AIRPORTS = {
    # It can contain multiple airports for a city in a state in a country. Here state or country is not modelled for simplicity, because airports are all over the world regions and we are focusing on few regions/cities only for seed data.
    # Admin can add more airports for a city/region via admin panel if needed.
    # Admin can also add more regions/cities via admin panel if needed.
    "BLR": [
        {
            "display_name": "Kempegowda International Airport, Bengaluru",
            "lat": 13.1986,
            "lng": 77.7066,
            "place_id": "ChIJL_P_CXMEDTkRw0ZdG-0GVvw",  # official Mapbox place ID for the airport in Bengaluru
            "address": "Kempegowda International Airport, Devanahalli, Bengaluru, Karnataka 560300, India",
        }
    ],
    "MYS": [
        {
            "display_name": "Mysore Airport, Mysore",
            "lat": 12.3052,
            "lng": 76.6536,
            "place_id": "ChIJX8f5gq6rDTkR6e-8K5J7hYzA",  # official Mapbox place ID for the airport in Mysore
            "address": "Mysore Airport, Mandakalli, Mysore, Karnataka 570008, India",
        }
    ],
    "MAA": [
        {
            "display_name": "Chennai International Airport, Chennai",
            "lat": 12.9941,
            "lng": 80.1709,
            "place_id": "ChIJGZ0fW3KqDTkR6r1K5J7hYzA",  # official Mapbox place ID for the airport in Chennai
            "address": "Chennai International Airport, Tirusulam, Chennai, Tamil Nadu 600027, India",
        }
    ],
}

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
        "cab_names": "WagonR, Celerio, Tiago, Santro, i10, Swift",
        "inventory_cab_names": "WagonR",
        "capacity": "4+1",
    },
    CarTypeEnum.sedan: {
        "description": "Comfortable sedans, suitable for city and outstation travel.",
        "cab_names": "Dzire, Amaze, Indigo",
        "inventory_cab_names": "Dzire",
        "capacity": "4+1",
    },
    CarTypeEnum.sedan_plus: {
        "description": "Premium sedans for extra comfort and luxury.",
        "cab_names": "Honda City, Etios, Dzire Plus, Aura, Xcent, Verna, Ciaz, Yaris, Slavia",
        "inventory_cab_names": "Etios, Dzire Plus, Xcent, Aura",
        "capacity": "4+1",
    },
    CarTypeEnum.suv: {
        "description": "Spacious SUVs, good for family/group travel and rough roads.",
        "cab_names": "Ertiga, Innova, Marazzo, XL6, Mobilio",
        "inventory_cab_names": "Ertiga, Innova",
        "capacity": "6+1",
    },
    CarTypeEnum.suv_plus: {
        "description": "Premium SUVs with extra comfort and luggage space.",
        "cab_names": "Innova Crysta, Hexa, Fortuner, XUV500, Alcazar",
        "inventory_cab_names": "Innova Crysta",
        "capacity": "7+1",
    },
}    

FUEL_TYPES_SEED_DATA = [
    FuelTypeEnum.petrol,
    FuelTypeEnum.diesel,
    FuelTypeEnum.cng,
]
def _get_regional_airports(airports_in_region: List[dict]) -> List[dict]:
    """Convert airport dicts to LocationInfo and back to dicts for JSON serialization."""
    if airports_in_region is None:
        airports_in_region = []

    if airports_in_region and len(airports_in_region) > 0:
        # Validate with Pydantic to ensure data integrity
        validated_airports = [
            LocationInfo.model_validate(ap) for ap in airports_in_region
        ]
        # Convert back to dict for JSON serialization
        airports_in_region = [ap.model_dump() for ap in validated_airports]

    return airports_in_region


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


def _get_seed_states():
    return [
        ("Karnataka", "KA"),
        ("Tamil Nadu", "TN"),
        ("Kerala", "KL"),
        ("Andhra Pradesh", "AP"),
    ]


def _get_seed_regions():
    # Return list of seed regions with (name, code, alt_names, state_code)
    # This is seed data and can be updated later via admin interface
    return [
        ("Bangalore", "BLR", ["Bengaluru", "Bangalore City"], "KA"),
        ("Mysore", "MYS", ["Mysuru"], "KA"),
    ]


def init_seed_data(session: Session):
    """Initialize seed data for the application."""
    is_seeded = is_file_exists(SEED_DATA_COMPLETION_FILE)
    if is_seeded:
        print("Seed data already initialized. Skipping seeding.")
        return
    try:
        session.begin()

        _seed_master_data(session)

        _seed_geographical_data(session)

        _seed_pricing_data(session)
        session.commit()

        # Create a completion of seed data file at the root of the project Cabbo to indicate seeding is done and avoid re-seeding
        save_file(SEED_DATA_COMPLETION_FILE, "Seed data initialization completed.")
        print("Seed data initialization completed.")
    except Exception as e:
        session.rollback()
        print(f"Error during seed data initialization: {e}")
        raise e
    finally:
        session.close()


def _seed_geographical_data(session: Session):
    # Seed countries, states, regions
    _seed_countries(session)
    _seed_states(session)
    _seed_regions(session)


def _seed_master_data(session: Session):
    # Seed core data like trip types, cab types, fuel types
    _seed_super_admin(session)
    _seed_trip_types(session)
    _seed_cab_types(session)
    _seed_fuel_types(session)
    _seed_kyc_document_types(session)


def _seed_pricing_data(session: Session):
    # Seed pricing data
    _seed_local_cab_pricing(session)
    _seed_outstation_cab_pricing(session)
    _seed_airport_cab_pricing(session)
    _seed_fixed_platform_pricing(session)
    _seed_night_pricing(session)
    _seed_permit_fee_pricing(session)
    _seed_cancelation_policy_pricing(session)


def _seed_countries(session: Session):
    # Seed countries
    countries_schema=[CountrySchema.model_validate(country) for country in SEED_COUNTRIES]
    create_countries(countries_schema, session)


def _seed_states(session: Session):
    # Seed states
    country_states = {"IN": _get_seed_states()}
    countries = get_all_countries(session)
    states = []
    for country in countries:
        code = (country.country_code or "").upper()
        states_list = country_states.get(code)
        if not states_list:
            continue
        for name, scode in states_list:
            exists = (
                session.query(StateModel)
                .filter(
                    StateModel.country_id == country.id,
                    StateModel.state_code == scode.upper(),
                )
                .first()
            )
            if exists:
                continue
            state = StateModel(
                state_name=name,
                state_code=scode.upper(),
                country_id=country.id,
            )
            states.append(state)

    session.add_all(states)
    session.commit()


def _seed_regions(session: Session):
    # Seed regions from states like Blr from Karnataka etc, Mysore from Karnataka etc
    supported_trip_types = []
    supported_fuel_types = []
    supported_car_types = []

    # Use the TripTypeMaster, FuelType and CabType Models to get supported types
    trip_types = session.query(TripTypeMaster).all()
    for trip_type in trip_types:
        supported_trip_types.append(trip_type.id)
    fuel_types = session.query(FuelType).all()
    for fuel_type in fuel_types:
        supported_fuel_types.append(fuel_type.id)
    car_types = session.query(CabType).all()
    for car_type in car_types:
        supported_car_types.append(car_type.id)
    regions = _get_seed_regions()
    _regions = []
    for name, code, alt_names, state_code in regions:
        state = (
            session.query(StateModel)
            .filter(StateModel.state_code == state_code.upper())
            .first()
        )
        if not state:
            continue
        airports_in_region = _get_regional_airports(SEED_AIRPORTS.get(code, None))

        region = RegionModel(
            region_name=name,
            region_code=code,
            region_alt_names=alt_names,
            country_id=state.country_id,
            state_id=state.id,
            trip_types=(
                json.dumps(supported_trip_types) if supported_trip_types else None
            ),
            fuel_types=(
                json.dumps(supported_fuel_types) if supported_fuel_types else None
            ),
            car_types=json.dumps(supported_car_types) if supported_car_types else None,
            airport_locations=(
                json.dumps(airports_in_region) if airports_in_region else None
            ),
        )
        _regions.append(region)
    session.add_all(_regions)
    session.commit()


def _seed_trip_types(session: Session):
    # Seed trip types master data
    create_trip_types(TRIP_TYPE_SEED_DATA, session)


def _seed_cab_types(session: Session):
    # Seed cab types master data
    create_cabs(CAB_TYPES_SEED_DATA, session)


def _seed_fuel_types(session: Session):
    # Seed fuel types master data
    create_fuel_types(FUEL_TYPES_SEED_DATA, session)
         


def _seed_local_cab_pricing(session: Session):
    # Seed local cab pricing data per cab type and fuel type and region
    price_map = _get_region_wise_price_map(TripTypeEnum.local)
    local_pricing = []
    secondary_local_pricing = []
    cab_types = session.query(CabType).all()
    fuel_types = session.query(FuelType).all()
    is_available_in_network = True
    trip_type_master_objs = session.query(TripTypeMaster).all()
    trip_type_id_map = {obj.trip_type: obj.id for obj in trip_type_master_objs}

    for region_code, region_data in price_map.items():
        region = (
            session.query(RegionModel)
            .filter(
                RegionModel.region_code == region_code.upper(),
                RegionModel.is_serviceable == True,
            )
            .first()
        )
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
                local_pricing.append(
                    LocalCabPricing(
                        id=str(uuid.uuid4()),
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
                        created_by=RoleEnum.system,
                    )
                )
                # Keeping a separate tripwise pricing configuration for local trips as these will be redundant if kept within LocalCabPricing table.
                # Hence to preserve normalization of DB, we are keeping a separate table for tripwise pricing configuration
                # For seeding the data, we are assuming some standard values for local trips across regions
                # These can be updated later via admin interface as needed
                secondary_local_pricing.append(
                    CommonPricingConfiguration(
                        id=str(uuid.uuid4()),
                        trip_type_id=trip_type_id_map[TripTypeEnum.local],
                        dynamic_platform_fee_percent=0.5,  # platform fee/convenience fee
                        placard_charge=50.0,  # Fixed charge for airport pickup if customer opts for it
                        max_included_km=42,  # 42 km included for airport trips is a common standard
                        overage_warning_km_threshold=2,  # Warning threshold for overages
                        toll=120,  # toll for airport pickup set to 120 if customer opts for it
                        parking=100,  # parking charge for airport pickup
                        created_by=RoleEnum.system,
                        region_id=region_id,
                    )
                )

    session.add_all(local_pricing)
    session.add_all(secondary_local_pricing)
    session.commit()
    _seed_local_trip_packages(session)


def _seed_outstation_cab_pricing(session: Session):
    # Seed outstation cab pricing data per cab type and fuel type
    price_map = _get_region_wise_price_map(TripTypeEnum.outstation)
    outstation_pricing = []
    secondary_outstation_pricing = []
    cab_types = session.query(CabType).all()
    fuel_types = session.query(FuelType).all()
    is_available_in_network = True
    trip_type_master_objs = session.query(TripTypeMaster).all()
    trip_type_id_map = {obj.trip_type: obj.id for obj in trip_type_master_objs}

    for state_code, state_data in price_map.items():
        state = (
            session.query(StateModel)
            .filter(
                StateModel.state_code == state_code.upper(),
                StateModel.is_serviceable == True,
            )
            .first()
        )
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
                outstation_pricing.append(
                    OutstationCabPricing(
                        id=str(uuid.uuid4()),
                        is_available_in_network=is_available_in_network,
                        cab_type_id=cab.id,
                        fuel_type_id=fuel.id,
                        base_fare_per_km=state_data["base_fare"][cab.name][fuel.name],
                        driver_allowance_per_day=state_data["driver_allowance_per_day"][
                            cab.name
                        ][fuel.name],
                        min_included_km_per_day=state_data["min_km_per_day"][cab.name],
                        overage_amount_per_km=state_data["overage_amount_per_km"][
                            cab.name
                        ][fuel.name],
                        state_id=state_id,
                        created_by=RoleEnum.system,
                    )
                )
                # Keeping a separate tripwise pricing configuration for outstation trips as these will be redundant if kept within OutstationCabPricing table.
                # Hence to preserve normalization of DB, we are keeping a separate table for tripwise pricing
                # For seeding the data, we are assuming some standard values for outstation trips across states
                # These can be updated later via admin interface as needed
                secondary_outstation_pricing.append(
                    CommonPricingConfiguration(
                        id=str(uuid.uuid4()),
                        trip_type_id=trip_type_id_map[TripTypeEnum.outstation],
                        dynamic_platform_fee_percent=3,  # 3% platform fee/convenience fee
                        overage_warning_km_threshold=50,  # Warning threshold for overages
                        minimum_toll_wallet=500,  # minimum toll 500 for outstation trips
                        minimum_parking_wallet=150,  # minimum parking 150 for outstation trips
                        created_by=RoleEnum.system,
                        state_id=state_id,
                    )
                )
    session.add_all(outstation_pricing)
    session.add_all(secondary_outstation_pricing)
    session.commit()


def _seed_airport_cab_pricing(session: Session):
    # Seed airport cab pricing data per cab type and fuel type
    price_map = _get_region_wise_price_map(TripTypeEnum.airport_pickup)
    airport_pricing = []
    airport_secondary_pricing = []

    cab_types = session.query(CabType).all()
    fuel_types = session.query(FuelType).all()
    is_available_in_network = True
    trip_type_master_objs = session.query(TripTypeMaster).all()
    trip_type_id_map = {obj.trip_type: obj.id for obj in trip_type_master_objs}
    for region_code, region_data in price_map.items():
        region = (
            session.query(RegionModel)
            .filter(
                RegionModel.region_code == region_code.upper(),
                RegionModel.is_serviceable == True,
            )
            .first()
        )
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
                airport_pricing.append(
                    AirportCabPricing(
                        id=str(uuid.uuid4()),
                        is_available_in_network=is_available_in_network,
                        cab_type_id=cab.id,
                        fuel_type_id=fuel.id,
                        fare_per_km=region_data["fare_per_km"][cab.name][fuel.name],
                        overage_amount_per_km=region_data["overage_amount_per_km"][
                            cab.name
                        ][fuel.name],
                        region_id=region_id,
                        created_by=RoleEnum.system,
                    )
                )

                # Keeping a separate tripwise pricing configuration for airport trips as these will be redundant if kept within AirportCabPricing table.
                # Hence to preserve normalization of DB, we are keeping a separate table for tripwise pricing
                airport_secondary_pricing.append(
                    CommonPricingConfiguration(
                        id=str(uuid.uuid4()),
                        trip_type_id=trip_type_id_map[TripTypeEnum.airport_pickup],
                        dynamic_platform_fee_percent=0.5,  # platform fee/convenience fee
                        placard_charge=50.0,  # Fixed charge for airport pickup if customer opts for it
                        max_included_km=42,  # 42 km included for airport trips is a common standard
                        overage_warning_km_threshold=2,  # Warning threshold for overages
                        toll=120,  # toll for airport pickup set to 120 if customer opts for it
                        parking=100,  # parking charge for airport pickup
                        created_by=RoleEnum.system,
                        region_id=region_id,
                    )
                )
                airport_secondary_pricing.append(
                    CommonPricingConfiguration(
                        id=str(uuid.uuid4()),
                        trip_type_id=trip_type_id_map[TripTypeEnum.airport_drop],
                        dynamic_platform_fee_percent=0.5,  # platform fee/convenience fee
                        max_included_km=42,  # 42 km included for airport trips is a standard
                        overage_warning_km_threshold=2,  # Warning threshold for overages
                        toll=120,  # toll for airport drop set to 120 if customer opts for it
                        parking=0,  # no parking charge for airport drop
                        created_by=RoleEnum.system,
                        region_id=region_id,
                    )
                )

    session.add_all(airport_pricing)
    session.add_all(airport_secondary_pricing)
    session.commit()


def _seed_local_trip_packages(session: Session):
    # Seed local rental package configurations
    trip_type_master_objs = session.query(TripTypeMaster).all()
    trip_type_id_map = {obj.trip_type: obj.id for obj in trip_type_master_objs}
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
    session.add_all(trip_package_configs)
    session.commit()


def _seed_cancelation_policy_pricing(session: Session):
    # Seed cancellation policy pricing configurations
    # Insert into CancellationPolicy based on trip types and region for local and airport trips and state for outstation trips
    trip_type_master_objs = session.query(TripTypeMaster).all()
    trip_type_id_map = {obj.trip_type: obj.id for obj in trip_type_master_objs}
    regions = (
        session.query(RegionModel).filter(RegionModel.is_serviceable == True).all()
    )
    states = session.query(StateModel).filter(StateModel.is_serviceable == True).all()
    cancelation_policies = []
    for region in regions:
        for trip_type in [
            TripTypeEnum.local,
            TripTypeEnum.airport_pickup,
            TripTypeEnum.airport_drop,
        ]:
            # For seeding the data, we are assuming some standard values for cancellation policies across regions
            # These can be updated later via admin interface as needed
            if trip_type in [
                TripTypeEnum.airport_pickup,
                TripTypeEnum.airport_drop,
            ]:
                cancelation_policy = CancellationPolicy(
                    id=str(uuid.uuid4()),
                    trip_type_id=trip_type_id_map[trip_type],
                    region_id=region.id,
                    free_cutoff_minutes=30,  # Free cancellation within 30 minutes
                    free_cutoff_time_label="30 minutes before trip start",
                    cancelation_amount=20.0,  # Flat cancellation fee after free period
                    created_by=RoleEnum.system,
                )
            elif trip_type == TripTypeEnum.local:
                cancelation_policy = CancellationPolicy(
                    id=str(uuid.uuid4()),
                    trip_type_id=trip_type_id_map[trip_type],
                    region_id=region.id,
                    free_cutoff_minutes=60,  # Free cancellation within 60 minutes
                    free_cutoff_time_label="1 hour before trip start",
                    cancelation_amount=50.0,  # Flat cancellation fee after free period
                    created_by=RoleEnum.system,
                )
            cancelation_policies.append(cancelation_policy)

    for state in states:
        # For seeding the data, we are assuming some standard values for cancellation policies across states
        trip_type = TripTypeEnum.outstation
        cancelation_policy = CancellationPolicy(
            id=str(uuid.uuid4()),
            trip_type_id=trip_type_id_map[trip_type],
            state_id=state.id,
            free_cutoff_minutes=1440,  # Free cancellation within 1440 minutes
            free_cutoff_time_label="1 day before trip start",
            cancelation_amount=100.0,  # Flat cancellation fee after free period
            created_by=RoleEnum.system,
        )
        cancelation_policies.append(cancelation_policy)
    session.add_all(cancelation_policies)
    session.commit()


def _seed_fixed_platform_pricing(session: Session):
    # Seed fixed platform pricing configurations
    # Fixed platform fee/infrastructure fee for all trips
    fixed_platform_fee_config = FixedPlatformPricingConfiguration(
        id=str(uuid.uuid4()), fixed_platform_fee=3.0
    )
    session.add(fixed_platform_fee_config)
    session.commit()


def _seed_night_pricing(session: Session):
    regions = (
        session.query(RegionModel).filter(RegionModel.is_serviceable == True).all()
    )
    states = session.query(StateModel).filter(StateModel.is_serviceable == True).all()
    night_charge_configs = []
    for region in regions:
        night_charge_config = NightPricingConfiguration(
            id=str(uuid.uuid4()),
            night_start_hour=20,  # 8PM
            night_end_hour=6,  # 6AM
            region_id=region.id,
            created_by=RoleEnum.system,
        )
        night_charge_configs.append(night_charge_config)
    for state in states:
        night_charge_config = NightPricingConfiguration(
            id=str(uuid.uuid4()),
            night_start_hour=20,  # 8PM
            night_end_hour=6,  # 6AM
            state_id=state.id,
            created_by=RoleEnum.system,
        )
        night_charge_configs.append(night_charge_config)
    session.add_all(night_charge_configs)
    session.commit()


def _seed_super_admin(session: Session):
    # Create a super admin user with a secure password hash
    create_super_admin_user(session)


def _seed_permit_fee_pricing(session: Session):
    permit_fee_config_per_state = _get_weekly_permit_fee_per_state()
    states = session.query(StateModel).all()
    cab_types = session.query(CabType).all()
    fuel_types = session.query(FuelType).all()
    permit_fee_pricings = []
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
                permit_fee_pricings.append(
                    PermitFeeConfiguration(
                        id=str(uuid.uuid4()),
                        state_id=state.id,
                        cab_type_id=cab.id,
                        fuel_type_id=fuel.id,
                        permit_fee=weekly_fee,
                        created_by=RoleEnum.system,
                    )
                )
    session.add_all(permit_fee_pricings)
    session.commit()


def _seed_kyc_document_types(session: Session):
    # Seed KYC Document Types Master table for drivers' KYC verification
    create_master_kyc_data(session)
