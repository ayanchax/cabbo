APP_NAME = "cabbo"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Backend API for cab booking platform."
APP_ADMIN_EMAIL = "admin@cabbo.co.in"

AIRPORTS = {
    #It can contain multiple airports for a city in a state in a country. Here state or country is not modelled for simplicity, because airports are all over the world.
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
SEED_DATA_COMPLETION_FILE = "seed_data_completed.chk"