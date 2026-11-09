from datetime import datetime, timezone
from extensions import db
from models import HelpRequest, StatusHistory
from helpers import calculate_matching_score
from tests.conftest import create_user


def test_create_help_request(client, app):
    """Test help seeker submitting a new help request."""
    with app.app_context():
        seeker = create_user(role='help_seeker', email='seeker1@example.com')

    with client.session_transaction() as sess:
        sess['user_id'] = seeker.id
        sess['role'] = 'help_seeker'

    response = client.post('/requests/new', data={
        'category': 'Essential Items Assistance',
        'title': 'Need blankets for winter',
        'description': 'Need warm blankets for two seniors living in ground floor apartment.',
        'urgency': 'Normal',
        'locality': 'Indiranagar',
        'contact_preference': 'share_on_accept'
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        req = HelpRequest.query.filter_by(title='Need blankets for winter').first()
        assert req is not None
        assert req.status == 'Pending'
        assert req.seeker_id == seeker.id

        # Verify audit history entry was logged
        history = StatusHistory.query.filter_by(entity_type='HelpRequest', entity_id=req.id).first()
        assert history is not None
        assert history.new_status == 'Pending'


def test_duplicate_acceptance_prevention(client, app):
    """
    CRITICAL WORKFLOW D: Test that when two volunteers attempt to accept
    the same request, only the first succeeds and the second is safely rejected.
    """
    with app.app_context():
        seeker = create_user(role='help_seeker', email='seeker2@example.com')
        vol1 = create_user(role='volunteer', email='vol1@example.com')
        vol2 = create_user(role='volunteer', email='vol2@example.com')

        req = HelpRequest(
            seeker_id=seeker.id,
            category='Medical Assistance',
            title='Prescription delivery',
            description='Pick up urgent insulin prescription.',
            urgency='Critical',
            locality='Indiranagar',
            status='Pending'
        )
        db.session.add(req)
        db.session.commit()
        req_id = req.id

    # 1. Volunteer 1 accepts the request
    with client.session_transaction() as sess:
        sess['user_id'] = vol1.id
        sess['role'] = 'volunteer'

    resp1 = client.post(f'/volunteers/accept/{req_id}', follow_redirects=True)
    assert resp1.status_code == 200

    with app.app_context():
        updated_req = HelpRequest.query.get(req_id)
        assert updated_req.status == 'Accepted'
        assert updated_req.assigned_volunteer_id == vol1.id

    # 2. Volunteer 2 tries to accept the SAME request
    with client.session_transaction() as sess:
        sess['user_id'] = vol2.id
        sess['role'] = 'volunteer'

    resp2 = client.post(f'/volunteers/accept/{req_id}', follow_redirects=True)
    assert resp2.status_code == 200
    # Must show conflict notice
    assert b"already accepted" in resp2.data or b"no longer available" in resp2.data

    with app.app_context():
        # Ensure assignment has NOT changed to vol2
        final_req = HelpRequest.query.get(req_id)
        assert final_req.assigned_volunteer_id == vol1.id


def test_status_lifecycle_progression(client, app):
    """Test valid lifecycle transitions through Help Seeker confirmation."""
    with app.app_context():
        seeker = create_user(role='help_seeker', email='seeker3@example.com')
        volunteer = create_user(role='volunteer', email='vol3@example.com')

        req = HelpRequest(
            seeker_id=seeker.id,
            category='Transportation Assistance',
            title='Ride to clinic',
            description='Assistance needed to clinic appointment.',
            urgency='Urgent',
            locality='Indiranagar',
            status='Accepted',
            assigned_volunteer_id=volunteer.id
        )
        db.session.add(req)
        db.session.commit()
        req_id = req.id

    with client.session_transaction() as sess:
        sess['user_id'] = volunteer.id
        sess['role'] = 'volunteer'

    # Transition to In Progress
    resp = client.post(f'/volunteers/update-status/{req_id}', data={'new_status': 'In Progress'}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert HelpRequest.query.get(req_id).status == 'In Progress'

    # Volunteer reports completion; the request remains pending seeker confirmation.
    resp = client.post(f'/volunteers/update-status/{req_id}', data={
        'new_status': 'awaiting_confirmation',
        'completion_note': 'Delivered the supplies.'
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        req = HelpRequest.query.get(req_id)
        assert req.status == 'awaiting_confirmation'
        assert req.completion_note == 'Delivered the supplies.'
        assert req.volunteer_completed_at is not None


def test_rule_based_matching_score(app):
    """Test transparent rule-based matching calculation."""
    with app.app_context():
        seeker = create_user(role='help_seeker', email='seeker_rule@example.com')
        
        req_critical = HelpRequest(
            seeker_id=seeker.id,
            category='Medical Assistance',
            title='Critical Meds',
            description='Test',
            urgency='Critical',
            locality='Indiranagar',
            status='Pending'
        )
        req_normal = HelpRequest(
            seeker_id=seeker.id,
            category='Essential Items Assistance',
            title='Normal Items',
            description='Test',
            urgency='Normal',
            locality='Koramangala',
            status='Pending'
        )

        # Volunteer in Indiranagar
        score_crit = calculate_matching_score(req_critical, 'Indiranagar')
        score_norm = calculate_matching_score(req_normal, 'Indiranagar')

        # Critical + matching locality must score substantially higher than Normal in another locality
        assert score_crit > score_norm
