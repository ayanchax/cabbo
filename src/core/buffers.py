from models.trip.trip_enums import TripTypeEnum


#Conceptual rule of trip start (ongoing) buffer times. These are the buffers that are used to determine if a trip can be started or not. The buffers are based on the trip type and are used to ensure that the trip is started in a timely manner and the customer is not left waiting for too long. The buffer times can be adjusted based on the trip type and business requirements.:
# A trip can enter its start flow from:
# scheduled_start - TRIP_START_EARLY_BUFFER
# through:
# max(expected_end_datetime(if provided), scheduled_start + TRIP_START_LATE_BUFFER)

#Conceptual rule of driver assignment on trip start (ongoing) buffer times. These are the buffers that are used to determine if a driver can be assigned to a trip or not. The buffers are based on the trip type and are used to ensure that the driver is assigned in a timely manner and the customer is not left waiting for too long. The buffer times can be adjusted based on the trip type and business requirements.:
# A driver can be assigned to a trip if the current time is within the following window:
# max(expected_end_datetime(if provided), scheduled_start + TRIP_START_LATE_BUFFER_MINUTES)

TRIP_START_EARLY_BUFFER_MINUTES = {
    TripTypeEnum.airport_drop: 60,
    TripTypeEnum.airport_pickup: 60,
    TripTypeEnum.local: 30,
    TripTypeEnum.outstation: 60,
}

TRIP_START_LATE_BUFFER_MINUTES = {
    TripTypeEnum.airport_drop: 120,
    TripTypeEnum.airport_pickup: 180,
    TripTypeEnum.local: 60,
    TripTypeEnum.outstation: 120,
}