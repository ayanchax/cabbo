# Admin route allowed for cust_admin and super_admin for performing admin level tasks such as listing all customers, activate/deactivate customers, view customer trips
# Passenger management is done by customer themselves via customer routes, passenger has nothing to do with admin.

# - Admin based customer management endpoints, only super_admin, customer_admin can do.
#     See all customers in system by various params:
#        - all, active, inactive, email_verified, not_email_verified, phone_verified, not_phone_verified 
    
#     See a customer profile by customer_id
#     Activate a customer
#     Deactivate a customer
#     Suspend account - for disputed accounts.