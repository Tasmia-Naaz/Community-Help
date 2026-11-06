"""Create only the new verification and messaging tables in an existing database."""

from app import create_app
from extensions import db
from models import (
    Conversation, ConversationReport, Message, User, VolunteerVerification,
    VolunteerVerificationHistory
)


def migrate_community_features():
    app = create_app()
    feature_tables = [
        VolunteerVerification.__table__,
        VolunteerVerificationHistory.__table__,
        Conversation.__table__,
        Message.__table__,
        ConversationReport.__table__
    ]
    with app.app_context():
        db.metadata.create_all(bind=db.engine, tables=feature_tables)
        legacy_volunteers = User.query.filter_by(role='volunteer').all()
        for volunteer in legacy_volunteers:
            if volunteer.volunteer_verification:
                continue
            verification = VolunteerVerification(
                volunteer_id=volunteer.id,
                verification_status='pending'
            )
            db.session.add(verification)
            db.session.flush()
            db.session.add(VolunteerVerificationHistory(
                verification_id=verification.id,
                action='legacy_application_imported',
                status='pending',
                message='Existing volunteer requires administrator review after migration.'
            ))
        db.session.commit()
        print('Volunteer verification and messaging tables are ready; existing records were preserved.')


if __name__ == '__main__':
    migrate_community_features()
