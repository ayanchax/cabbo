from typing import Optional
from pydantic_core import ValidationError
import json
from typing import Optional
from pydantic import ValidationError
from sqlalchemy.orm import Session
from models.geography.country_orm import CountryModel
from models.geography.country_schema import CountrySchema
from models.geography.region_orm import RegionModel
from models.geography.region_schema import RegionSchema, RegionUpdate
from models.geography.state_orm import StateModel
from models.geography.state_schema import StateSchema


def get_region(
    country_code: str, state_code: str, region_code: str, db: Session
) -> Optional["RegionSchema"]:
    """Fetch the RegionSchema for the given country code and region code.
    Returns None if not found.
    """
    # Join countryModel and regionModel to fetch region details

    region_data = (
        db.query(RegionModel, CountryModel, StateModel)
        .join(CountryModel, RegionModel.country_id == CountryModel.id)
        .join(StateModel, RegionModel.state_id == StateModel.id)
        .filter(
            CountryModel.country_code == country_code,
            StateModel.state_code == state_code,
            RegionModel.region_code == region_code,
        )
        .first()
    )
    if region_data:
        region_model, country_model, state_model = region_data
        r_model: RegionModel = region_model
        c_model: CountryModel = country_model
        s_model: StateModel = state_model
        try:
            region_schema = RegionSchema(
                region_name=r_model.region_name,
                region_code=r_model.region_code,
                region_alt_names=(
                    json.loads(r_model.region_alt_names)
                    if r_model.region_alt_names
                    else None
                ),
                state_code=s_model.state_code if s_model.state_code else None,
                country_code=c_model.country_code,
                trip_types=(
                    json.loads(r_model.trip_types) if r_model.trip_types else None
                ),
                fuel_types=(
                    json.loads(r_model.fuel_types) if r_model.fuel_types else None
                ),
                car_types=json.loads(r_model.car_types) if r_model.car_types else None,
                airport_locations=(
                    json.loads(r_model.airport_locations)
                    if r_model.airport_locations
                    else None
                ),
            )

            return region_schema
        except ValidationError:
            return None


def get_region_by_id(region_id: str, db: Session) -> Optional["RegionSchema"]:
    """Fetch the RegionSchema for the given region ID.
    Returns None if not found.
    """
    region_model = db.query(RegionModel).filter(RegionModel.id == region_id).first()
    if region_model:
        try:
            region_schema = RegionSchema(
                region_name=region_model.region_name,
                region_code=region_model.region_code,
                region_alt_names=(
                    json.loads(region_model.region_alt_names)
                    if region_model.region_alt_names
                    else None
                ),
                state_code=None,  # State code not fetched here
                country_code=None,  # Country code not fetched here
                trip_types=(
                    json.loads(region_model.trip_types)
                    if region_model.trip_types
                    else None
                ),
                fuel_types=(
                    json.loads(region_model.fuel_types)
                    if region_model.fuel_types
                    else None
                ),
                car_types=(
                    json.loads(region_model.car_types)
                    if region_model.car_types
                    else None
                ),
                airport_locations=(
                    json.loads(region_model.airport_locations)
                    if region_model.airport_locations
                    else None
                ),
            )
            return region_schema
        except ValidationError:
            return None


def get_all_regions(db: Session) -> list["RegionSchema"]:
    """Fetch all regions as a list of RegionSchema."""
    region_models = db.query(RegionModel).all()
    region_schemas = []
    for r_model in region_models:
        try:
            region_schema = RegionSchema(
                region_name=r_model.region_name,
                region_code=r_model.region_code,
                region_alt_names=(
                    json.loads(r_model.region_alt_names)
                    if r_model.region_alt_names
                    else None
                ),
                state_code=None,  # State code not fetched here
                country_code=None,  # Country code not fetched here
                trip_types=(
                    json.loads(r_model.trip_types) if r_model.trip_types else None
                ),
                fuel_types=(
                    json.loads(r_model.fuel_types) if r_model.fuel_types else None
                ),
                car_types=json.loads(r_model.car_types) if r_model.car_types else None,
                airport_locations=(
                    json.loads(r_model.airport_locations)
                    if r_model.airport_locations
                    else None
                ),
            )
            region_schemas.append(region_schema)
        except ValidationError:
            continue
    return region_schemas


def get_regions_by_country(country_code: str, db: Session) -> list["RegionSchema"]:
    """Fetch all regions for a given country code as a list of RegionSchema."""
    country_model = (
        db.query(CountryModel).filter(CountryModel.country_code == country_code).first()
    )
    if not country_model:
        return []

    region_models = (
        db.query(RegionModel).filter(RegionModel.country_id == country_model.id).all()
    )
    region_schemas = []
    for r_model in region_models:
        try:
            region_schema = RegionSchema(
                region_name=r_model.region_name,
                region_code=r_model.region_code,
                region_alt_names=(
                    json.loads(r_model.region_alt_names)
                    if r_model.region_alt_names
                    else None
                ),
                state_code=None,  # State code not fetched here
                country_code=country_code,
                trip_types=(
                    json.loads(r_model.trip_types) if r_model.trip_types else None
                ),
                fuel_types=(
                    json.loads(r_model.fuel_types) if r_model.fuel_types else None
                ),
                car_types=json.loads(r_model.car_types) if r_model.car_types else None,
                airport_locations=(
                    json.loads(r_model.airport_locations)
                    if r_model.airport_locations
                    else None
                ),
            )
            region_schemas.append(region_schema)
        except ValidationError:
            continue
    return region_schemas


def get_regions_by_state(
    country_code: str, state_code: str, db: Session
) -> list["RegionSchema"]:
    """Fetch all regions for a given country code and state code as a list of RegionSchema."""
    country_model = (
        db.query(CountryModel).filter(CountryModel.country_code == country_code).first()
    )
    if not country_model:
        return []

    state_model = (
        db.query(StateModel)
        .filter(
            StateModel.state_code == state_code,
            StateModel.country_id == country_model.id,
        )
        .first()
    )
    if not state_model:
        return []
    region_models = (
        db.query(RegionModel).filter(RegionModel.state_id == state_model.id).all()
    )
    region_schemas = []
    for r_model in region_models:
        try:
            region_schema = RegionSchema(
                region_name=r_model.region_name,
                region_code=r_model.region_code,
                region_alt_names=(
                    json.loads(r_model.region_alt_names)
                    if r_model.region_alt_names
                    else None
                ),
                state_code=state_code,
                country_code=country_code,
                trip_types=(
                    json.loads(r_model.trip_types) if r_model.trip_types else None
                ),
                fuel_types=(
                    json.loads(r_model.fuel_types) if r_model.fuel_types else None
                ),
                car_types=json.loads(r_model.car_types) if r_model.car_types else None,
                airport_locations=(
                    json.loads(r_model.airport_locations)
                    if r_model.airport_locations
                    else None
                ),
            )
            region_schemas.append(region_schema)
        except ValidationError:
            continue
    return region_schemas


def add_region(payload: RegionSchema, db: Session) -> RegionSchema:
    """Add a new region to the database."""
    try:
        # Fetch country and state models
        country_model = (
            db.query(CountryModel)
            .filter(CountryModel.country_code == payload.country_code)
            .first()
        )
        if not country_model:
            raise ValueError(f"Country with code {payload.country_code} not found.")

        state_model = (
            db.query(StateModel)
            .filter(
                StateModel.state_code == payload.state_code,
                StateModel.country_id == country_model.id,
            )
            .first()
        )
        if not state_model:
            raise ValueError(
                f"State with code {payload.state_code} not found in country {payload.country_code}."
            )
        region_model = RegionModel(
            region_name=payload.region_name,
            region_code=payload.region_code.upper(),
            region_alt_names=(
                json.dumps(payload.region_alt_names)
                if payload.region_alt_names
                else None
            ),
            state_id=state_model.id,
            country_id=country_model.id,
            trip_types=json.dumps(payload.trip_types) if payload.trip_types else None,
            fuel_types=json.dumps(payload.fuel_types) if payload.fuel_types else None,
            car_types=json.dumps(payload.car_types) if payload.car_types else None,
            airport_locations=(
                json.dumps(payload.airport_locations)
                if payload.airport_locations
                else None
            ),
        )
        db.add(region_model)
        db.commit()
        db.refresh(region_model)
        return RegionSchema.model_validate(region_model)
    except Exception as e:
        db.rollback()
        raise e


def update_region(
    region_id: str, payload: RegionUpdate, db: Session
) -> Optional[RegionSchema]:
    """Update an existing region in the database."""
    region_model = db.query(RegionModel).filter(RegionModel.id == region_id).first()
    if not region_model:
        return None
    try:
        if payload.region_name is not None:
            region_model.region_name = payload.region_name
        if payload.region_alt_names is not None:
            region_model.region_alt_names = json.dumps(payload.region_alt_names)
        db.commit()
        db.refresh(region_model)
        return RegionSchema.model_validate(region_model)
    except Exception as e:
        db.rollback()
        raise e


def delete_region(region_id: str, db: Session) -> bool:
    """Delete a region from the database."""
    region_model = db.query(RegionModel).filter(RegionModel.id == region_id).first()
    if not region_model:
        return False
    try:
        db.delete(region_model)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e


def get_all_countries(db: Session) -> list["CountrySchema"]:
    """Fetch all countries as a list of CountrySchema."""
    country_models = db.query(CountryModel).all()
    country_schemas = []
    for c_model in country_models:
        try:
            country_schema = CountrySchema.model_validate(c_model)
            country_schemas.append(country_schema)
        except ValidationError:
            continue
    return country_schemas


def add_country(payload: CountrySchema, db: Session) -> CountrySchema:
    """Add a new country to the database."""
    try:
        country_model = CountryModel(
            country_name=payload.country_name,
            country_code=payload.country_code.upper(),
            phone_code=payload.phone_code,
            currency=payload.currency,
            currency_symbol=payload.currency_symbol,
            time_zone=payload.time_zone,
            flag=payload.flag,
            locale=payload.locale,
        )
        db.add(country_model)
        db.commit()
        db.refresh(country_model)
        return CountrySchema.model_validate(country_model)
    except Exception as e:
        db.rollback()
        raise e


def update_country(
    country_id: str, payload: CountrySchema, db: Session
) -> Optional[CountrySchema]:
    """Update an existing country in the database."""
    # We will not allow updating any fields in country as these fields are immutable once set
    pass


def delete_country(country_id: str, db: Session) -> bool:
    """Delete a country from the database."""
    country_model = db.query(CountryModel).filter(CountryModel.id == country_id).first()
    if not country_model:
        return False
    try:
        db.delete(country_model)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e


def get_country_by_code(country_code: str, db: Session) -> Optional["CountrySchema"]:
    """Fetch the CountrySchema for the given country code.
    Returns None if not found.
    """
    country_model = (
        db.query(CountryModel)
        .filter(CountryModel.country_code == country_code.upper())
        .first()
    )
    if country_model:
        try:
            country_schema = CountrySchema.model_validate(country_model)
            return country_schema
        except ValidationError:
            return None


def get_all_states(db: Session) -> list["StateSchema"]:
    """Fetch all states as a list of StateSchema."""
    state_models = db.query(StateModel).all()
    state_schemas = []
    for s_model in state_models:
        try:
            state_schema = StateSchema.model_validate(s_model)
            state_schemas.append(state_schema)
        except ValidationError:
            continue
    return state_schemas


def get_states_by_country(country_code: str, db: Session) -> list["StateSchema"]:
    """Fetch all states for a given country code as a list of StateSchema."""
    country_model = (
        db.query(CountryModel).filter(CountryModel.country_code == country_code).first()
    )
    if not country_model:
        return []

    state_models = (
        db.query(StateModel).filter(StateModel.country_id == country_model.id).all()
    )
    state_schemas = []
    for s_model in state_models:
        try:
            state_schema = StateSchema.model_validate(s_model)
            state_schemas.append(state_schema)
        except ValidationError:
            continue
    return state_schemas


def get_state_by_code(
    country_code: str, state_code: str, db: Session
) -> Optional["StateSchema"]:
    """Fetch the StateSchema for the given country code and state code.
    Returns None if not found.
    """
    country_model = (
        db.query(CountryModel).filter(CountryModel.country_code == country_code).first()
    )
    if not country_model:
        return None

    state_model = (
        db.query(StateModel)
        .filter(
            StateModel.state_code == state_code,
            StateModel.country_id == country_model.id,
        )
        .first()
    )
    if state_model:
        try:
            state_schema = StateSchema.model_validate(state_model)
            return state_schema
        except ValidationError:
            return None


def add_state(payload: StateSchema, db: Session) -> StateSchema:
    """Add a new state to the database."""
    try:
        # Fetch country model
        country_model = (
            db.query(CountryModel)
            .filter(CountryModel.country_code == payload.country_code.upper())
            .first()
        )
        if not country_model:
            raise ValueError(f"Country with code {payload.country_code} not found.")

        state_model = StateModel(
            state_name=payload.state_name,
            state_code=payload.state_code.upper(),
            country_id=country_model.id,
        )
        db.add(state_model)
        db.commit()
        db.refresh(state_model)
        return StateSchema.model_validate(state_model)
    except Exception as e:
        db.rollback()
        raise e


def update_state(
    state_id: str, payload: StateSchema, db: Session
) -> Optional[StateSchema]:
    """Update an existing state in the database."""
    # We will not allow updating any fields in state as these fields are immutable once set
    pass


def delete_state(state_id: str, db: Session) -> bool:
    """Delete a state from the database."""
    state_model = db.query(StateModel).filter(StateModel.id == state_id).first()
    if not state_model:
        return False
    try:
        db.delete(state_model)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e
