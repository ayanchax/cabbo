from datetime import timedelta
CUSTOMER_SESSION_COOKIE_NAME = "__Host-cabbo_cust_session"
SYSTEM_USER_SESSION_COOKIE_NAME = "__Host-cabbo_sysuser_session"
CUSTOMER_SESSION_LIFETIME = timedelta(
    days=30
)  # Absolute expiry at 30 days for customer, because we do not want to log off customer frequently by setting a lower session lifetime, because we want customers to use the app rather than playing the auth game too often. This gains customer trust and acquaintance with the app and also saves some amount as we avoid sending frequent SMS OTPS to customer.
SYSTEM_USER_SESSION_LIFETIME = timedelta(
    days=1
)  # Absolute expiry at 1 days for SYSTEM users.
