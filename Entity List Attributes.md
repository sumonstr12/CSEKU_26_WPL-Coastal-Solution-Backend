# Entity List, Attributes, and Relationships

Based on the SRS, the system's core data entities include User, Role, Citizen Profile, Volunteer/Responder Profile, Incident Report, Incident Category, Incident Location, Evidence Attachment, Verification Record, Response Assignment, Response Action, Alert, Notification, Shelter/Resource, Administrative Area, and Audit Log. 

---

## 1. User

**Attributes:**

* `id` (PK)
* `full_name`
* `email`
* `phone`
* `password`
* `is_active`
* `is_verified`
* `created_at`
* `updated_at`

---

## 2. Role

**Attributes:**

* `id` (PK)
* `name`
* `description`

**Examples:**

* Citizen
* Volunteer
* Responder
* Local Authority
* Disaster Management Officer
* System Administrator

---

## 3. Citizen Profile

**Attributes:**

* `id` (PK)
* `user_id` (FK)
* `address`
* `administrative_area_id` (FK)
* `created_at`
* `updated_at`

---

## 4. Volunteer / Responder Profile

**Attributes:**

* `id` (PK)
* `user_id` (FK)
* `responder_type`
* `organization`
* `availability_status`
* `administrative_area_id` (FK)
* `created_at`
* `updated_at`

---

## 5. Incident Category

**Attributes:**

* `id` (PK)
* `name`
* `description`
* `is_active`
* `created_at`

**Examples:**

* Cyclone
* Storm Surge
* Tidal Flooding
* River Flooding
* Coastal Erosion
* Fire
* Infrastructure Damage
* Missing Person
* Other Emergency

---

## 6. Incident Report

**Attributes:**

* `id` (PK)
* `reporter_id` (FK → User)
* `category_id` (FK → Incident Category)
* `location_id` (FK → Incident Location)
* `title`
* `description`
* `severity`
* `priority`
* `affected_people_count`
* `incident_datetime`
* `status`
* `created_at`
* `updated_at`

**Status examples:**

* Submitted
* Under Review
* Verified
* Unverified
* Prioritized
* Assigned
* In Progress
* Resolved
* Closed
* Rejected
* Duplicate

---

## 7. Incident Location

**Attributes:**

* `id` (PK)
* `latitude`
* `longitude`
* `address`
* `location_source`
* `administrative_area_id` (FK)

**Location source:**

* GPS
* Manual

---

## 8. Administrative Area

**Attributes:**

* `id` (PK)
* `name`
* `area_type`
* `parent_id` (Self FK)

**Area types:**

* Division
* District
* Upazila
* Union

This entity can represent the geographical hierarchy:

```text
Division
   │
   └── District
          │
          └── Upazila
                 │
                 └── Union
```

---

## 9. Evidence Attachment

**Attributes:**

* `id` (PK)
* `incident_id` (FK)
* `uploaded_by` (FK → User)
* `file`
* `file_type`
* `file_size`
* `created_at`

---

## 10. Verification Record

**Attributes:**

* `id` (PK)
* `incident_id` (FK)
* `verified_by` (FK → User)
* `verification_status`
* `comment`
* `verified_at`

**Verification status:**

* Verified
* Unverified
* Rejected
* Duplicate

---

## 11. Response Assignment

**Attributes:**

* `id` (PK)
* `incident_id` (FK)
* `assigned_to` (FK → User)
* `assigned_by` (FK → User)
* `assigned_at`
* `status`

**Assignment status:**

* Assigned
* Accepted
* Declined
* Completed

---

## 12. Response Action

**Attributes:**

* `id` (PK)
* `incident_id` (FK)
* `responder_id` (FK → User)
* `action_type`
* `description`
* `action_datetime`
* `outcome`
* `created_at`

**Action types:**

* Rescue
* Medical Assistance
* Food Supply
* Evacuation
* Shelter Support
* Assessment

---

## 13. Help / Assistance Request

**Attributes:**

* `id` (PK)
* `incident_id` (FK)
* `requested_by` (FK → User)
* `request_type`
* `description`
* `people_count`
* `status`
* `created_at`
* `resolved_at`

**Request types:**

* Rescue
* Medical Assistance
* Food
* Water
* Shelter
* Evacuation
* Other

---

## 14. Shelter

**Attributes:**

* `id` (PK)
* `name`
* `location_id` (FK)
* `administrative_area_id` (FK)
* `capacity`
* `current_occupancy`
* `contact_number`
* `status`

**Status:**

* Open
* Full
* Closed

---

## 15. Resource

**Attributes:**

* `id` (PK)
* `name`
* `resource_type`
* `quantity`
* `unit`
* `location_id` (FK)
* `availability_status`

**Examples:**

* Food
* Water
* Medicine
* Boat
* Ambulance
* Rescue Equipment

---

## 16. Alert

**Attributes:**

* `id` (PK)
* `created_by` (FK → User)
* `title`
* `message`
* `alert_type`
* `severity`
* `administrative_area_id` (FK)
* `starts_at`
* `expires_at`
* `status`
* `created_at`

---

## 17. Notification

**Attributes:**

* `id` (PK)
* `user_id` (FK)
* `title`
* `message`
* `notification_type`
* `related_incident_id` (FK, nullable)
* `related_alert_id` (FK, nullable)
* `is_read`
* `created_at`

---

## 18. Audit Log

**Attributes:**

* `id` (PK)
* `user_id` (FK)
* `action`
* `entity_type`
* `entity_id`
* `old_value`
* `new_value`
* `ip_address`
* `created_at`

---

# Relationship Diagram

```text
                              ┌──────────┐
                              │   Role   │
                              └────┬─────┘
                                   │ 1
                                   │
                                   │ M
                              ┌────▼─────┐
                              │   User   │
                              └────┬─────┘
                   ┌───────────────┼─────────────────┐
                   │               │                 │
                  1:1             1:M               1:M
                   │               │                 │
        ┌──────────▼──────┐   ┌────▼─────┐    ┌──────▼─────┐
        │ Citizen Profile │   │ Audit Log │    │Notification│
        └─────────────────┘   └──────────┘    └────────────┘
                   │
                   │ 1:M
                   │
            ┌──────▼────────┐
            │Incident Report│
            └──────┬────────┘
       ┌───────────┼───────────────┬──────────────────┐
       │           │               │                  │
      M:1         M:1             1:M                1:M
       │           │               │                  │
┌──────▼─────┐ ┌───▼────────┐ ┌────▼──────────┐ ┌────▼───────────┐
│  Category  │ │  Location  │ │   Evidence    │ │ Verification   │
└────────────┘ └─────┬──────┘ │  Attachment   │ │    Record      │
                     │        └───────────────┘ └────────────────┘
                    M:1
                     │
          ┌──────────▼──────────┐
          │ Administrative Area │
          └──────────┬──────────┘
                     │
          ┌──────────┼───────────────┐
          │          │               │
         1:M        1:M             1:M
          │          │               │
     ┌────▼────┐ ┌───▼────┐    ┌────▼─────┐
     │ Shelter │ │ Alert  │    │Responder │
     └─────────┘ └───┬────┘    │ Profile  │
                     │         └────┬─────┘
                     │              │
                     │              │
                     ▼              ▼
                Notification   Response Assignment
                                      │
                                      │ M:1
                                      │
                               Incident Report
                                      │
                   ┌──────────────────┼─────────────────┐
                   │                  │                 │
                  1:M                1:M               1:M
                   │                  │                 │
          ┌────────▼───────┐ ┌────────▼──────┐ ┌───────▼─────────┐
          │Response Action │ │Help Request   │ │ Resource        │
          └────────────────┘ └───────────────┘ └─────────────────┘
```

This structure covers the main workflow defined in your SRS:

**User → Incident Report → Verification → Assignment → Response Action → Resolution**, along with **Alerts, Notifications, Location Management, Resources, and Audit Logging**.

