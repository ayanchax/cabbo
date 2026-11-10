"""Stable refund reason codes shared by provider adapters and recovery workflows.

Values are persisted in refunds.last_error. Keep them unchanged when renaming
Python constants so existing records, logs, and admin filters remain compatible.
"""

# Provider validation and financial review.
PROVIDER_REFUND_MISMATCH = "provider_refund_mismatch"
UNKNOWN_PROVIDER_REFUND_STATUS = "unknown_provider_refund_status"
MISSING_PAYMENT_ID = "missing_payment_id"
INVALID_REFUND_AMOUNT = "invalid_refund_amount"
PAYMENT_IDENTITY_OR_AMOUNT_MISMATCH = "payment_identity_or_amount_mismatch"
REFUND_HISTORY_TOO_LARGE = "refund_history_too_large"
MULTIPLE_PROVIDER_REFUNDS = "multiple_provider_refunds"
PAYMENT_NOT_CAPTURED_YET = "payment_not_captured_yet"
PAYMENT_NOT_REFUNDABLE = "payment_not_refundable"
UNMATCHED_REFUNDED_AMOUNT = "unmatched_refunded_amount"
INSUFFICIENT_PROVIDER_BALANCE = "insufficient_provider_balance"
PROVIDER_SUBMISSION_REQUIRES_REVIEW = "provider_submission_requires_review"
PROVIDER_SUBMISSION_UNAVAILABLE = "provider_submission_unavailable"
UNSUPPORTED_REFUND_PROVIDER = "unsupported_refund_provider"
PROVIDER_REFUND_FAILED = "provider_refund_failed"
PROVIDER_STATUS_UNAVAILABLE = "provider_status_unavailable"

# Booking eligibility and cancellation-policy review.
MISSING_OR_NOT_CANCELLED_TRIP = "missing_or_not_cancelled_trip"
REFUND_ELIGIBILITY_UNRESOLVED = "refund_eligibility_unresolved"
UNSUPPORTED_REFUND_POLICY = "unsupported_refund_policy"
MISSING_CANCELLATION_POLICY = "missing_cancellation_policy"
MISSING_TRIP_START_TIME = "missing_trip_start_time"
MISSING_CANCELLATION_REASON = "missing_cancellation_reason"

# Notification work is tracked independently of the financial outcome.
MISSING_NOTIFICATION_RECIPIENT = "missing_notification_recipient"
CANCELLATION_NOTIFICATION_NOT_DELIVERED = "cancellation_notification_not_delivered"
PROCESSED_NOTIFICATION_NOT_DELIVERED = "processed_notification_not_delivered"
NOTIFICATION_DELIVERY_FAILED = "notification_delivery_failed"
