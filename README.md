# Blood Bank Management System (BBMS)

A web-based healthcare software system designed to coordinate blood donations, track live blood bank inventory with shelf-life expiry management, and streamline blood requests between donors, patients, and hospital staff.

Developed as a **Software Engineering Mini-Project** for the Department of Computer Science and Engineering, **PES University**.

---

## Team Members & Project Roles

| Team Member | SRN | Role & Primary Contributions |
| :--- | :--- | :--- |
| **Qamar Ahmed** | `PES2UG24CS904` | Donor Profile (`BB-F-004`), Donation Review Service (`BB-F-006`), Inventory Updates (`BB-F-013`), Blood Expiry Tracking (`BB-F-018`), Universal Responsive Navigation (`BB-NF-004`) |
| **Khush Bhardwaj** | `PES2UG24CS226` | Blood Request Submission (`BB-F-009`), User Management & Account Deactivation (`BB-F-017`), Test Coverage |
| **KOUSHIK C** | `PES2UG24CS232` | Blood Request Review (`BB-F-010`), Inventory Adjustments (`BB-F-012`), Accessibility (`BB-NF-004`), Data Integrity (`BB-NF-006`) |
| **Hemaksh Breja** | `PES2UG24CS191` | Blood Availability & Compatibility Matrix (`BB-F-011`), Donation History & Certificates (`BB-F-007`), Request History & Pickup Slips (`BB-F-015`), Patient Profile (`BB-F-008`), Performance (`BB-NF-001`), Security Lockout (`BB-NF-003`) |

---

## Key Features & Module Overview

The system is organized into four main functional areas based on our Software Requirements Specification (SRS) and System Architecture Document (SAD):

### 1. Donor Portal
- **Donor Profile Management (`BB-F-004`):** Registration of donor blood type, age validation (18–65 eligibility window), emergency contact numbers, and residential address.
- **Donation Logging (`BB-F-005`):** Submission of donation records with unit counts and donation dates.
- **Donation History & Certificates (`BB-F-007`):** Historical log of donations, automated 56-day clinical recovery countdown before next eligible donation, lifetime impact statistics, and printable donor appreciation certificates.

### 2. Patient & Request Portal
- **Patient Profile Management (`BB-F-008`):** Medical profile tracking blood group, diagnosed condition, attending doctor, hospital name, emergency contacts, and an interactive profile completeness meter.
- **Submit Blood Request (`BB-F-009`):** Emergency and routine requests specifying needed units and required date.
- **Request History & Hospital Pickup Slips (`BB-F-015`):** Status tracking (Pending, Approved, Rejected, Cancelled), urgency countdown indicators, printable hospital pickup slips for approved units, and self-service cancellation for pending requests.

### 3. Inventory & Shelf-Life Tracking
- **Live Stock Availability (`BB-F-011`):** Real-time view of available blood units across all 8 major blood groups (A+, A-, B+, B-, AB+, AB-, O+, O-).
- **Clinical Compatibility Matrix:** Interactive tool showing compatible donor and recipient blood types for emergency transfusion planning.
- **Blood Expiry Management (`BB-F-018`):** Automatic calculation of whole blood 42-day shelf-life from collection date. Dynamic tracking of the earliest expiring blood unit per blood group to support First-In, First-Out (FIFO) dispatching and minimize wastage.

### 4. Staff & Administration Dashboard
- **Donation Review Workflow (`BB-F-006`):** Dedicated staff review screen to approve or reject pending donations. Approved donations automatically increment corresponding inventory units inside an atomic transaction.
- **Request Review Workflow (`BB-F-010`):** Staff review of patient blood requests. Approvals automatically deduct available stock; requests exceeding stock are safely prevented.
- **Staff Analytics Dashboard (`BB-F-016`):** Centralized overview showing total registered users, donors, patients, pending reviews, and stock capacity utilization gauges.
- **User Access Management (`BB-F-017`):** Staff interface to search users, view attached profiles, and activate/deactivate accounts with self-deactivation and superuser protection guards.

### 5. Security & Data Integrity
- **Role-Based Access Control (`BB-SR-003`):** Granular access gates separating donors, patients, and staff members across all views and API endpoints.
- **Authentication Security (`BB-NF-003`, `BB-SR-001`):** Cryptographic password hashing (PBKDF2), password complexity validation rules (length, casing, digits), and cache-based rate limiting against brute-force login attacks (5-minute lockout after 5 consecutive failures).
- **Transactional Consistency (`BB-NF-006`):** Atomic database transactions (`@transaction.atomic`) and row-level locking (`select_for_update`) in `blood/services.py` to prevent race conditions during inventory updates.

---

## Tech Stack

- **Backend:** Python 3.12+, Django 5.2 (MVT Pattern + Domain Service Layer)
- **Database:** SQLite 3 (Development & Testing)
- **Frontend:** Semantic HTML5, CSS3 (Modern Flexbox/Grid, Responsive Mobile-Friendly Layout, Universal Role-Aware Navbar), Vanilla JavaScript
- **Version Control & CI:** Git, GitHub (feature branching, peer code reviews, pull requests)

---

## Project Structure

```text
Blood-Bank-Management-System/
├── manage.py                     # Django management script
├── requirements.txt              # Project Python dependencies
├── README.md                     # Project documentation
├── 2_SRS.pdf                     # Software Requirements Specification
├── 2_SAD.pdf                     # Software Architecture Document
├── 2_TestPlan.pdf                # Testing Plan & Traceability Matrix
│
├── config/                       # Core Django project configuration
│   ├── settings.py               # Application settings, middleware, database config
│   ├── urls.py                   # Root URL routing
│   ├── wsgi.py                   # WSGI server entry point
│   └── asgi.py                   # ASGI server entry point
│
├── blood/                        # Main BBMS application
│   ├── models.py                 # Data models (Donation, BloodRequest, BloodInventory, Profiles)
│   ├── views.py                  # HTTP view controllers & authentication logic
│   ├── services.py               # Atomic domain services (donation/request reviews, inventory)
│   ├── forms.py                  # Django Forms with validation rules
│   ├── urls.py                   # Application route definitions
│   ├── admin.py                  # Django Admin customized interfaces & bulk actions
│   ├── tests.py                  # Automated test suite (90+ unit and integration tests)
│   │
│   ├── migrations/               # Database migration history (0001 through 0008)
│   │
│   └── templates/blood/          # HTML templates
│       ├── navbar.html           # Universal role-aware navigation bar
│       ├── blood_availability.html # Inventory dashboard & compatibility matrix
│       ├── donor_profile.html    # Donor profile edit & status view
│       ├── patient_profile.html  # Patient profile with completeness meter
│       ├── donate.html           # Donation submission form
│       ├── donation_history.html # Donation records & certificates
│       ├── request_blood.html    # Blood request submission form
│       ├── request_history.html  # Blood request records & pickup slips
│       ├── manage_donations.html # Staff review page for donations
│       ├── manage_requests.html  # Staff review page for requests
│       ├── admin_dashboard.html  # Staff metrics & capacity dashboard
│       ├── user_management.html  # Staff user activation & list
│       ├── login.html            # Sign-in page with lockout warnings
│       └── register.html         # Sign-up page with live password strength meter
│
└── Team Details/                 # Student details & SRN documentation
```

---

## Local Development Setup

Follow these step-by-step instructions to get the project running locally on your machine.

### 1. Prerequisites
- **Python 3.12** or higher installed ([Download Python](https://www.python.org/downloads/))
- **Git** installed ([Download Git](https://git-scm.com/))

Verify installations:
```bash
python --version
git --version
```

---

### 2. Clone the Repository
```bash
git clone https://github.com/BBMS-Team-2/Blood-Bank-Management-System.git
cd Blood-Bank-Management-System
```

---

### 3. Create and Activate Virtual Environment

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(If PowerShell displays an execution policy error, run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`)*

**On macOS / Linux (Bash/Zsh):**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

---

### 5. Apply Database Migrations
Run the migrations to create the SQLite database tables and apply initial schemas:
```bash
python manage.py migrate
```

---

### 6. Create an Administrator / Staff Account
Create a superuser account to test administrative and staff review features:
```bash
python manage.py createsuperuser
```
Follow the prompts in the terminal to set a username, email, and password.

---

### 7. Run the Development Server
```bash
python manage.py runserver
```
Once started, open your web browser and navigate to:
**[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

---

## Testing & Quality Assurance

The codebase includes an automated test suite covering model validation, atomic service workflows, permissions, and edge cases.

### Run All Unit and Integration Tests
```bash
python manage.py test
```

### Run System Configuration Checks
Verify that settings, model definitions, and URLs contain zero errors:
```bash
python manage.py check
```

### Verify Migration Integrity
Check for unapplied model changes without creating new migration files:
```bash
python manage.py makemigrations --check --dry-run
```

---

## Evaluator Walkthrough Guide

To evaluate the different roles and features:

1. **Public / Guest:**
   - Open `http://127.0.0.1:8000/` to view real-time blood availability and the clinical compatibility matrix.
2. **Donor Persona:**
   - Register a new account at `/accounts/register/`.
   - Navigate to **Donor Profile** to set blood type and age.
   - Click **Donate Blood** to record a donation.
   - View **Donation History** to inspect the 56-day interval recovery status and view your certificate.
3. **Patient Persona:**
   - Register another user account.
   - Navigate to **Patient Profile** to fill out emergency contacts and hospital details.
   - Submit a request via **Request Blood**.
   - Check **Request History** to monitor urgency badges and print hospital pickup slips once approved.
4. **Staff / Admin Persona:**
   - Log in using your superuser account created in Step 6.
   - Access **Staff Dashboard** to see live metrics and stock utilization gauges.
   - Visit **Manage Donations** and **Manage Requests** to approve or reject pending entries and observe automatic inventory stock adjustments.
   - Visit **User Management** to search user records and manage active statuses.
   - Access the Django Admin interface at `/admin/` for low-level database inspection.

---

## Team Git Workflow

To maintain code stability on our shared repository:
- All new features and bug fixes are developed on dedicated feature branches: `<developer-name>/<feature-name>` (e.g. `qamar/donation-review-inventory`).
- Direct commits to `main` are restricted.
- Changes are merged into `main` via GitHub Pull Requests requiring peer review and verification of passing test suites.

---

## Academic Notice & Acknowledgments

This project was built for educational purposes as part of the Software Engineering course curriculum at **PES University**, Bengaluru.
Special thanks to our course faculty and mentors for their guidance throughout Sprints 1 and 2.
