from sqlalchemy import create_engine, inspect, text

from migrate_help_seeker_confirmation import migrate_help_seeker_confirmation


def test_confirmation_migration_adds_columns_and_preserves_existing_requests():
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE help_requests ('
            'id INTEGER PRIMARY KEY, title VARCHAR(150) NOT NULL, status VARCHAR(30) NOT NULL'
            ')'
        ))
        connection.execute(text(
            "INSERT INTO help_requests (id, title, status) "
            "VALUES (17, 'Existing request', 'Completed')"
        ))

    migrate_help_seeker_confirmation(engine)
    migrate_help_seeker_confirmation(engine)

    columns = {column['name'] for column in inspect(engine).get_columns('help_requests')}
    assert {
        'volunteer_completed_at',
        'completion_note',
        'seeker_confirmed_at',
        'confirmed_by_id',
        'dispute_reason',
        'disputed_at',
        'rating',
        'feedback'
    }.issubset(columns)
    with engine.connect() as connection:
        existing_request = connection.execute(
            text('SELECT id, title, status FROM help_requests WHERE id = 17')
        ).one()
    assert tuple(existing_request) == (17, 'Existing request', 'Completed')
    engine.dispose()
