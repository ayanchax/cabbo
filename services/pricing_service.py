# Stub for pricing logic service


def calculate_price(
    origin,
    destination,
    start_date,
    end_date,
    car_type,
    fuel_type,
    hops,
    is_interstate,
    is_round_trip,
    num_adults,
    num_children,
    num_luggages,
):
    # TODO: Implement config-driven pricing logic
    # Return dummy values for now
    return {
        "base_fare": 1000,
        "allowance": 200,
        "tolls_estimate": 150,
        "parking_estimate": 50,
        "platform_fee": 100,
        "permit_fee": 0 if not is_interstate else 500,
        "total_price": 1500 if not is_interstate else 2000,
    }
