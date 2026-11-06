import sys
from pathlib import Path
import pytest

# Ensure application root directory is on Python search path
app_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(app_dir))

from app import create_app
from extensions import db
from models import User, VolunteerVerification


@pytest.fixture
def app():
    """Create application configured for testing with in-memory database."""
    application = create_app('testing')
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Test client for HTTP requests."""
    return app.test_client()


@pytest.fixture
def db_session(app):
    """Direct database session access."""
    with app.app_context():
        yield db.session


def create_user(role='help_seeker', email='user@example.com', password='Password@123', locality='Indiranagar'):
    """Helper to quickly create and commit a user for testing."""
    user = User(
        full_name=f"Test {role.title()}",
        email=email,
        phone="+91-98765-00000",
        locality=locality,
        role=role,
        is_verified=True,
        is_suspended=False
    )
    user.set_password(password)
    db.session.add(user)
    if role == 'volunteer':
        db.session.flush()
        db.session.add(VolunteerVerification(
            volunteer_id=user.id,
            verification_status='approved'
        ))
    db.session.commit()
    # Eagerly access attributes so they remain cached on the object
    _ = (user.id, user.email, user.role, user.full_name, user.locality, user.is_suspended, user.is_verified)
    db.session.expunge(user)
    return user
