"""
Database Initialization and Seed Script for Community Help Connect.
Can be run via Windows PowerShell:
    python seed.py --admin-only
    python seed.py --demo
"""

import sys
from datetime import datetime, timezone, timedelta
from app import create_app
from extensions import db
from models import (
    User, HelpRequest, ResourceListing, EmergencyEvent, StatusHistory, Notification,
    VolunteerVerification, VolunteerVerificationHistory
)


def init_db(app):
    """Create all database tables based on SQLAlchemy models."""
    with app.app_context():
        db.create_all()
        print(" [OK] Database tables verified / created successfully.")


def create_initial_admin(app):
    """
    Creates the master administrator account securely.
    Public registration explicitly forbids admin account creation.
    """
    with app.app_context():
        admin_email = "admin@communityhelp.org"
        existing = User.query.filter_by(email=admin_email).first()
        if existing:
            admin_id = existing.id
            existing.set_password("Admin@12345")
            existing.is_suspended = False
            db.session.commit()
            print(f" [INFO] Admin account '{admin_email}' already exists. Demo password restored.")
            return admin_id

        admin = User(
            full_name="System Administrator",
            email=admin_email,
            phone="+91-98765-43210",
            locality="Central District",
            role="admin",
            is_verified=True,
            is_suspended=False
        )
        admin.set_password("Admin@12345")
        db.session.add(admin)
        db.session.flush()
        admin_id = admin.id
        db.session.commit()
        print(f" [OK] Master Admin created: {admin_email} | Password: Admin@12345")
        return admin_id


def seed_demo_data(app):
    """
    Populates realistic demo accounts, requests, and resource listings
    for  demonstrations and local testing.
    """
    with app.app_context():
        admin_id = create_initial_admin(app)

        # 1. Demo Help Seeker
        seeker = User.query.filter_by(email="seeker@example.com").first()
        if not seeker:
            seeker = User(
                full_name="Priya Sharma",
                email="seeker@example.com",
                phone="+91-98765-11111",
                locality="Indiranagar, Sector 4",
                role="help_seeker",
                is_verified=True
            )
            db.session.add(seeker)
        seeker.role = "help_seeker"
        seeker.is_verified = True
        seeker.is_suspended = False
        seeker.set_password("Seeker@123")

        # 2. Demo Volunteer
        volunteer = User.query.filter_by(email="volunteer@example.com").first()
        if not volunteer:
            volunteer = User(
                full_name="Rahul Verma",
                email="volunteer@example.com",
                phone="+91-98765-22222",
                locality="Indiranagar, Sector 4",
                role="volunteer",
                is_verified=True
            )
            db.session.add(volunteer)
        volunteer.role = "volunteer"
        volunteer.is_verified = True
        volunteer.is_suspended = False
        volunteer.set_password("Volunteer@123")

        # 3. Demo Donor
        donor = User.query.filter_by(email="donor@example.com").first()
        if not donor:
            donor = User(
                full_name="Ananya Desai",
                email="donor@example.com",
                phone="+91-98765-33333",
                locality="Koramangala, 5th Block",
                role="donor",
                is_verified=True
            )
            db.session.add(donor)
        donor.role = "donor"
        donor.is_verified = True
        donor.is_suspended = False
        donor.set_password("Donor@123")

        db.session.commit()
        demo_verification = VolunteerVerification.query.filter_by(volunteer_id=volunteer.id).first()
        if not demo_verification:
            demo_verification = VolunteerVerification(
                volunteer_id=volunteer.id,
                verification_status='approved',
                verification_reviewed_at=datetime.now(timezone.utc),
                verification_reviewed_by=admin_id,
                verification_notes='Pre-approved demo account; no identity documents are on file.'
            )
            db.session.add(demo_verification)
            db.session.flush()
            db.session.add(VolunteerVerificationHistory(
                verification_id=demo_verification.id,
                action='approved',
                status='approved',
                message='Pre-approved demo account; no identity documents are on file.',
                actor_id=admin_id
            ))
            db.session.commit()
        else:
            if demo_verification.verification_status != 'approved':
                demo_verification.verification_status = 'approved'
                demo_verification.verification_reviewed_at = datetime.now(timezone.utc)
                demo_verification.verification_reviewed_by = admin_id
                db.session.add(VolunteerVerificationHistory(
                    verification_id=demo_verification.id,
                    action='approved',
                    status='approved',
                    message='Pre-approved demo account; no identity documents are on file.',
                    actor_id=admin_id
                ))
                db.session.commit()
        print(" [OK] Demo user accounts created (Seeker, Volunteer, Donor).")

        # 4. Demo Help Requests across the 6 categories
        now = datetime.now(timezone.utc)
        
        sample_requests = [
            {
                'category': 'Medical Assistance',
                'title': 'Emergency insulin pickup for senior citizen',
                'description': 'My 78-year-old grandmother needs her monthly insulin vials collected from Apollo Pharmacy on 100ft road as I am out of town today.',
                'urgency': 'Critical',
                'locality': 'Indiranagar, Sector 4',
                'deadline': now + timedelta(hours=6),
                'contact_preference': 'share_on_accept',
                'status': 'Pending'
            },
            {
                'category': 'Transportation Assistance',
                'title': 'Hospital transportation assistance for dialysis appointment',
                'description': 'Wheelchair accessible transport needed tomorrow at 9:00 AM to Victoria Hospital and back at 1:00 PM.',
                'urgency': 'Urgent',
                'locality': 'Indiranagar, Sector 4',
                'deadline': now + timedelta(days=1),
                'contact_preference': 'share_on_accept',
                'status': 'Pending'
            },
            {
                'category': 'Essential Items Assistance',
                'title': 'Winter blankets and sweaters for elderly shelter residents',
                'description': 'Seeking 15 warm blankets and clean woolens for 10 elderly residents at St. Joseph Community Home before night temperatures drop.',
                'urgency': 'Normal',
                'locality': 'Indiranagar, Sector 4',
                'deadline': now + timedelta(days=3),
                'contact_preference': 'share_always',
                'status': 'Pending'
            },
            {
                'category': 'Lost and Found Assistance',
                'title': 'Lost Golden Retriever wearing a blue nylon collar',
                'description': 'Friendly male Golden Retriever named "Buddy" slipped out of the garden gate near 12th Main park. Microchipped, answers to whistle.',
                'urgency': 'Normal',
                'locality': 'Indiranagar, Sector 4',
                'deadline': None,
                'contact_preference': 'share_always',
                'status': 'Pending'
            },
            {
                'category': 'Emergency Relief',
                'title': 'Clean drinking water bottles for rain-flooded basement apartment',
                'description': 'Storm drain backflow flooded 3 ground floor apartments. Drinking water supply contaminated. Need 20-liter drinking water jars.',
                'urgency': 'Critical',
                'locality': 'Indiranagar, Sector 4',
                'deadline': now + timedelta(hours=12),
                'contact_preference': 'share_on_accept',
                'status': 'Pending'
            }
        ]

        created_req_count = 0
        for data in sample_requests:
            existing_req = HelpRequest.query.filter_by(title=data['title']).first()
            if not existing_req:
                req = HelpRequest(
                    seeker_id=seeker.id,
                    category=data['category'],
                    title=data['title'],
                    description=data['description'],
                    urgency=data['urgency'],
                    locality=data['locality'],
                    deadline=data['deadline'],
                    contact_preference=data['contact_preference'],
                    status=data['status']
                )
                db.session.add(req)
                db.session.flush()

                # Add status history
                history = StatusHistory(
                    entity_type='HelpRequest',
                    entity_id=req.id,
                    previous_status='Created',
                    new_status='Pending',
                    changed_by_id=seeker.id,
                    notes='Demo initial request setup'
                )
                db.session.add(history)
                created_req_count += 1

        db.session.commit()
        print(f" [OK] Added {created_req_count} sample help requests.")

        # 5. Demo Resource Listings
        sample_resources = [
            {
                'category': 'Surplus Food Sharing',
                'description': 'Freshly prepared vegetarian meal boxes (rice, dal, sabzi, roti) from corporate conference buffet. Packed in sanitary disposable food containers.',
                'quantity': 35,
                'unit': 'packaged meal boxes',
                'locality': 'Koramangala, 5th Block',
                'available_until': now + timedelta(hours=8),
                'expiry_date': now + timedelta(hours=12),
                'pickup_instructions': 'Pickup from rear catering entrance of Horizon Tech Park. Ask for Manager Deepak.',
                'contact_preference': 'share_always',
                'status': 'Available'
            },
            {
                'category': 'Essential Items Assistance',
                'description': 'Unused children school kits containing notebooks, geometry sets, crayons, and water bottles.',
                'quantity': 25,
                'unit': 'study kits',
                'locality': 'Koramangala, 5th Block',
                'available_until': now + timedelta(days=14),
                'expiry_date': None,
                'pickup_instructions': 'Available for pickup weekdays between 10 AM and 6 PM.',
                'contact_preference': 'share_always',
                'status': 'Available'
            },
            {
                'category': 'Medical Assistance',
                'description': 'Two foldable adult wheelchairs and a pair of adjustable aluminum walking crutches, thoroughly sanitized.',
                'quantity': 2,
                'unit': 'wheelchairs + crutches',
                'locality': 'Indiranagar, Sector 4',
                'available_until': now + timedelta(days=30),
                'expiry_date': None,
                'pickup_instructions': 'Ground floor residence. Advance notice required to arrange loading.',
                'contact_preference': 'share_on_accept',
                'status': 'Available'
            }
        ]

        created_res_count = 0
        for rdata in sample_resources:
            existing_res = ResourceListing.query.filter_by(description=rdata['description']).first()
            if not existing_res:
                res = ResourceListing(
                    donor_id=donor.id,
                    category=rdata['category'],
                    description=rdata['description'],
                    quantity=rdata['quantity'],
                    unit=rdata['unit'],
                    locality=rdata['locality'],
                    available_until=rdata['available_until'],
                    expiry_date=rdata['expiry_date'],
                    pickup_instructions=rdata['pickup_instructions'],
                    contact_preference=rdata['contact_preference'],
                    status=rdata['status']
                )
                db.session.add(res)
                db.session.flush()

                rhistory = StatusHistory(
                    entity_type='ResourceListing',
                    entity_id=res.id,
                    previous_status='Created',
                    new_status='Available',
                    changed_by_id=donor.id,
                    notes='Demo initial resource setup'
                )
                db.session.add(rhistory)
                created_res_count += 1

        db.session.commit()
        print(f" [OK] Added {created_res_count} sample resource listings.")

        # 6. Sample Notifications
        if not Notification.query.filter_by(
            user_id=volunteer.id,
            title="Urgent Community Need in Your Area"
        ).first():
            n1 = Notification(
                user_id=volunteer.id,
                title="Urgent Community Need in Your Area",
                message="A critical medical assistance request was submitted in Indiranagar, Sector 4.",
                link="/volunteers/dashboard"
            )
            db.session.add(n1)
            db.session.commit()
        print(" [OK] Initial notifications populated.")
        print("\n=== SEED COMPLETE ===")
        print("Admin Login:     admin@communityhelp.org / Admin@12345")
        print("Seeker Login:    seeker@example.com    / Seeker@123")
        print("Volunteer Login: volunteer@example.com / Volunteer@123")
        print("Donor Login:     donor@example.com     / Donor@123")
        print("======================\n")


if __name__ == '__main__':
    app = create_app()
    arg = sys.argv[1] if len(sys.argv) > 1 else '--demo'

    init_db(app)

    if arg == '--admin-only':
        create_initial_admin(app)
    else:
        seed_demo_data(app)
