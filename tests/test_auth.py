from extensions import db
from models import User
from seed import seed_demo_data
from tests.conftest import create_user


def test_production_app_requires_environment_secret(monkeypatch):
    from app import create_app

    monkeypatch.delenv('SECRET_KEY', raising=False)
    try:
        create_app('production')
    except RuntimeError as exc:
        assert 'SECRET_KEY' in str(exc)
    else:
        raise AssertionError('Production must refuse to start without SECRET_KEY.')


def test_registration_success(client, app):
    """Test standard valid user registration."""
    response = client.post('/auth/register', data={
        'full_name': 'Test New User',
        'email': 'newuser@example.com',
        'phone': '+91-99999-88888',
        'locality': 'Koramangala',
        'role': 'help_seeker',
        'password': 'SecurePassword@123',
        'confirm_password': 'SecurePassword@123'
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email='newuser@example.com').first()
        assert user is not None
        assert user.role == 'help_seeker'
        assert user.password_hash != 'SecurePassword@123'
        assert user.check_password('SecurePassword@123')


def test_duplicate_email_registration_fails(client, app):
    """Test that attempting to register an existing email is rejected."""
    with app.app_context():
        create_user(email='existing@example.com')

    response = client.post('/auth/register', data={
        'full_name': 'Another Person',
        'email': 'existing@example.com',
        'phone': '+91-99999-77777',
        'locality': 'Indiranagar',
        'role': 'volunteer',
        'password': 'Password@123',
        'confirm_password': 'Password@123'
    })

    assert response.status_code == 200
    assert b"already registered" in response.data or b"is-invalid" in response.data


def test_public_admin_registration_prevented(client, app):
    """Test that public registration cannot grant the administrator role."""
    response = client.post('/auth/register', data={
        'full_name': 'Fake Admin',
        'email': 'fakeadmin@example.com',
        'phone': '+91-99999-66666',
        'locality': 'Central',
        'role': 'admin',
        'password': 'Password@123',
        'confirm_password': 'Password@123'
    }, follow_redirects=True)

    with app.app_context():
        admin = User.query.filter_by(email='fakeadmin@example.com').first()
        assert admin is None


def test_login_success_and_role_redirect(client, app):
    """Test successful authentication and role-based redirect for volunteer."""
    with app.app_context():
        create_user(role='volunteer', email='vol@example.com', password='VolPassword@123')

    response = client.post('/auth/login', data={
        'email': 'vol@example.com',
        'password': 'VolPassword@123'
    }, follow_redirects=True)

    assert response.status_code == 200
    # Volunteer should be redirected to volunteer coordination hub
    assert b"Volunteer Coordination Hub" in response.data or b"Volunteer Hub" in response.data


def test_login_invalid_password(client, app):
    """Test login failure on incorrect password."""
    with app.app_context():
        create_user(email='user@example.com', password='CorrectPassword@123')

    response = client.post('/auth/login', data={
        'email': 'user@example.com',
        'password': 'WrongPassword@123'
    }, follow_redirects=True)

    assert b"Invalid email address or password" in response.data


def test_logout(client, app):
    """Test user logout clears active session."""
    with app.app_context():
        user = create_user(email='logout_user@example.com')

    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['role'] = user.role

    response = client.get('/auth/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b"logged out" in response.data


def test_demo_seed_restores_passwords_for_existing_demo_accounts(client, app):
    with app.app_context():
        admin = create_user(
            role='admin',
            email='admin@communityhelp.org',
            password='OldAdminPassword@123'
        )
        admin.is_suspended = True
        seeker = create_user(
            role='help_seeker',
            email='seeker@example.com',
            password='OldSeekerPassword@123'
        )
        volunteer = create_user(
            role='volunteer',
            email='volunteer@example.com',
            password='OldVolunteerPassword@123'
        )
        db.session.get(User, volunteer.id).volunteer_verification.verification_status = 'pending'
        donor = create_user(
            role='donor',
            email='donor@example.com',
            password='OldDonorPassword@123'
        )

    seed_demo_data(app)

    demo_accounts = [
        ('admin@communityhelp.org', 'Admin@12345'),
        ('seeker@example.com', 'Seeker@123'),
        ('volunteer@example.com', 'Volunteer@123'),
        ('donor@example.com', 'Donor@123')
    ]
    for email, password in demo_accounts:
        response = client.post('/auth/login', data={'email': email, 'password': password})
        assert response.status_code == 302
        client.get('/auth/logout')

    with app.app_context():
        assert db.session.get(User, admin.id).is_suspended is False
        assert db.session.get(User, seeker.id).check_password('Seeker@123')
        assert db.session.get(User, volunteer.id).volunteer_verification.verification_status == 'approved'
        assert db.session.get(User, donor.id).check_password('Donor@123')
