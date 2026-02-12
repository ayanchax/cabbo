from typing import Dict, Optional
from pydantic_core import ValidationError
import json
from typing import Optional
from pydantic import ValidationError
from sqlalchemy.orm import Session
from core.exceptions import CabboException
from core.security import RoleEnum
from models.geography.country_orm import CountryModel
from models.geography.country_schema import CountrySchema, CountryUpdateSchema
from models.geography.region_orm import RegionModel
from models.geography.region_schema import RegionSchema, RegionUpdate
from models.geography.state_orm import StateModel
from models.geography.state_schema import StateSchema, StateUpdateSchema
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update


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
            RegionModel.is_serviceable == True,
            StateModel.is_serviceable == True,
            CountryModel.is_serviceable == True,
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
                alt_region_names=(
                    json.loads(r_model.alt_region_names)
                    if r_model.alt_region_names
                    else None
                ),
                alt_region_codes=(
                    json.loads(r_model.alt_region_codes)
                    if r_model.alt_region_codes
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
    region_model = (
        db.query(RegionModel)
        .filter(RegionModel.id == region_id, RegionModel.is_serviceable == True)
        .first()
    )
    if region_model:
        try:
            region_schema = RegionSchema(
                region_name=region_model.region_name,
                region_code=region_model.region_code,
                alt_region_names=(
                    json.loads(region_model.alt_region_names)
                    if region_model.alt_region_names
                    else None
                ),
                alt_region_codes=(
                    json.loads(region_model.alt_region_codes)
                    if region_model.alt_region_codes
                    else None
                ),
                state_code=region_model.state_id,   
                country_code=region_model.country_id,  
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

def get_region_by_code(region_code: str, db: Session) -> Optional["RegionSchema"]:
    """Fetch the RegionSchema for the given region code.
    Returns None if not found.
    """
    region_model = (
        db.query(RegionModel)
        .filter(RegionModel.region_code == region_code, RegionModel.is_serviceable == True)
        .first()
    )
    if region_model:
        try:
            region_schema = RegionSchema(
                id=region_model.id,
                region_name=region_model.region_name,
                region_code=region_model.region_code,
                alt_region_names=(
                    json.loads(region_model.alt_region_names)
                    if region_model.alt_region_names
                    else None
                ),
                alt_region_codes=(
                    json.loads(region_model.alt_region_codes)
                    if region_model.alt_region_codes
                    else None
                ),
                state_code=region_model.state_id,   
                country_code=region_model.country_id,  
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
    return None

def get_all_regions(db: Session) -> list["RegionSchema"]:
    """Fetch all regions as a list of RegionSchema."""
    region_models = db.query(RegionModel).filter(RegionModel.is_serviceable == True).all()
    region_schemas = []
    for r_model in region_models:
        try:
            region_schema = RegionSchema(
                region_name=r_model.region_name,
                region_code=r_model.region_code,
                alt_region_names=(
                    json.loads(r_model.alt_region_names)
                    if r_model.alt_region_names
                    else None
                ),
                alt_region_codes=(
                    json.loads(r_model.alt_region_codes)
                    if r_model.alt_region_codes
                    else None
                ),
                id=r_model.id,
                state_id=r_model.state_id,
                country_id=r_model.country_id,
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
        db.query(CountryModel)
        .filter(CountryModel.country_code == country_code, CountryModel.is_serviceable == True)
        .first()
    )
    if not country_model:
        return []

    region_models = (
        db.query(RegionModel)
        .filter(RegionModel.country_id == country_model.id, RegionModel.is_serviceable == True)
        .all()
    )
    region_schemas = []
    for r_model in region_models:
        try:
            region_schema = RegionSchema(
                region_name=r_model.region_name,
                region_code=r_model.region_code,
                alt_region_names=(
                    json.loads(r_model.alt_region_names)
                    if r_model.alt_region_names
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
        db.query(CountryModel)
        .filter(CountryModel.country_code == country_code, CountryModel.is_serviceable == True)
        .first()
    )
    if not country_model:
        return []

    state_model = (
        db.query(StateModel)
        .filter(
            StateModel.state_code == state_code,
            StateModel.country_id == country_model.id,
            StateModel.is_serviceable == True,
        )
        .first()
    )
    if not state_model:
        return []
    region_models = (
        db.query(RegionModel)
        .filter(RegionModel.state_id == state_model.id, RegionModel.is_serviceable == True)
        .all()
    )
    region_schemas = []
    for r_model in region_models:
        try:
            region_schema = RegionSchema(
                region_name=r_model.region_name,
                region_code=r_model.region_code,
                alt_region_names=(
                    json.loads(r_model.alt_region_names)
                    if r_model.alt_region_names
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
            .filter(
                (CountryModel.country_code == payload.country_code) | (CountryModel.id == payload.country_id),
                CountryModel.is_serviceable == True,
            )
            .first()
        )
        if not country_model:
            raise ValueError(f"Country with code {payload.country_code} not found.")

        state_model = (
            db.query(StateModel)
            .filter(
                StateModel.state_code == payload.state_code,
                StateModel.country_id == country_model.id,
                StateModel.is_serviceable == True,
            )
            .first()
        )
        if not state_model:
            raise ValueError(
                f"State with code {payload.state_code} not found in country {payload.country_code or payload.country_id}."
            )
        region_model = RegionModel(
            region_name=payload.region_name,
            region_code=payload.region_code.upper(),
            alt_region_names=(
                []
                if not payload.alt_region_names or len(payload.alt_region_names) == 0
                else json.dumps(payload.alt_region_names)
            ),
            alt_region_codes=(
                []
                if not payload.alt_region_codes or len(payload.alt_region_codes) == 0
                else json.dumps(payload.alt_region_codes)
            ),
            state_id=state_model.id,
            country_id=country_model.id,
            trip_types=(
                [] if not payload.trip_types or len(payload.trip_types) == 0 else json.dumps(payload.trip_types)
            ),
            fuel_types=(
                [] if not payload.fuel_types or len(payload.fuel_types) == 0 else json.dumps(payload.fuel_types)
            ),
            car_types=(
                [] if not payload.car_types or len(payload.car_types) == 0 else json.dumps(payload.car_types)
            ),
            airport_locations=(
                [] if not payload.airport_locations or len(payload.airport_locations) == 0 else json.dumps(payload.airport_locations)
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
    region_model = (
        db.query(RegionModel)
        .filter(RegionModel.id == region_id, RegionModel.is_serviceable == True)
        .first()
    )
    if not region_model:
        return None
    try:
        #We only allow updating region_name and region_alt_names
        if payload.region_name is not None:
            region_model.region_name = payload.region_name
        if payload.alt_region_names is not None:
            region_model.alt_region_names = json.dumps(payload.alt_region_names)
        db.commit()
        db.refresh(region_model)
        return RegionSchema.model_validate(region_model)
    except Exception as e:
        db.rollback()
        raise e


def delete_region(region_id: str, db: Session) -> bool:
    """Delete a region from the database."""
    region_model = (
        db.query(RegionModel)
        .filter(RegionModel.id == region_id, RegionModel.is_serviceable == True)
        .first()
    )
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
    country_models = db.query(CountryModel).filter(CountryModel.is_serviceable == True).all()
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
            currency=payload.currency,
            currency_symbol=payload.currency_symbol,
            flag=payload.flag,
            time_zone=payload.time_zone,
            locale=payload.locale,
            phone_code=payload.phone_code,
            phone_number_regex=payload.phone_regex,
            postal_code_regex=payload.postal_code_regex,
            is_default=payload.is_default if payload.is_default else False,
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
    country_model = (
        db.query(CountryModel)
        .filter(CountryModel.id == country_id, CountryModel.is_serviceable == True)
        .first()
    )
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
        .filter(
            CountryModel.country_code == country_code.upper() | CountryModel.id == country_code,
            CountryModel.is_serviceable == True,
        )
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
    state_models = db.query(StateModel).filter(StateModel.is_serviceable == True).all()
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
        db.query(CountryModel)
        .filter(CountryModel.country_code == country_code, CountryModel.is_serviceable == True)
        .first()
    )
    if not country_model:
        return []

    state_models = (
        db.query(StateModel)
        .filter(StateModel.country_id == country_model.id, StateModel.is_serviceable == True)
        .all()
    )
    state_schemas = []
    for s_model in state_models:
        try:
            state_schema = StateSchema.model_validate(s_model)
            state_schemas.append(state_schema)
        except ValidationError:
            continue
    return state_schemas


def get_state_by_state_code(
    state_code: str, db: Session
) -> Optional["StateSchema"]:
    """Fetch the StateSchema for the given state code.
    Returns None if not found.
    """
    

    state_model = (
        db.query(StateModel)
        .filter(
            StateModel.state_code == state_code,
            StateModel.is_serviceable == True,
        )
        .first()
    )
    if state_model:
        try:
            state_schema = StateSchema.model_validate(state_model)
            return state_schema
        except ValidationError:
            return None
    return None

def get_state_by_id(state_id: str, db: Session) -> Optional["StateSchema"]:
    """Fetch the StateSchema for the given state ID.
    Returns None if not found.
    """
    state_model = (
        db.query(StateModel)
        .filter(StateModel.id == state_id, StateModel.is_serviceable == True)
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
            .filter(
                CountryModel.country_code == payload.country_code.upper(),
                CountryModel.is_serviceable == True,
            )
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
    state_model = (
        db.query(StateModel)
        .filter(StateModel.id == state_id, StateModel.is_serviceable == True)
        .first()
    )
    if not state_model:
        return False
    try:
        db.delete(state_model)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e


def disable_state(state_id: str, db: Session) -> bool:
    """Disable a state in the database."""
    state_model = (
        db.query(StateModel)
        .filter(StateModel.id == state_id, StateModel.is_serviceable == True)
        .first()
    )
    if not state_model:
        return False
    try:
        state_model.is_serviceable = False
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e


def enable_state(state_id: str, db: Session) -> bool:
    """Enable a state in the database."""
    state_model = (
        db.query(StateModel)
        .filter(StateModel.id == state_id, StateModel.is_serviceable == False)
        .first()
    )
    if not state_model:
        return False
    try:
        state_model.is_serviceable = True
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e


def disable_country(country_id: str, db: Session) -> bool:
    """Disable a country in the database."""
    country_model = (
        db.query(CountryModel)
        .filter(CountryModel.id == country_id, CountryModel.is_serviceable == True)
        .first()
    )
    if not country_model:
        return False
    try:
        country_model.is_serviceable = False
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e


def enable_country(country_id: str, db: Session) -> bool:
    """Enable a country in the database."""
    country_model = (
        db.query(CountryModel)
        .filter(CountryModel.id == country_id, CountryModel.is_serviceable == False)
        .first()
    )
    if not country_model:
        return False
    try:
        country_model.is_serviceable = True
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e


def disable_region(region_id: str, db: Session) -> bool:
    """Disable a region in the database."""
    region_model = (
        db.query(RegionModel)
        .filter(RegionModel.id == region_id, RegionModel.is_serviceable == True)
        .first()
    )
    if not region_model:
        return False
    try:
        region_model.is_serviceable = False
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e


def enable_region(region_id: str, db: Session) -> bool:
    """Enable a region in the database."""
    region_model = (
        db.query(RegionModel)
        .filter(RegionModel.id == region_id, RegionModel.is_serviceable == False)
        .first()
    )
    if not region_model:
        return False
    try:
        region_model.is_serviceable = True
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e

def create_countries(countries:list[CountrySchema], db:Session):
    for country in countries:
        add_country(country, db)

def get_state_by_state_code_and_country_id(state_code:str, country_id:str, db:Session) -> Optional[StateSchema]:
    """Fetch the StateSchema for the given state code and country ID.
    Returns None if not found.
    """
    state_model = (
        db.query(StateModel)
        .filter(
            StateModel.state_code == state_code.upper(),
            StateModel.country_id == country_id,
            StateModel.is_serviceable == True,  
        )
        .first()
    )
    if state_model:
        try:
            state_schema = StateSchema.model_validate(state_model)
            return state_schema
        except ValidationError:
            return None
    return None

def get_states_by_country_id(country_id: str, db: Session) -> list["StateSchema"]:
    """Fetch all states for a given country ID as a list of StateSchema."""
    state_models = (
        db.query(StateModel)
        .filter(StateModel.country_id == country_id, StateModel.is_serviceable == True)
        .all()
    )
    state_schemas = []
    for s_model in state_models:
        try:
            state_schema = StateSchema.model_validate(s_model)
            state_schemas.append(state_schema)
        except ValidationError:
            continue
    return state_schemas

def get_regions_by_state_id(state_id: str, db: Session) -> list["RegionSchema"]:
    """Fetch all regions for a given state ID as a list of RegionSchema."""
    region_models = (
        db.query(RegionModel)
        .filter(RegionModel.state_id == state_id, RegionModel.is_serviceable == True)
        .all()
    )
    region_schemas = []
    for r_model in region_models:
        try:
            region_schema = RegionSchema(
                id=r_model.id,
                region_name=r_model.region_name,
                region_code=r_model.region_code,
                alt_region_names=(
                    json.loads(r_model.alt_region_names)
                    if r_model.alt_region_names
                    else None
                ),
                state_id=r_model.state_id,
                country_id=r_model.country_id,
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

def lookup_region_by_code(regions:Dict[str, RegionSchema], region_code:str) -> Optional[RegionSchema]:
    for _, region in regions.items():
        if not region.is_serviceable:
            continue
        if region.region_code.upper() == region_code:
            return region
        if region.alt_region_codes and region_code in [code.upper() for code in region.alt_region_codes]:
            return region
    return None #If we reach here, no matching region found or region is not serviceable

def lookup_state_by_code(states:Dict[str, StateSchema], state_code:str) -> Optional[StateSchema]:
    for _, state in states.items():
        if not state.is_serviceable:
            continue
        if state.state_code.upper() == state_code:
            return state
    return None #If we reach here, no matching state found or state is not serviceable

def look_up_state_by_id(states:Dict[str, StateSchema], state_id:str) -> Optional[StateSchema]:
    for _, state in states.items():
        if not state.is_serviceable:
            continue
        if state.id == state_id:
            return state
    return None #If we reach here, no matching state found or state is not serviceable

def lookup_country_by_country_id(countries:Dict[str, CountrySchema], country_id:str) -> Optional[CountrySchema]:
    for _, country in countries.items():
        if not country.is_serviceable:
            continue
        if country.id == country_id:
            return country
    return None #If we reach here, no matching country found or country is not serviceable

async def async_add_country(payload: CountrySchema, db:AsyncSession, created_by:RoleEnum) -> CountrySchema:
    """Asynchronously add a new country to the system configuration."""
    try:
        if payload.is_default: # If the new country is marked as default, unset the default flag from all other countries 
            await db.execute(update(CountryModel).where(CountryModel.is_default == True).values(is_default=False) )
        
        country_model = CountryModel(
            country_name=payload.country_name,
                country_code=payload.country_code.upper(),
                currency=payload.currency,
                currency_symbol=payload.currency_symbol,
                flag=payload.flag,
                time_zone=payload.time_zone,
                locale=payload.locale,
                phone_code=payload.phone_code,
                phone_number_regex=payload.phone_regex,
                postal_code_regex=payload.postal_code_regex,
                min_age_for_drivers=payload.min_age_for_drivers,
                min_age_for_customers=payload.min_age_for_customers,
                max_age_for_drivers=payload.max_age_for_drivers,
                max_age_for_customers=payload.max_age_for_customers,
                min_age_for_system_users=payload.min_age_for_system_users,
                max_age_for_system_users=payload.max_age_for_system_users,
                created_by=created_by,
                is_default=payload.is_default if payload.is_default else False,

        )
        db.add(country_model)
        await db.commit()
        await db.refresh(country_model)
        return CountrySchema.model_validate(country_model)
    except Exception as e:
        await db.rollback()
        return None

async def async_get_all_countries(db:AsyncSession) -> list[CountrySchema]:
    """Asynchronously fetch all countries as a list of CountrySchema."""
    result = await db.execute(select(CountryModel))
    country_models = result.scalars().all()
    country_schemas = []
    for c_model in country_models:
        try:
            country_schema = CountrySchema.model_validate(c_model)
            country_schemas.append(country_schema)
        except ValidationError:
            continue
    return country_schemas

async def async_delete_country(country_id: str, db: AsyncSession) -> tuple[bool, Optional[str]]:
    """Asynchronously delete a country from the database."""
    result = await db.execute(select(CountryModel).filter(CountryModel.id == country_id))
    country_model = result.scalars().first()
    if not country_model:
        return False, "Country not found or already disabled"
    if country_model.created_by == RoleEnum.system:
        return False, "System-created countries cannot be deleted"
    try:
        if country_model.is_default:
            return False, "Default country cannot be deleted. Please set another country as default before deleting this country."
        if country_model.is_serviceable == False:
            return False, "Country is already disabled"
        country_model.is_serviceable = False # Soft delete by marking as not serviceable
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)
    
async def async_update_country(payload:CountryUpdateSchema, db:AsyncSession) -> tuple[Optional[CountrySchema], Optional[str]]:
    """Asynchronously update an existing country in the database."""
    if not payload.id:
        return None, "Country ID is required for update"
    result = await db.execute(select(CountryModel).filter(CountryModel.id == payload.id))
    country_model = result.scalars().first()
    if not country_model:
        return None, "Country not found or already disabled"
    if country_model.created_by == RoleEnum.system:
        return None, "System-created countries cannot be updated"
    try:
        for field, value in payload.model_dump(exclude_unset=True, exclude={"id"}).items():
            setattr(country_model, field, value)

        await db.commit()
        await db.refresh(country_model)
        return CountrySchema.model_validate(country_model), None
    except Exception as e:
        await db.rollback()
        return None, str(e)
    

async def async_add_state(payload: StateSchema, db: AsyncSession, created_by: RoleEnum=RoleEnum.system) -> StateSchema:
    """Asynchronously add a new state to the system configuration."""
    try:
        # Fetch country model
        result = await db.execute(select(CountryModel).filter(CountryModel.country_code == payload.country_code.upper()))
        country_model = result.scalars().first()
        if not country_model:
            raise CabboException(f"Country with code {payload.country_code} not found.", status_code=404)

        state_model = StateModel(
            state_name=payload.state_name,
            state_code=payload.state_code.upper(),
            country_id=country_model.id,
            created_by=created_by
        )
        db.add(state_model)
        await db.commit()
        await db.refresh(state_model)
        return StateSchema.model_validate(state_model)
    except Exception as e:
        await db.rollback()
        return None
    
async def async_get_all_states(db: AsyncSession) -> list[StateSchema]:
    """Asynchronously fetch all states as a list of StateSchema."""
    result = await db.execute(select(StateModel))
    state_models = result.scalars().all()
    state_schemas = []
    for s_model in state_models:
        try:
            state_schema = StateSchema.model_validate(s_model)
            state_schemas.append(state_schema)
        except ValidationError:
            continue
    return state_schemas

async def async_delete_state(state_id: str, db: AsyncSession) -> tuple[bool, Optional[str]]:
    """Asynchronously delete a state from the database."""
    result = await db.execute(select(StateModel).filter(StateModel.id == state_id))
    state_model = result.scalars().first()
    if not state_model:
        return False, "State not found or already disabled"
    if state_model.created_by == RoleEnum.system:
        return False, "System-created states cannot be deleted"
    try:
        state_model.is_serviceable = False # Soft delete by marking as not serviceable
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)
    
async def async_update_state(payload: StateUpdateSchema, db: AsyncSession) -> tuple[Optional[StateSchema], Optional[str]]:
    """Asynchronously update an existing state in the database."""
    if not payload.id:
        return None, "State ID is required for update"
    result = await db.execute(select(StateModel).filter(StateModel.id == payload.id))
    state_model = result.scalars().first()
    if not state_model:
        return None, "State not found or already disabled"
    if state_model.created_by == RoleEnum.system:
        return None, "System-created states cannot be updated"
    try:
        for field, value in payload.model_dump(exclude_unset=True, exclude={"id","country_id"}).items():
            setattr(state_model, field, value)

        await db.commit()
        await db.refresh(state_model)
        return StateSchema.model_validate(state_model), None
    except Exception as e:
        await db.rollback()
        return None, str(e)

async def async_add_region(payload: RegionSchema, db: AsyncSession, created_by: RoleEnum=RoleEnum.system) -> RegionSchema:
    """Asynchronously add a new region to the system configuration."""
    try:
        # Fetch country and state models
        result = await db.execute(select(CountryModel).filter((CountryModel.country_code == payload.country_code.upper()) | (CountryModel.id == payload.country_id)))
        country_model = result.scalars().first()
        if not country_model:
            raise CabboException(f"Country with code {payload.country_code} not found.", status_code=404)

        result = await db.execute(select(StateModel).filter((StateModel.state_code == payload.state_code.upper() | StateModel.id == payload.state_id)
                                                            , StateModel.country_id == country_model.id))
        state_model = result.scalars().first()
        if not state_model:
            raise CabboException(f"State with code {payload.state_code or payload.state_id} not found in country {payload.country_code or payload.country_id}.", status_code=404)

        region_model = RegionModel(
            region_name=payload.region_name,
            region_code=payload.region_code.upper(),
            alt_region_names=([] if not payload.alt_region_names or len(payload.alt_region_names) == 0 else json.dumps(payload.alt_region_names)),
            alt_region_codes=([] if not payload.alt_region_codes or len(payload.alt_region_codes) == 0 else json.dumps(payload.alt_region_codes)),
            state_id=state_model.id,
            country_id=country_model.id,
            trip_types=([] if not payload.trip_types or len(payload.trip_types) == 0 else json.dumps(payload.trip_types)),
            fuel_types=([] if not payload.fuel_types or len(payload.fuel_types) == 0 else json.dumps(payload.fuel_types)),
            car_types=([] if not payload.car_types or len(payload.car_types) == 0 else json.dumps(payload.car_types)),
            airport_locations=([] if not payload.airport_locations or len(payload.airport_locations) == 0 else json.dumps(payload.airport_locations)),
            created_by=created_by

        )
        db.add(region_model)
        await db.commit()
        await db.refresh(region_model)
        return RegionSchema.model_validate(region_model)
    except Exception as e:
        await db.rollback()
        raise CabboException(f"Failed to add region: {str(e)}", status_code=500)

async def async_get_all_regions(db: AsyncSession) -> list[RegionSchema]:
    """Asynchronously fetch all regions as a list of RegionSchema."""
    result = await db.execute(select(RegionModel))
    region_models = result.scalars().all()
    region_schemas = []
    for r_model in region_models:
        try:
            region_schema = RegionSchema(
                id=r_model.id,
                region_name=r_model.region_name,
                region_code=r_model.region_code,
                alt_region_names=(
                    json.loads(r_model.alt_region_names)
                    if r_model.alt_region_names
                    else None
                ),
                state_id=r_model.state_id,
                country_id=r_model.country_id,
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

async def async_delete_region(region_id: str, db: AsyncSession) -> tuple[bool, Optional[str]]:
    """Asynchronously delete a region from the database."""
    result = await db.execute(select(RegionModel).filter(RegionModel.id == region_id))
    region_model = result.scalars().first()
    if not region_model:
        return False, "Region not found or already disabled"
    if region_model.created_by == RoleEnum.system:
        return False, "System-created regions cannot be deleted"
    try:
        region_model.is_serviceable = False # Soft delete by marking as not serviceable
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)

async def async_update_region(payload: RegionUpdate, db: AsyncSession) -> tuple[Optional[RegionSchema], Optional[str]]:
    """Asynchronously update an existing region in the database."""
    if not payload.id:
        return None, "Region ID is required for update"
    result = await db.execute(select(RegionModel).filter(RegionModel.id == payload.id))
    region_model = result.scalars().first()
    if not region_model:
        return None, "Region not found or already disabled"
    if region_model.created_by == RoleEnum.system:
        return None, "System-created regions cannot be updated"
    try:
        for field, value in payload.model_dump(exclude_unset=True, exclude={"id","state_id", "country_id"}).items():
            setattr(region_model, field, value)

        await db.commit()
        await db.refresh(region_model)
        return RegionSchema.model_validate(region_model), None
    except Exception as e:
        await db.rollback()
        return None, str(e)

async def async_set_default_country(country_id: str, db: AsyncSession) -> tuple[bool, Optional[str]]:
    """Asynchronously set a country as the default country in the database.""" 
    result = await db.execute(select(CountryModel).filter(CountryModel.id == country_id)) 
    country_model = result.scalars().first() 
    if not country_model: 
        return False, "Country not found" 
    if country_model.is_default: 
        return False, "Country is already set as default"
    try: 
        # Unset default flag from all other countries 
        await db.execute(update(CountryModel).where(CountryModel.is_default == True).values(is_default=False)) 
        # Set default flag for the specified country 
        country_model.is_default = True
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)

async def async_activate_country(country_id: str, db: AsyncSession) -> tuple[bool, Optional[str]]:
    """Asynchronously activate a country in the database."""
    result = await db.execute(select(CountryModel).filter(CountryModel.id == country_id))
    country_model = result.scalars().first()
    if not country_model:
        return False, "Country not found"
    try:
        if country_model.is_serviceable:
            return False, "Country is already active"
        country_model.is_serviceable = True
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)
    

async def async_activate_state(state_id: str, db: AsyncSession) -> tuple[bool, Optional[str]]:
    """Asynchronously activate a state in the database."""
    result = await db.execute(select(StateModel).filter(StateModel.id == state_id))
    state_model = result.scalars().first()
    if not state_model:
        return False, "State not found"
    try:
        if state_model.is_serviceable:
            return False, "State is already active"
        state_model.is_serviceable = True
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)

  
async def async_activate_region(region_id: str, db: AsyncSession) -> tuple[bool, Optional[str]]:
    """Asynchronously activate a region in the database."""
    result = await db.execute(select(RegionModel).filter(RegionModel.id == region_id))
    region_model = result.scalars().first()
    if not region_model:
        return False, "Region not found"
    try:
        if region_model.is_serviceable:
            return False, "Region is already active"
        region_model.is_serviceable = True
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)

 
    """Asynchronously deactivate a region in the database."""
    result = await db.execute(select(RegionModel).filter(RegionModel.id == region_id))
    region_model = result.scalars().first()
    if not region_model:
        return False, "Region not found"
    try:
        if not region_model.is_serviceable:
            return False, "Region is already inactive"
        region_model.is_serviceable = False
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)