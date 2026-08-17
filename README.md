# Coastal Disaster Reporting & Crisis Management System — Backend

Backend API for the **Citizen Participation-Based Coastal Disaster Reporting & Crisis Management System**, built to support disaster reporting, verification, response coordination, and alerting for coastal communities in Bangladesh.

## Overview

This backend powers a citizen-participation platform where citizens report hazards/disasters, authorities verify and triage reports, responders coordinate action, and verified alerts are broadcast to affected areas. It complements (not replaces) official agencies such as BMD, DDM, local administration, and NGOs.

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django + Django REST Framework |
| Database | PostgreSQL + PostGIS (geospatial data) |
| Cache / Queue | Redis |
| Background Jobs | Celery |
| File Storage | S3-compatible object storage |
| Auth | Token/JWT-based, Role-Based Access Control (RBAC) |
| API Docs | OpenAPI / Swagger |
| Maps/GIS | OpenStreetMap-based / approved GIS provider |

## Core Features

- **Authentication & RBAC** — Citizen, Volunteer, Responder, Local Authority, Disaster Management Officer, and Admin roles with server-side enforced permissions.
- **Incident Reporting API** — Create/read/update incident reports with category, severity, description, timestamp, GPS/manual location, and evidence attachments.
- **Verification & Triage** — Mark reports Verified / Unverified / Rejected / Duplicate; assign priority (Critical/High/Medium/Low).
- **Crisis Management** — Assign incidents to responders/teams, track response actions, resource records (shelter, rescue, medical, food/water), and escalation.
- **Alerts & Notifications** — Publish verified, location-targeted alerts via in-app, SMS, email, or push (clearly distinguished from unverified citizen reports).
- **Dashboard & Analytics APIs** — Active incidents, severity/geographic distribution, response status, historical stats, filterable/exportable reports.
- **Admin & Audit** — User/role/category management, notification templates, full audit logging, backup & recovery support.
- **Geographic Filtering** — Filter/query incidents by location, category, severity, priority, status, and administrative unit (union/upazila/district).

## Core Data Entities

`User`, `Role`, `CitizenProfile`, `ResponderProfile`, `IncidentReport`, `IncidentCategory`, `IncidentLocation`, `EvidenceAttachment`, `VerificationRecord`, `ResponseAssignment`, `ResponseAction`, `Alert`, `Notification`, `ShelterResource`, `AdministrativeArea`

May be modified in the future based on requirements.

## Incident Status Flow

```
Submitted → Under Review → Verified/Unverified → Prioritized → Assigned
    → In Progress → Resolved → Closed
    (Rejected / Duplicate as terminal branches from review)
```

## Security

- HTTPS-only in production
- Passwords hashed (never stored in plaintext)
- Rate limiting(optional), input validation on sensitive endpoints
- Validated file uploads (type, size, security scan)
- Secrets managed via environment variables, never committed to source

## Getting Started

### Prerequisites
- Python 3.10+
- PostgreSQL with PostGIS extension
- Redis

### Installation
```bash
git clone https://github.com/sumonstr12/Coastal-Solution-Backend.git
cd Coastal-Solution-Backend
```
Activate Virtual Enviroment:
for linux-
```bash
python3 -m venv venv
source venv/bin/activate
```
for windows-
```bash
python -m venv venv
venv/Scripts/activate
```
```bash
pip install -r requirements.txt
```

### Environment Variables
Create a `.env` file:
```
DEBUG=True
SECRET_KEY=your-secret-key
```
For security reasons,the Secret Key is not included in this document.Please contact me directly for the secret key.

### Run Migrations & Start Server
```bash
python manage.py migrate
python manage.py runserver
```


## API Documentation

Once running, API docs are available at:
```
/api/docs/        # Swagger UI
/api/schema/       # OpenAPI schema
```


## Future Enhancements

- AI-assisted duplicate/false-report detection
- Automated incident prioritization
- Integration with official weather/disaster alert APIs
- USSD/SMS-based reporting

## Acknowledgement

Built as part of an academic project — Discipline of CSE, Khulna University.
