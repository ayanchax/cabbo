from typing import List, Optional
from models.geography.serviceable_area_orm import ServiceableAreaModel
from models.geography.serviceable_area_schema import ServiceableAreaSchema
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_orm import TripTypeMaster
from models.trip.trip_schema import TripSearchRequest
from sqlalchemy.orm import Session

def get_serviceable_area_by_trip_type(
    trip_type: TripTypeEnum, db: Session
) -> Optional[List[ServiceableAreaSchema]]:
    """
    Given a TripTypeEnum, return the corresponding ServiceableAreaSchema
    if the trip type is supported in the serviceable area.
    """
    # Query the serviceable area config for this trip type
    service_area = db.query(ServiceableAreaModel).join(
        TripTypeMaster, ServiceableAreaModel.trip_type_id == TripTypeMaster.id
    ).filter(ServiceableAreaModel.trip_type_id == TripTypeMaster.id, TripTypeMaster.trip_type==trip_type).first()
    
    if not service_area:
        return None
    service_areas:List[ServiceableAreaSchema]=[]
    for area in service_area.serviceable_areas:
        try:
            area = ServiceableAreaSchema.model_validate(area)
            service_areas.append(area)
        except Exception as e:
            # Handle or log the validation error if needed
            continue
    return service_areas