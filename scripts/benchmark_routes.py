"""Benchmark rendered route response times using a synthetic in-memory database."""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from extensions import db
from models import User, VolunteerVerification


ROUTES = (
    ('Homepage', '/', 'help_seeker'),
    ('Help Seeker Dashboard', '/requests/dashboard', 'help_seeker'),
    ('Volunteer Dashboard', '/volunteers/dashboard', 'volunteer'),
    ('Donor Dashboard', '/donations/dashboard', 'donor'),
    ('Admin Dashboard', '/admin/dashboard', 'admin'),
)
SAMPLES = 10


def create_benchmark_user(role):
    user = User(
        full_name=f'Benchmark {role}',
        email=f'benchmark-{role}@example.invalid',
        phone='0000000000',
        locality='Benchmark',
        role=role,
        is_verified=True,
        is_suspended=False
    )
    user.set_password('benchmark-only-password')
    db.session.add(user)
    db.session.flush()
    if role == 'volunteer':
        db.session.add(VolunteerVerification(
            volunteer_id=user.id,
            verification_status='approved'
        ))
    return user


def main():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        roles = {role for _, _, role in ROUTES}
        users = {role: create_benchmark_user(role) for role in roles}
        db.session.commit()
        user_ids = {role: user.id for role, user in users.items()}
        client = app.test_client()
        results = []

        for label, path, role in ROUTES:
            with client.session_transaction() as session:
                session.clear()
                session['user_id'] = user_ids[role]
                session['role'] = role

            first_response = client.get(path)
            if first_response.status_code != 200:
                raise RuntimeError(
                    f'{label} returned HTTP {first_response.status_code}'
                )

            samples = []
            for _ in range(SAMPLES):
                started = time.perf_counter()
                response = client.get(path)
                elapsed_ms = (time.perf_counter() - started) * 1000
                if response.status_code != 200:
                    raise RuntimeError(
                        f'{label} returned HTTP {response.status_code}'
                    )
                samples.append(elapsed_ms)
            results.append((
                statistics.mean(samples),
                statistics.median(samples),
                max(samples),
                label
            ))

        print('Synthetic in-memory Flask test-client timings (milliseconds)')
        print('Route                       mean      median    max')
        for mean_ms, median_ms, max_ms, label in sorted(results, reverse=True):
            print(f'{label:27} {mean_ms:8.2f} {median_ms:10.2f} {max_ms:8.2f}')
        print('These timings exclude Render, network, and Supabase latency.')
        db.session.remove()
        db.drop_all()


if __name__ == '__main__':
    main()
