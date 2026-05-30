# BRMS — Bank Reconciliation Management System

A full-featured Django web application for automated bank reconciliation,
built to spec from the BRMS Functional Specification Document v1.0.

## Features
- Role-based access control (Admin, Officer, Manager, Auditor, Executive)
- Reconciliation session lifecycle management (Draft → Processing → Pending Review → Approved)
- File upload and CSV/Excel transaction extraction
- Automatic reconciliation engine with 3 matching rules (Exact, Amount+Date, Fuzzy Reference)
- Exception management with categorisation and resolution workflow
- Finance Manager approval workflow with comments
- Full immutable audit trail
- Dashboard with KPIs and monthly trends

## Quick Start

```bash
# 1. Install dependencies
pip install django pillow python-dateutil

# 2. Apply migrations
python manage.py migrate

# 3. (Optional) Load demo data
python seed.py

# 4. Run the development server
python manage.py runserver
```

Open http://127.0.0.1:8000

## Demo Credentials

| Username   | Password   | Role                    |
|------------|------------|-------------------------|
| admin      | admin1234  | System Administrator    |
| j.mensah   | pass1234   | Reconciliation Officer  |
| k.boateng  | pass1234   | Finance Manager         |
| a.asante   | pass1234   | Internal Auditor        |
| d.appiah   | pass1234   | Executive User          |

## Upload Format (CSV)
The system accepts CSV files with these columns (flexible header names):
```
date, reference, narration, debit, credit, currency
```
Example:
```
date,reference,narration,debit,credit,currency
2024-04-01,TXN-001,Vendor payment,1500.00,,GHS
2024-04-02,TXN-002,Customer receipt,,2000.00,GHS
```

## Project Structure
```
brms/           Django project config
accounts/       User management & auth
reconciliation/ Core models, engine, views
dashboard/      Analytics dashboard
templates/      All HTML templates
static/css/     BRMS design system CSS
```
