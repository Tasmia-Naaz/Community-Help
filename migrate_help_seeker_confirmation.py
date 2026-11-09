"""Add Help Seeker completion-confirmation fields to an existing database."""

from sqlalchemy import inspect, text

from app import create_app
from extensions import db


CONFIRMATION_COLUMNS = {
    'volunteer_completed_at': 'TIMESTAMP NULL',
    'completion_note': 'TEXT NULL',
    'seeker_confirmed_at': 'TIMESTAMP NULL',
    'confirmed_by_id': 'INTEGER NULL',
    'dispute_reason': 'TEXT NULL',
    'disputed_at': 'TIMESTAMP NULL',
    'rating': 'INTEGER NULL',
    'feedback': 'TEXT NULL',
}


def _add_confirmation_columns(engine):
    inspector = inspect(engine)
    if not inspector.has_table('help_requests'):
        raise RuntimeError(
            'The help_requests table does not exist. Initialize the application database first.'
        )

    existing_columns = {
        column['name'] for column in inspector.get_columns('help_requests')
    }
    status_column = next(
        column for column in inspector.get_columns('help_requests')
        if column['name'] == 'status'
    )
    existing_foreign_keys = {
        constraint['name'] for constraint in inspector.get_foreign_keys('help_requests')
    }
    with engine.begin() as connection:
        for column_name, column_definition in CONFIRMATION_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(text(
                    f'ALTER TABLE help_requests ADD COLUMN {column_name} {column_definition}'
                ))
        if engine.dialect.name == 'mysql' and status_column['type'].__class__.__name__ == 'ENUM':
            connection.execute(text(
                "ALTER TABLE help_requests MODIFY COLUMN status "
                "ENUM('Pending', 'Accepted', 'In Progress', 'awaiting_confirmation', "
                "'disputed', 'Completed', 'Cancelled') NOT NULL DEFAULT 'Pending'"
            ))
        if (
            engine.dialect.name in {'mysql', 'postgresql'}
            and 'fk_help_requests_confirmed_by' not in existing_foreign_keys
        ):
            connection.execute(text(
                'ALTER TABLE help_requests ADD CONSTRAINT fk_help_requests_confirmed_by '
                'FOREIGN KEY (confirmed_by_id) REFERENCES users(id) ON DELETE SET NULL'
            ))


def migrate_help_seeker_confirmation(engine=None):
    if engine is not None:
        _add_confirmation_columns(engine)
    else:
        app = create_app()
        with app.app_context():
            _add_confirmation_columns(db.engine)

    print(
        'Help Seeker confirmation fields are ready; existing help requests and records were preserved.'
    )


if __name__ == '__main__':
    migrate_help_seeker_confirmation()
