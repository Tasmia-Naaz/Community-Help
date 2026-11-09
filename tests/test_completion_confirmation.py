from datetime import datetime, timezone

from extensions import db
from models import HelpRequest, Notification, StatusHistory
from tests.conftest import create_user


def login_as(client, user):
    with client.session_transaction() as session:
        session['user_id'] = user.id


def create_in_progress_request(seeker, volunteer, title='Community assistance'):
    request_obj = HelpRequest(
        seeker_id=seeker.id,
        category='Essential Items Assistance',
        title=title,
        description='Help needed with a delivery.',
        urgency='Normal',
        locality='Indiranagar',
        status='In Progress',
        assigned_volunteer_id=volunteer.id
    )
    db.session.add(request_obj)
    db.session.commit()
    return request_obj.id


def test_volunteer_completion_is_pending_until_help_seeker_confirms(client, app):
    with app.app_context():
        seeker = create_user(email='confirmation-seeker@example.com')
        volunteer = create_user(role='volunteer', email='confirmation-volunteer@example.com')
        request_id = create_in_progress_request(seeker, volunteer)

    login_as(client, volunteer)
    response = client.post(
        f'/volunteers/update-status/{request_id}',
        data={
            'new_status': 'awaiting_confirmation',
            'completion_note': 'Delivered the groceries at the front door.'
        }
    )
    assert response.status_code == 302
    with app.app_context():
        request_obj = db.session.get(HelpRequest, request_id)
        assert request_obj.status == 'awaiting_confirmation'
        assert request_obj.completion_note == 'Delivered the groceries at the front door.'
        assert request_obj.volunteer_completed_at is not None
        assert Notification.query.filter_by(
            user_id=seeker.id,
            title='Please Confirm Your Help Request'
        ).count() == 1

    # A repeated volunteer submission must not overwrite the original completion report.
    client.post(
        f'/volunteers/update-status/{request_id}',
        data={'new_status': 'awaiting_confirmation', 'completion_note': 'Changed note'}
    )
    with app.app_context():
        assert db.session.get(HelpRequest, request_id).completion_note == 'Delivered the groceries at the front door.'
    volunteer_dashboard = client.get('/volunteers/dashboard')
    assert volunteer_dashboard.status_code == 200
    assert b'Awaiting Help Seeker Confirmation' in volunteer_dashboard.data

    login_as(client, seeker)
    seeker_dashboard = client.get('/requests/dashboard')
    assert seeker_dashboard.status_code == 200
    assert b'Pending Confirmation' in seeker_dashboard.data
    assert b'Delivered the groceries at the front door.' in seeker_dashboard.data
    response = client.post(f'/requests/{request_id}/confirm-completion')
    assert response.status_code == 302
    with app.app_context():
        request_obj = db.session.get(HelpRequest, request_id)
        assert request_obj.status == 'Completed'
        assert request_obj.confirmed_by_id == seeker.id
        assert request_obj.seeker_confirmed_at is not None
        assert Notification.query.filter_by(
            user_id=volunteer.id,
            title='Help Seeker Confirmed Completion'
        ).count() == 1

    # Confirmation cannot be repeated, and feedback can be submitted only once.
    client.post(f'/requests/{request_id}/confirm-completion')
    response = client.post(
        f'/requests/{request_id}/feedback',
        data={'rating': '5', 'feedback': 'Very helpful and kind.'}
    )
    assert response.status_code == 302
    client.post(
        f'/requests/{request_id}/feedback',
        data={'rating': '1', 'feedback': 'A duplicate rating must not replace the first.'}
    )
    with app.app_context():
        request_obj = db.session.get(HelpRequest, request_id)
        assert request_obj.rating == 5
        assert request_obj.feedback == 'Very helpful and kind.'
        assert StatusHistory.query.filter_by(
            entity_type='HelpRequest',
            entity_id=request_id,
            new_status='Completed'
        ).count() == 1


def test_help_seeker_dispute_notifies_volunteer_and_admin_then_admin_reopens(client, app):
    with app.app_context():
        seeker = create_user(email='dispute-seeker@example.com')
        volunteer = create_user(role='volunteer', email='dispute-volunteer@example.com')
        admin = create_user(role='admin', email='dispute-admin@example.com')
        request_id = create_in_progress_request(seeker, volunteer, 'Disputed assistance')
        request_obj = db.session.get(HelpRequest, request_id)
        request_obj.status = 'awaiting_confirmation'
        request_obj.volunteer_completed_at = datetime.now(timezone.utc)
        db.session.commit()

    login_as(client, seeker)
    response = client.post(
        f'/requests/{request_id}/dispute-completion',
        data={'reason': 'The delivery never arrived.'}
    )
    assert response.status_code == 302
    with app.app_context():
        request_obj = db.session.get(HelpRequest, request_id)
        assert request_obj.status == 'disputed'
        assert request_obj.dispute_reason == 'The delivery never arrived.'
        assert request_obj.disputed_at is not None
        assert Notification.query.filter_by(user_id=volunteer.id, title='Help Seeker Reported an Issue').count() == 1
        assert Notification.query.filter_by(user_id=admin.id, title='Help Request Needs Review').count() == 1

    login_as(client, admin)
    response = client.get('/admin/dashboard')
    assert response.status_code == 200
    assert b'Disputed Requests' in response.data
    response = client.post(
        f'/admin/requests/{request_id}/resolve-dispute',
        data={'action': 'reopen'}
    )
    assert response.status_code == 302
    with app.app_context():
        request_obj = db.session.get(HelpRequest, request_id)
        assert request_obj.status == 'Pending'
        assert request_obj.assigned_volunteer_id is None
        assert Notification.query.filter_by(user_id=seeker.id, title='Administrator Reviewed Your Dispute').count() == 1
        assert Notification.query.filter_by(user_id=volunteer.id, title='Administrator Reviewed the Disputed Task').count() == 1


def test_admin_can_verify_dispute_and_other_users_cannot_confirm(client, app):
    with app.app_context():
        seeker = create_user(email='verify-dispute-seeker@example.com')
        other_seeker = create_user(email='other-seeker@example.com')
        volunteer = create_user(role='volunteer', email='verify-dispute-volunteer@example.com')
        admin = create_user(role='admin', email='verify-dispute-admin@example.com')
        request_id = create_in_progress_request(seeker, volunteer, 'Verified disputed assistance')
        request_obj = db.session.get(HelpRequest, request_id)
        request_obj.status = 'disputed'
        request_obj.dispute_reason = 'Please investigate.'
        db.session.commit()

    login_as(client, other_seeker)
    assert client.post(f'/requests/{request_id}/confirm-completion').status_code == 403

    login_as(client, admin)
    response = client.post(
        f'/admin/requests/{request_id}/resolve-dispute',
        data={'action': 'completed', 'resolution_note': 'Verified with the Help Seeker.'}
    )
    assert response.status_code == 302
    # A duplicate administrator resolution is rejected.
    client.post(
        f'/admin/requests/{request_id}/resolve-dispute',
        data={'action': 'reopen'}
    )
    with app.app_context():
        request_obj = db.session.get(HelpRequest, request_id)
        assert request_obj.status == 'Completed'
        assert request_obj.confirmed_by_id is None
        assert Notification.query.filter_by(user_id=seeker.id, title='Administrator Reviewed Your Dispute').count() == 1


def test_completion_requires_assigned_volunteer_and_csrf(client, app):
    with app.app_context():
        seeker = create_user(email='csrf-seeker@example.com')
        volunteer = create_user(role='volunteer', email='csrf-volunteer@example.com')
        other_volunteer = create_user(role='volunteer', email='csrf-other-volunteer@example.com')
        request_id = create_in_progress_request(seeker, volunteer)

    login_as(client, other_volunteer)
    client.post(
        f'/volunteers/update-status/{request_id}',
        data={'new_status': 'awaiting_confirmation'}
    )
    with app.app_context():
        assert db.session.get(HelpRequest, request_id).status == 'In Progress'

    app.config['WTF_CSRF_ENABLED'] = True
    login_as(client, volunteer)
    response = client.post(
        f'/volunteers/update-status/{request_id}',
        data={'new_status': 'awaiting_confirmation'}
    )
    assert response.status_code == 400
