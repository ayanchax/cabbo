# Master configuration for cab types, fuel types, and pricing

# Example structure: {car_type: {fuel_type: {"base_fare_per_km": value, "hourly_rate": value, "driver_allowance": value, "airport_fare_per_km": value}}}
# Outstation: use base_fare_per_km and driver_allowance (per day), daily allotted km = 300km
# Local: use hourly_rate, minimum rental duration = 3 hours
# Airport: use airport_fare_per_km, calculate km from pickup/drop to airport
CAB_PRICING_CONFIG = {
    "Hatchback": {
        "petrol": {
            "base_fare_per_km": 10,
            "hourly_rate": 120,
            "driver_allowance": 250,
            "airport_fare_per_km": 15,
        },
        "diesel": {
            "base_fare_per_km": 9,
            "hourly_rate": 110,
            "driver_allowance": 240,
            "airport_fare_per_km": 14,
        },
        "cng": {
            "base_fare_per_km": 8,
            "hourly_rate": 100,
            "driver_allowance": 230,
            "airport_fare_per_km": 13,
        },
    },
    "Sedan": {
        "petrol": {
            "base_fare_per_km": 12,
            "hourly_rate": 150,
            "driver_allowance": 300,
            "airport_fare_per_km": 18,
        },
        "diesel": {
            "base_fare_per_km": 11,
            "hourly_rate": 140,
            "driver_allowance": 290,
            "airport_fare_per_km": 17,
        },
        "cng": {
            "base_fare_per_km": 10,
            "hourly_rate": 130,
            "driver_allowance": 280,
            "airport_fare_per_km": 16,
        },
    },
    "SUV": {
        "petrol": {
            "base_fare_per_km": 15,
            "hourly_rate": 200,
            "driver_allowance": 400,
            "airport_fare_per_km": 22,
        },
        "diesel": {
            "base_fare_per_km": 14,
            "hourly_rate": 190,
            "driver_allowance": 390,
            "airport_fare_per_km": 21,
        },
        "cng": {
            "base_fare_per_km": 13,
            "hourly_rate": 180,
            "driver_allowance": 380,
            "airport_fare_per_km": 20,
        },
    },
    "SUV+": {
        "petrol": {
            "base_fare_per_km": 18,
            "hourly_rate": 250,
            "driver_allowance": 500,
            "airport_fare_per_km": 28,
        },
        "diesel": {
            "base_fare_per_km": 17,
            "hourly_rate": 240,
            "driver_allowance": 490,
            "airport_fare_per_km": 27,
        },
        "cng": {
            "base_fare_per_km": 16,
            "hourly_rate": 230,
            "driver_allowance": 480,
            "airport_fare_per_km": 26,
        },
    },
}

# Tolls and parking configuration for pricing logic
# For local and airport: fixed toll and parking
# For outstation: toll = 350 * ceil(num_days / 3), parking = 120 * ceil(num_days / 3)
TOLL_PARKING_CONFIG = {
    "local": {"toll": 80, "parking": 60},
    "airport": {"toll": 120, "parking": 100},
    "outstation": {"toll_per_block": 500, "parking_per_block": 150, "block_days": 3},
}

# You can add more config such as minimum fare, night charges, etc. as needed.
