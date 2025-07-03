from core.exceptions import CabboException
from core.security import RoleEnum
from models.customer.passenger_orm import Passenger
from models.customer.passenger_schema import PassengerCreate, PassengerUpdate
from sqlalchemy.orm import Session


def create_passenger(
    customer_id: str, payload: PassengerCreate, db: Session
) -> Passenger:
    """Create a new passenger for a customer.
    Args:
        customer_id (str): The UUID of the customer.
        payload (PassengerCreate): The passenger creation payload containing name and phone number.
        db (Session): The database session.
    Returns:
        Passenger: The created passenger object.

    """
    try:
        passenger = Passenger(
            customer_id=customer_id,
            name=payload.name,
            phone_number=payload.phone_number,
            is_active=True,
            created_by=RoleEnum.customer,
        )
        db.add(passenger)
        db.commit()
        db.refresh(passenger)
        return passenger
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error creating passenger: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


def get_passenger_by_id(passenger_id: str, db: Session) -> Passenger:
    """Retrieve a passenger by their ID.
    Args:
        passenger_id (str): The UUID of the passenger.
        db (Session): The database session.
    Returns:
        Passenger: The passenger object if found, otherwise None.
    """
    return db.query(Passenger).filter(Passenger.id == passenger_id).first()


def get_all_passengers_by_customer_id(customer_id: str, db: Session):
    """Retrieve all passengers for a given customer.
    Args:
        customer_id (str): The UUID of the customer.
        db (Session): The database session.
    Returns:
        List[Passenger]: A list of passenger objects associated with the customer.
    """
    return db.query(Passenger).filter(Passenger.customer_id == customer_id).all()


def get_all_active_passengers_by_customer_id(customer_id: str, db: Session):
    """Retrieve all active passengers for a given customer.
    Args:
        customer_id (str): The UUID of the customer.
        db (Session): The database session.
    Returns:
        List[Passenger]: A list of active passenger objects associated with the customer.
    """
    return (
        db.query(Passenger)
        .filter(Passenger.customer_id == customer_id, Passenger.is_active == True)
        .all()
    )


def get_all_passengers(db: Session):
    """Retrieve all passengers in the database.
    Args:
        db (Session): The database session.
    Returns:
        List[Passenger]: A list of all passenger objects.
    """
    return db.query(Passenger).all()


def get_all_active_passengers(db: Session):
    """Retrieve all active passengers in the database.
    Args:
        db (Session): The database session.
    Returns:
        List[Passenger]: A list of all active passenger objects.
    """
    return db.query(Passenger).filter(Passenger.is_active == True).all()


def update_passenger(
    passenger_id: str, payload: PassengerUpdate, db: Session
) -> Passenger:
    """Update an existing passenger's details.
    Args:
        passenger_id (str): The UUID of the passenger to update.
        payload (PassengerCreate): The updated passenger data.
        db (Session): The database session.
    Returns:
        Passenger: The updated passenger object.
    """
    passenger = get_passenger_by_id(passenger_id, db)
    if not passenger:
        raise CabboException("Passenger not found", status_code=404)

    passenger.name = payload.name
    passenger.phone_number = payload.phone_number
    db.commit()
    db.refresh(passenger)
    return passenger


def delete_passenger(passenger_id: str, db: Session) -> bool:
    """Delete a passenger by their ID.
    Args:
        passenger_id (str): The UUID of the passenger to delete.
        db (Session): The database session.
    Returns:
        bool: True if deletion was successful, False otherwise.
    """
    passenger = get_passenger_by_id(passenger_id, db)
    if not passenger:
        raise CabboException("Passenger not found", status_code=404)

    db.delete(passenger)
    db.commit()
    return True


def deactivate_passenger(passenger_id: str, db: Session) -> Passenger:
    """Deactivate a passenger by their ID.
    Args:
        passenger_id (str): The UUID of the passenger to deactivate.
        db (Session): The database session.
    Returns:
        Passenger: The deactivated passenger object.
    """
    passenger = get_passenger_by_id(passenger_id, db)
    if not passenger:
        raise CabboException("Passenger not found", status_code=404)

    passenger.is_active = False
    db.commit()
    db.refresh(passenger)
    return passenger


def activate_passenger(passenger_id: str, db: Session) -> Passenger:
    """Activate a passenger by their ID.
    Args:
        passenger_id (str): The UUID of the passenger to activate.
        db (Session): The database session.
    Returns:
        Passenger: The activated passenger object.
    """
    passenger = get_passenger_by_id(passenger_id, db)
    if not passenger:
        raise CabboException("Passenger not found", status_code=404)

    passenger.is_active = True
    db.commit()
    db.refresh(passenger)
    return passenger


def get_passenger_by_phone_number(phone_number: str, db: Session) -> Passenger:
    """Retrieve a passenger by their phone number.
    Args:
        phone_number (str): The phone number of the passenger.
        db (Session): The database session.
    Returns:
        Passenger: The passenger object if found, otherwise None.
    """
    return db.query(Passenger).filter(Passenger.phone_number == phone_number).first()
