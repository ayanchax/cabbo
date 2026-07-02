# Legal Pages Rationale

This document records the V1 decision for Cabbo legal, policy, and support
content.

## Decision

Cabbo should expose legal and support pages in the customer frontend, but the
content should be owned by the backend.

For V1, the backend can maintain the content as versioned Markdown or JSON
files in the backend repository. A database-backed legal-content management
system is not required for launch.

The frontend should only render the latest active content returned by the
backend and link to it from the customer profile and other relevant surfaces.

## Why Backend-Owned Content

Legal and policy content is business-critical. It should not be coupled to a
frontend deployment when the actual policy logic lives in backend systems such
as booking, fares, cancellation, refunds, support routing, and payments.

Backend-owned content allows Cabbo to:

- keep legal wording aligned with backend policy logic
- version content with effective dates
- later record which policy version a customer accepted
- update content without changing frontend presentation code
- migrate from file-based content to database-backed content later without
  changing the frontend contract much

## V1 Content Storage

Use backend-managed files for V1.

Recommended shape:

```json
{
  "slug": "terms-of-service",
  "title": "Terms of Service",
  "version": "2026.07.01",
  "effective_date": "2026-07-01",
  "content_format": "markdown",
  "content": "...",
  "requires_acceptance": true,
  "last_updated": "2026-07-01T00:00:00Z"
}
```

Recommended backend endpoints:

```txt
GET /api/v1/legal/pages
GET /api/v1/legal/pages/{slug}
```

The list endpoint should return lightweight metadata for navigation. The detail
endpoint should return the page content.

## V1 Frontend Scope

The customer frontend should:

- show legal/support links from the customer profile page
- render legal pages from backend-provided Markdown/content
- show page title, version, effective date, and last updated date where useful
- avoid hardcoding final legal copy in frontend components
- handle loading, empty, and error states gracefully

The frontend should not:

- own the canonical policy wording
- implement a legal-content editor
- expose draft or inactive legal versions
- decide refund or cancellation eligibility from policy text

Backend policy logic remains the source of truth for actual fare, refund,
cancellation, support, and payment outcomes.

## Required V1 Pages

### Help And Support

Purpose: give the customer a direct way to contact Cabbo.

Content should be short and action-focused:

- call support
- WhatsApp support
- mention that booking ID helps support resolve faster
- clarify support availability if Cabbo has defined hours

Trip-specific support actions should still live on booking-detail pages. The
profile link is a general support entry point.

### Terms Of Service

Purpose: explain the customer agreement for using Cabbo.

Should cover:

- account creation and customer responsibilities
- booking rules
- scheduled-trip nature of Cabbo V1
- payments, advance, balance, and pay-to-driver amounts
- cancellation and refund references
- customer no-show or misuse behavior
- driver assignment and operational limitations
- disputes and support escalation
- limitation of liability, where legally appropriate
- changes to terms and versioning

### Privacy Policy

Purpose: explain what personal data Cabbo collects and why.

Should cover:

- phone number, name, optional email, profile picture
- pickup/drop locations and trip details
- payment and refund metadata received from payment providers
- support interactions and special requests
- device/browser data needed for security and reliability
- why the data is used
- who data may be shared with, such as drivers, payment providers, support
  tools, and legally required recipients
- retention and deletion principles
- security practices
- customer rights and grievance/contact route

Cabbo should avoid collecting profile fields that are not needed for V1, such
as DOB, gender, and emergency contact, unless a future workflow justifies them.

### Cancellation And Refund Policy

Purpose: make cancellation and refund outcomes understandable before and after
booking.

Should cover:

- cancellation windows by trip type or region, if applicable
- full versus partial refund conditions
- customer no-show handling
- Cabbo operational-failure refunds
- payment-source refund behavior
- expected settlement timelines after refund initiation
- failed or delayed refund support path

The displayed text must stay aligned with backend policy configuration. The
frontend should never calculate refund eligibility from this text.

### Fare And Charges Policy

Purpose: explain how Cabbo fares and extra charges work.

Should cover:

- base fare
- platform/convenience fee
- advance payment and balance payment
- tolls, parking, airport charges, permits, driver allowance, night charges
- outstation included days and included mileage
- overage charges
- pay-to-driver items
- add-ons where applicable
- why some charges are included in fare and others may be payable directly to
  the driver

This page should support the fare disclaimers already shown in booking flows.

### Safety, Contact, And Grievance

Purpose: provide customer safety guidance and official contact/escalation
information.

Should cover:

- Cabbo support phone and WhatsApp
- grievance/contact email
- expected response path
- safe pickup and trip conduct guidance
- driver/cab verification guidance where applicable
- emergency disclaimer: in immediate danger, contact local emergency services

This page can be merged with Help and Support for V1 if Cabbo wants fewer
links, but the grievance/contact information must remain easy to find.

## Profile Link Placement

Legal and support links should appear on the customer profile page, below the
account information and above or near logout.

The profile page is the right place because these links are account-level
references. Trip-specific support remains on booking-detail pages, where the
booking ID and trip context are already available.

## Writing Style

Cabbo legal pages should be:

- clear and practical
- written in plain English
- structured around customer questions
- specific to Cabbo's scheduled cab-booking model
- consistent with backend behavior
- reviewed before production launch

The content should not copy wording from other cab apps. Other apps can inform
structure and customer expectations, but Cabbo's wording must reflect Cabbo's
own policies, operations, and legal review.

## Future Upgrade Path

After V1, Cabbo can move legal content from backend files into a database table
if needed.

Possible future schema:

- slug
- title
- version
- status: draft, active, archived
- content_format
- content
- effective_date
- published_at
- requires_acceptance
- created_by
- approved_by

Customer acceptance tracking can later store:

- customer ID
- terms version
- privacy version
- accepted timestamp
- source surface

This should not block V1 unless legal review or changes in legal files requires explicit acceptance
versioning before v1 launch.
