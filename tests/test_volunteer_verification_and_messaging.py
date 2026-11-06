import io
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

from extensions import db
from models import (
    Conversation, ConversationReport, HelpRequest, Message, Notification,
    ResourceListing, ResourceRequest, User, VolunteerVerification,
    VolunteerVerificationHistory
)
from tests.conftest import create_user


def login_as(client, user):
    with client.session_transaction() as session:
        session['user_id'] = user.id
        session['role'] = user.role


def valid_pdf():
    return b'%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF'


def test_volunteer_registration_requires_id_and_starts_pending(client, app, monkeypatch):
    no_file = {
        'full_name': 'New Volunteer',
        'email': 'new-volunteer@example.com',
        'phone': '+91-98765-11111',
        'locality': 'Central Ward',
        'password': 'Password@123',
        'confirm_password': 'Password@123',
        'role': 'volunteer',
        'id_document_type': 'national_id'
    }
    response = client.post('/auth/register', data=no_file)
    assert response.status_code == 200
    assert b'ID document is required' in response.data
    with app.app_context():
        assert User.query.filter_by(email='new-volunteer@example.com').first() is None

    monkeypatch.setattr('auth.routes.upload_verification_document', lambda path, content, content_type: path)
    response = client.post('/auth/register', data={
        **no_file,
        'id_document': (io.BytesIO(valid_pdf()), 'identity.pdf')
    }, content_type='multipart/form-data')
    assert response.status_code == 302
    with app.app_context():
        volunteer = User.query.filter_by(email='new-volunteer@example.com').one()
        verification = VolunteerVerification.query.filter_by(volunteer_id=volunteer.id).one()
        assert verification.verification_status == 'pending'
        assert verification.id_document_name == 'identity.pdf'
        assert verification.id_document_path.startswith(f'volunteer/{volunteer.id}/')
        assert VolunteerVerificationHistory.query.filter_by(
            verification_id=verification.id, action='application_submitted'
        ).count() == 1
        assert Notification.query.filter_by(user_id=volunteer.id).count() == 2


def test_registration_rejects_spoofed_file_and_information_request_allows_resubmission(client, app, monkeypatch):
    registration = {
        'full_name': 'Corrected Volunteer',
        'email': 'corrected-volunteer@example.com',
        'phone': '+91-98765-11111',
        'locality': 'Central Ward',
        'password': 'Password@123',
        'confirm_password': 'Password@123',
        'role': 'volunteer',
        'id_document_type': 'passport'
    }
    rejected = client.post('/auth/register', data={
        **registration,
        'id_document': (io.BytesIO(b'not a PDF'), 'identity.pdf')
    }, content_type='multipart/form-data')
    assert rejected.status_code == 200
    with app.app_context():
        assert User.query.filter_by(email=registration['email']).first() is None

    monkeypatch.setattr('auth.routes.upload_verification_document', lambda path, content, content_type: path)
    client.post('/auth/register', data={
        **registration,
        'id_document': (io.BytesIO(valid_pdf()), 'identity.pdf')
    }, content_type='multipart/form-data')
    with app.app_context():
        volunteer = User.query.filter_by(email=registration['email']).one()
        admin = create_user(role='admin', email='information-admin@example.com')
        volunteer_id, admin_id = volunteer.id, admin.id
    login_as(client, admin)
    response = client.post(
        f'/admin/volunteers/{volunteer_id}/verification/request-information',
        data={'message': 'Please submit a clearer identity document.'}
    )
    assert response.status_code == 302
    login_as(client, volunteer)
    status_page = client.get('/auth/volunteer-verification')
    assert b'Admin has requested additional documents' in status_page.data
    response = client.post('/auth/volunteer-verification/resubmit', data={
        'id_document_type': 'passport',
        'id_document': (io.BytesIO(valid_pdf()), 'updated.pdf')
    }, content_type='multipart/form-data')
    assert response.status_code == 302
    with app.app_context():
        verification = VolunteerVerification.query.filter_by(volunteer_id=volunteer_id).one()
        assert verification.verification_status == 'resubmitted'
        assert verification.id_document_name == 'updated.pdf'
        assert verification.history[0].action == 'documents_resubmitted'
        assert verification.history[1].actor_id == admin_id


def test_pending_and_suspended_volunteers_are_blocked_from_volunteer_routes(client, app):
    with app.app_context():
        pending = create_user(role='volunteer', email='pending-volunteer@example.com')
        VolunteerVerification.query.filter_by(volunteer_id=pending.id).one().verification_status = 'pending'
        request_record = HelpRequest(
            seeker_id=pending.id,
            category='Medical Assistance',
            title='A request',
            description='A sufficiently detailed request description.',
            locality='Central Ward'
        )
        db.session.add(request_record)
        db.session.commit()
        volunteer_id, request_id = pending.id, request_record.id

    login_as(client, pending)
    dashboard = client.get('/volunteers/dashboard')
    assert dashboard.status_code == 302
    assert dashboard.headers['Location'].endswith('/auth/volunteer-verification')
    accepted = client.post(f'/volunteers/accept/{request_id}')
    assert accepted.status_code == 302
    with app.app_context():
        assert db.session.get(HelpRequest, request_id).assigned_volunteer_id is None
        verification = VolunteerVerification.query.filter_by(volunteer_id=volunteer_id).one()
        verification.verification_status = 'suspended'
        db.session.commit()
    blocked = client.get('/volunteers/dashboard')
    assert blocked.status_code == 302


def test_admin_review_updates_status_history_and_private_preview(client, app, monkeypatch):
    with app.app_context():
        admin = create_user(role='admin', email='reviewer@example.com')
        volunteer = create_user(role='volunteer', email='reviewed-volunteer@example.com')
        verification = VolunteerVerification.query.filter_by(volunteer_id=volunteer.id).one()
        verification.id_document_path = f'volunteer/{volunteer.id}/id.pdf'
        verification.id_document_type = 'national_id'
        verification.verification_status = 'pending'
        db.session.commit()
        admin_id, volunteer_id = admin.id, volunteer.id
    login_as(client, admin)

    monkeypatch.setattr('admin.routes.create_document_signed_url', lambda path, expires_in: 'https://storage.example/signed')
    preview = client.get(f'/admin/volunteers/{volunteer_id}/documents/id')
    assert preview.status_code == 302
    assert preview.headers['Location'] == 'https://storage.example/signed'

    approved = client.post(f'/admin/volunteers/{volunteer_id}/verification/approve')
    assert approved.status_code == 302
    with app.app_context():
        verification = VolunteerVerification.query.filter_by(volunteer_id=volunteer_id).one()
        assert verification.verification_status == 'approved'
        assert verification.verification_reviewed_by == admin_id
        assert verification.verification_reviewed_at is not None
        assert VolunteerVerificationHistory.query.filter_by(action='approved').count() == 1
        assert Notification.query.filter_by(user_id=volunteer_id).count() == 1

    login_as(client, volunteer)
    assert client.get('/volunteers/dashboard').status_code == 200
    login_as(client, admin)
    suspended = client.post(
        f'/admin/volunteers/{volunteer_id}/verification/suspend',
        data={'message': 'Policy violation'}
    )
    assert suspended.status_code == 302
    with app.app_context():
        assert VolunteerVerification.query.filter_by(volunteer_id=volunteer_id).one().verification_status == 'suspended'
    login_as(client, volunteer)
    assert client.get('/volunteers/dashboard').status_code == 302


def test_help_seeker_and_donor_exchange_private_messages(client, app):
    with app.app_context():
        seeker = create_user(role='help_seeker', email='messaging-seeker@example.com')
        donor = create_user(role='donor', email='messaging-donor@example.com')
        resource = ResourceListing(
            donor_id=donor.id,
            category='Essential Items Assistance',
            name='Blankets',
            description='Warm blankets',
            quantity=5,
            unit='items',
            locality='Central Ward',
            available_until=datetime.now(timezone.utc) + timedelta(days=2),
            status='Available'
        )
        db.session.add(resource)
        db.session.commit()
        seeker_id, donor_id, resource_id = seeker.id, donor.id, resource.id

    login_as(client, seeker)
    response = client.post(f'/messages/contact/{resource_id}')
    assert response.status_code == 302
    with app.app_context():
        conversation = Conversation.query.one()
        conversation_id = conversation.id
        assert conversation.help_seeker_id == seeker_id
        assert conversation.donor_id == donor_id
        assert conversation.resource_listing_id == resource_id
        assert Notification.query.filter_by(user_id=donor_id).count() == 1

    client.post(
        f'/messages/conversations/{conversation_id}/send',
        data={'message_text': 'Are the blankets still available?'}
    )
    login_as(client, donor)
    donor_view = client.get(f'/messages/?conversation={conversation_id}')
    assert donor_view.status_code == 200
    assert b'Are the blankets still available?' in donor_view.data
    with app.app_context():
        assert Message.query.one().is_read is True
        assert Message.query.one().read_at is not None

    client.post(
        f'/messages/conversations/{conversation_id}/send',
        data={'message_text': 'Yes, five are available for pickup.'}
    )
    login_as(client, seeker)
    seeker_view = client.get(f'/messages/?conversation={conversation_id}')
    assert b'five are available for pickup' in seeker_view.data
    with app.app_context():
        assert Message.query.count() == 2
        assert Message.query.filter_by(is_read=False).count() == 0


def test_nonparticipants_cannot_read_private_conversation(client, app):
    with app.app_context():
        seeker = create_user(role='help_seeker', email='private-seeker@example.com')
        donor = create_user(role='donor', email='private-donor@example.com')
        unrelated = create_user(role='help_seeker', email='unrelated@example.com')
        volunteer = create_user(role='volunteer', email='private-volunteer@example.com')
        conversation = Conversation(help_seeker_id=seeker.id, donor_id=donor.id)
        db.session.add(conversation)
        db.session.commit()
        conversation_id = conversation.id
    login_as(client, unrelated)
    assert client.get(f'/messages/?conversation={conversation_id}').status_code == 404
    login_as(client, volunteer)
    assert client.get(f'/messages/?conversation={conversation_id}').status_code == 404


def test_closed_conversation_blocks_messages_until_donor_reopens(client, app):
    with app.app_context():
        seeker = create_user(role='help_seeker', email='closed-seeker@example.com')
        donor = create_user(role='donor', email='closed-donor@example.com')
        conversation = Conversation(help_seeker_id=seeker.id, donor_id=donor.id)
        db.session.add(conversation)
        db.session.commit()
        conversation_id = conversation.id
    login_as(client, donor)
    assert client.post(f'/messages/conversations/{conversation_id}/close').status_code == 302
    login_as(client, seeker)
    closed_response = client.post(
        f'/messages/conversations/{conversation_id}/send',
        data={'message_text': 'This should not be sent.'},
        follow_redirects=True
    )
    assert b'conversation is closed' in closed_response.data
    with app.app_context():
        assert Message.query.count() == 0
    login_as(client, donor)
    assert client.post(f'/messages/conversations/{conversation_id}/reopen').status_code == 302
    login_as(client, seeker)
    client.post(
        f'/messages/conversations/{conversation_id}/send',
        data={'message_text': 'This is now allowed.'}
    )
    with app.app_context():
        assert Message.query.count() == 1


def test_donor_and_volunteer_can_exchange_private_resource_messages(client, app):
    with app.app_context():
        donor = create_user(role='donor', email='resource-chat-donor@example.com')
        volunteer = create_user(role='volunteer', email='resource-chat-volunteer@example.com')
        other_volunteer = create_user(role='volunteer', email='resource-chat-other@example.com')
        resource = ResourceListing(
            donor_id=donor.id,
            category='Essential Items Assistance',
            name='Winter coats',
            description='Warm coats for pickup.',
            quantity=4,
            unit='items',
            locality='Central Ward',
            status='Available'
        )
        db.session.add(resource)
        db.session.flush()
        resource_request = ResourceRequest(
            resource_id=resource.id,
            volunteer_id=volunteer.id,
            quantity=2,
            status='Pending'
        )
        db.session.add(resource_request)
        db.session.commit()
        donor_id, volunteer_id = donor.id, volunteer.id
        request_id = resource_request.id

    login_as(client, donor)
    response = client.post(f'/messages/resource-requests/{request_id}/contact')
    assert response.status_code == 302
    conversation_id = int(response.headers['Location'].rsplit('=', 1)[1])
    with app.app_context():
        conversation = db.session.get(Conversation, conversation_id)
        assert conversation.help_seeker_id == volunteer_id
        assert conversation.donor_id == donor_id
        assert Notification.query.filter_by(user_id=volunteer_id).count() == 1

    login_as(client, volunteer)
    assert client.get(f'/messages/?conversation={conversation_id}').status_code == 200
    assert client.post(
        f'/messages/conversations/{conversation_id}/send',
        data={'message_text': 'When can I collect the coats?'}
    ).status_code == 302

    login_as(client, donor)
    donor_view = client.get(f'/messages/?conversation={conversation_id}')
    assert donor_view.status_code == 200
    assert b'When can I collect the coats?' in donor_view.data

    login_as(client, other_volunteer)
    assert client.get(f'/messages/?conversation={conversation_id}').status_code == 404
    assert client.post(f'/messages/resource-requests/{request_id}/contact').status_code == 403


def test_volunteer_can_start_private_conversation_with_resource_donor(client, app):
    with app.app_context():
        donor = create_user(role='donor', email='volunteer-start-donor@example.com')
        volunteer = create_user(role='volunteer', email='volunteer-start@example.com')
        resource = ResourceListing(
            donor_id=donor.id,
            category='Essential Items Assistance',
            name='Food boxes',
            description='Food boxes for pickup.',
            quantity=3,
            unit='boxes',
            locality='Central Ward',
            status='Available'
        )
        db.session.add(resource)
        db.session.flush()
        resource_request = ResourceRequest(
            resource_id=resource.id,
            volunteer_id=volunteer.id,
            quantity=1,
            status='Pending'
        )
        db.session.add(resource_request)
        db.session.commit()
        donor_id = donor.id
        request_id = resource_request.id

    login_as(client, volunteer)
    response = client.post(f'/messages/resource-requests/{request_id}/contact')
    assert response.status_code == 302
    conversation_id = int(response.headers['Location'].rsplit('=', 1)[1])

    login_as(client, donor)
    assert client.get(f'/messages/?conversation={conversation_id}').status_code == 200
    assert client.post(
        f'/messages/conversations/{conversation_id}/send',
        data={'message_text': 'The food boxes are ready for pickup.'}
    ).status_code == 302

    login_as(client, volunteer)
    volunteer_view = client.get(f'/messages/?conversation={conversation_id}')
    assert b'The food boxes are ready for pickup.' in volunteer_view.data
    with app.app_context():
        conversation = db.session.get(Conversation, conversation_id)
        assert conversation.donor_id == donor_id


def test_volunteer_can_contact_donor_without_reserving_resource(client, app):
    with app.app_context():
        donor = create_user(role='donor', email='direct-donor@example.com')
        volunteer = create_user(role='volunteer', email='direct-volunteer@example.com')
        pending = create_user(role='volunteer', email='direct-pending@example.com')
        db.session.get(User, pending.id).volunteer_verification.verification_status = 'pending'
        resource = ResourceListing(
            donor_id=donor.id,
            category='Essential Items Assistance',
            name='School kits',
            description='Notebooks and stationery for pickup.',
            quantity=8,
            unit='kits',
            locality='Central Ward',
            status='Available'
        )
        db.session.add(resource)
        db.session.commit()
        donor_id, volunteer_id, pending_id = donor.id, volunteer.id, pending.id
        resource_id, quantity = resource.id, resource.quantity

    login_as(client, volunteer)
    resource_page = client.get('/messages/resources')
    assert resource_page.status_code == 200
    assert b'School kits' in resource_page.data
    response = client.post(f'/messages/contact/{resource_id}')
    assert response.status_code == 302
    conversation_id = int(response.headers['Location'].rsplit('=', 1)[1])

    with app.app_context():
        conversation = db.session.get(Conversation, conversation_id)
        assert conversation.help_seeker_id == volunteer_id
        assert conversation.donor_id == donor_id
        assert db.session.get(ResourceListing, resource_id).quantity == quantity
        assert Notification.query.filter_by(user_id=donor_id).count() == 1

    login_as(client, donor)
    response = client.post(
        f'/messages/conversations/{conversation_id}/send',
        data={'message_text': 'The school kits are available.'},
        headers={'Accept': 'application/json'}
    )
    assert response.status_code == 201
    assert response.get_json()['message']['text'] == 'The school kits are available.'

    login_as(client, volunteer)
    polled = client.get(f'/messages/conversations/{conversation_id}/poll?after=0')
    assert polled.status_code == 200
    assert polled.get_json()['messages'][0]['is_read'] is True
    assert b'direct-donor@example.com' not in client.get(
        f'/messages/?conversation={conversation_id}'
    ).data

    report_response = client.post(
        f'/messages/conversations/{conversation_id}/report',
        data={'reason': 'Please review this test conversation.'}
    )
    assert report_response.status_code == 302
    with app.app_context():
        report_id = ConversationReport.query.one().id
        admin = create_user(role='admin', email='report-review-admin@example.com')
        other = create_user(role='help_seeker', email='report-review-other@example.com')

    login_as(client, admin)
    review = client.get(f'/admin/conversation-reports?report={report_id}')
    assert review.status_code == 200
    assert b'Please review this test conversation.' in review.data
    assert b'The school kits are available.' in review.data

    login_as(client, other)
    assert client.get(f'/messages/?conversation={conversation_id}').status_code == 404
    login_as(client, pending)
    assert client.get('/messages/').status_code == 302
    assert client.post(f'/messages/contact/{resource_id}').status_code == 302
    with app.app_context():
        assert Conversation.query.count() == 1
        assert db.session.get(User, pending_id).volunteer_verification.verification_status == 'pending'


def test_message_history_is_paginated_and_private(client, app):
    with app.app_context():
        seeker = create_user(role='help_seeker', email='history-seeker@example.com')
        donor = create_user(role='donor', email='history-donor@example.com')
        unrelated = create_user(role='help_seeker', email='history-unrelated@example.com')
        conversation = Conversation(help_seeker_id=seeker.id, donor_id=donor.id)
        db.session.add(conversation)
        db.session.flush()
        db.session.add_all([
            Message(
                conversation_id=conversation.id,
                sender_id=seeker.id if index % 2 else donor.id,
                message_text=f'History message {index}'
            )
            for index in range(55)
        ])
        db.session.commit()
        conversation_id = conversation.id
        unrelated_user = unrelated

    login_as(client, seeker)
    inbox = client.get(f'/messages/?conversation={conversation_id}')
    assert inbox.status_code == 200
    assert b'Load older messages' in inbox.data
    assert b'History message 54' in inbox.data
    assert b'History message 0' not in inbox.data

    older = client.get(f'/messages/conversations/{conversation_id}/history?before=6')
    assert older.status_code == 200
    result = older.get_json()
    assert [message['text'] for message in result['messages']] == [
        'History message 0',
        'History message 1',
        'History message 2',
        'History message 3',
        'History message 4'
    ]
    assert result['has_more'] is False

    login_as(client, unrelated_user)
    assert client.get(
        f'/messages/conversations/{conversation_id}/history?before=6'
    ).status_code == 404


def test_storage_error_logs_supabase_detail_without_logging_service_key(monkeypatch, caplog):
    import document_storage

    service_key = 'test-secret-service-key'
    monkeypatch.setenv('SUPABASE_URL', 'https://project.example')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', service_key)

    def reject_request(*args, **kwargs):
        raise HTTPError(
            'https://project.example/storage/v1/object/private/file.pdf',
            400,
            'Bad Request',
            {},
            io.BytesIO(b'{"message":"Bucket not found","key":"test-secret-service-key"}')
        )

    monkeypatch.setattr(document_storage, 'urlopen', reject_request)
    with caplog.at_level('ERROR'):
        try:
            document_storage.upload_verification_document('volunteer/1/id.pdf', b'%PDF-1.7\n%%EOF', 'application/pdf')
        except document_storage.DocumentStorageError as exc:
            assert 'HTTP 400' in str(exc)
        else:
            raise AssertionError('Expected a storage error.')

    assert 'Bucket not found' in caplog.text
    assert service_key not in caplog.text
