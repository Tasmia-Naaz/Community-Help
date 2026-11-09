from datetime import datetime, timezone

from extensions import db
from models import HelpRequest, Notification, ResourceListing, User
from tests.conftest import create_user


def test_help_seeker_dashboard_paginates_requests_and_keeps_status_filter(client, app):
    with app.app_context():
        seeker = create_user(email='pagination-seeker@example.com')
        db.session.add_all([
            HelpRequest(
                seeker_id=seeker.id,
                category='Essential Items Assistance',
                title=f'Pagination request {index}',
                description='A sufficiently detailed request for pagination tests.',
                urgency='Normal',
                locality='Indiranagar',
                status='Pending',
                created_at=datetime(2026, 1, index, tzinfo=timezone.utc)
            )
            for index in range(1, 26)
        ])
        db.session.commit()

    with client.session_transaction() as session:
        session['user_id'] = seeker.id
        session['role'] = 'help_seeker'

    response = client.get('/requests/dashboard?status=Pending&requests_page=2')

    assert response.status_code == 200
    assert b'Pagination request 5' in response.data
    assert b'Pagination request 25' not in response.data
    assert b'requests_page=1' in response.data
    assert b'status=Pending' in response.data


def test_notifications_are_paginated_and_marked_read_without_full_row_load(client, app):
    with app.app_context():
        user = create_user(email='pagination-notifications@example.com')
        db.session.add_all([
            Notification(
                user_id=user.id,
                title=f'Notification {index}',
                message='Pagination test notification',
                is_read=False,
                created_at=datetime(2026, 1, index, tzinfo=timezone.utc)
            )
            for index in range(1, 26)
        ])
        db.session.commit()

    with client.session_transaction() as session:
        session['user_id'] = user.id
        session['role'] = user.role

    response = client.get('/auth/notifications?notifications_page=2')

    assert response.status_code == 200
    assert b'Notification 5' in response.data
    assert b'Notification 25' not in response.data
    assert b'notifications_page=1' in response.data
    with app.app_context():
        assert Notification.query.filter_by(user_id=user.id, is_read=False).count() == 0


def test_donor_dashboard_paginates_listings_and_preserves_metrics(client, app):
    with app.app_context():
        donor = create_user(role='donor', email='pagination-donor@example.com')
        db.session.add_all([
            ResourceListing(
                donor_id=donor.id,
                category='Essential Items Assistance',
                name=f'Pagination resource {index}',
                description='A listed resource for pagination tests.',
                quantity=1,
                unit='items',
                locality='Indiranagar',
                status='Available',
                created_at=datetime(2026, 1, index, tzinfo=timezone.utc)
            )
            for index in range(1, 26)
        ])
        db.session.commit()

    with client.session_transaction() as session:
        session['user_id'] = donor.id
        session['role'] = donor.role

    response = client.get('/donations/dashboard?listings_page=2')

    assert response.status_code == 200
    assert b'Pagination resource 5' in response.data
    assert b'Pagination resource 25' not in response.data
    assert b'listings_page=1' in response.data
    assert b'>25<' in response.data
