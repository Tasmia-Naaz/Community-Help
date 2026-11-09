from datetime import datetime, timezone
from uuid import uuid4

from flask import current_app, render_template, redirect, url_for, flash, request, session, g, abort
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from models import User, Notification, VolunteerVerification, VolunteerVerificationHistory
from forms import RegistrationForm, LoginForm
from helpers import (
    check_login_rate_limit, record_failed_login,
    clear_failed_logins, create_notification
)
from decorators import login_required
from document_storage import DocumentStorageError, upload_verification_document, delete_verification_document
from document_validation import InvalidDocumentError, read_validated_document
from . import auth_bp


def _store_upload(user_id, kind, document):
    if not document:
        return None
    path = f'volunteer/{user_id}/{uuid4().hex}-{kind}{document["extension"]}'
    upload_verification_document(path, document['content'], document['content_type'])
    return path


def _cleanup_uploaded(paths):
    for path in paths:
        try:
            delete_verification_document(path)
        except DocumentStorageError:
            current_app.logger.exception('Could not remove an orphaned verification document.')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Public registration for Help Seekers, Volunteers, and Donors."""
    if session.get('user_id'):
        flash("You are already logged in.", "info")
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        email = (form.email.data or '').strip().lower()
        role = form.role.data

        # Explicit security safeguard: Public registration cannot create administrators
        if role == 'admin':
            flash("Administrator accounts cannot be created via public registration.", "danger")
            return render_template('register.html', form=form)

        id_document = None
        certificate = None
        if role == 'volunteer':
            if not form.id_document_type.data:
                form.id_document_type.errors.append('Select the type of ID document.')
            try:
                id_document = read_validated_document(
                    form.id_document.data, required=True,
                    max_bytes=current_app.config['VOLUNTEER_DOCUMENT_MAX_BYTES']
                )
                certificate = read_validated_document(
                    form.volunteer_certificate.data, required=False,
                    max_bytes=current_app.config['VOLUNTEER_DOCUMENT_MAX_BYTES']
                )
            except InvalidDocumentError as exc:
                field = form.id_document if not id_document else form.volunteer_certificate
                field.errors.append(str(exc))
            if form.id_document_type.errors or form.id_document.errors or form.volunteer_certificate.errors:
                return render_template('register.html', form=form)

        new_user = User(
            full_name=(form.full_name.data or '').strip(),
            email=email,
            phone=(form.phone.data or '').strip(),
            locality=(form.locality.data or '').strip(),
            role=role,
            is_verified=True,
            is_suspended=False
        )
        new_user.set_password(form.password.data or '')
        uploaded_paths = []
        try:
            db.session.add(new_user)
            db.session.flush()
            if role == 'volunteer':
                id_path = _store_upload(new_user.id, 'id', id_document)
                uploaded_paths.append(id_path)
                certificate_path = _store_upload(new_user.id, 'certificate', certificate)
                if certificate_path:
                    uploaded_paths.append(certificate_path)
                verification = VolunteerVerification(
                    volunteer_id=new_user.id,
                    id_document_type=form.id_document_type.data,
                    id_document_path=id_path,
                    id_document_name=id_document['filename'],
                    id_document_content_type=id_document['content_type'],
                    id_document_size=id_document['size'],
                    certificate_path=certificate_path,
                    certificate_name=certificate['filename'] if certificate else None,
                    certificate_content_type=certificate['content_type'] if certificate else None,
                    certificate_size=certificate['size'] if certificate else None,
                    volunteering_experience=(form.volunteering_experience.data or '').strip() or None,
                    verification_status='pending'
                )
                db.session.add(verification)
                db.session.flush()
                db.session.add(VolunteerVerificationHistory(
                    verification_id=verification.id,
                    action='application_submitted',
                    status='pending',
                    message='Volunteer application submitted.',
                    actor_id=new_user.id
                ))

            create_notification(
                user_id=new_user.id,
                title="Welcome to Community Help Connect!",
                message=f"Thank you for registering as a {role.replace('_', ' ').title()}.",
                link=None
            )
            if role == 'volunteer':
                create_notification(
                    user_id=new_user.id,
                    title="Volunteer application submitted",
                    message="Your documents are under review.",
                    link=url_for('auth.volunteer_verification_status')
                )
            db.session.commit()
        except (DocumentStorageError, SQLAlchemyError) as exc:
            db.session.rollback()
            _cleanup_uploaded(uploaded_paths)
            current_app.logger.error('Volunteer registration could not be completed: %s', exc)
            flash(str(exc) if isinstance(exc, DocumentStorageError) else
                  "Your account could not be created. Please try again.", "danger")
            return render_template('register.html', form=form), 503 if isinstance(exc, DocumentStorageError) else 500

        flash(
            "Account created. Your volunteer documents are pending administrator review."
            if role == 'volunteer' else "Account created successfully! You can now log in.",
            "success"
        )
        return redirect(url_for('auth.login'))

    return render_template('register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Secure user login with rate-limiting throttling and role redirection."""
    if session.get('user_id'):
        return redirect(url_for('index'))

    form = LoginForm()
    ip_identifier = request.remote_addr or 'unknown-ip'

    if form.validate_on_submit():
        email = (form.email.data or '').strip().lower()
        throttle_key = f"{ip_identifier}:{email}"

        # Check rate-limit throttling
        is_allowed, minutes_left = check_login_rate_limit(throttle_key)
        if not is_allowed:
            flash(f"Too many failed login attempts. For security, please try again in {minutes_left} minutes.", "danger")
            return render_template('login.html', form=form)

        user = User.query.filter_by(email=email).first()

        # Generic failure message to prevent email enumeration
        if not user or not user.check_password(form.password.data):
            record_failed_login(throttle_key)
            flash("Invalid email address or password. Please try again.", "danger")
            return render_template('login.html', form=form)

        if user.is_suspended:
            flash("Your account has been suspended. Please contact administrator support.", "danger")
            return render_template('login.html', form=form)

        # Clear throttle record on successful authentication
        clear_failed_logins(throttle_key)

        # Establish secure session
        session.clear()
        session['user_id'] = user.id
        session['user_name'] = user.full_name
        session['role'] = user.role
        session['locality'] = user.locality
        session.permanent = True

        flash(f"Welcome back, {user.full_name}!", "success")

        # Redirect based on user role
        if user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user.role == 'volunteer':
            verification = user.volunteer_verification
            if not verification or verification.verification_status != 'approved':
                return redirect(url_for('auth.volunteer_verification_status'))
            return redirect(url_for('volunteers.volunteer_dashboard'))
        elif user.role == 'donor':
            return redirect(url_for('donations.donor_dashboard'))
        elif user.role == 'help_seeker':
            return redirect(url_for('help_requests.seeker_dashboard'))
        return redirect(url_for('index'))

    return render_template('login.html', form=form)


@auth_bp.route('/volunteer-verification', methods=['GET'])
@login_required
def volunteer_verification_status():
    if g.current_user.role != 'volunteer':
        abort(403)
    verification = g.current_user.volunteer_verification
    if not verification:
        abort(404)
    latest_action = verification.history[0].action if verification.history else None
    return render_template(
        'volunteer_verification.html',
        verification=verification,
        information_requested=latest_action == 'information_requested'
    )


@auth_bp.route('/volunteer-verification/resubmit', methods=['POST'])
@login_required
def resubmit_volunteer_documents():
    user = g.current_user
    if user.role != 'volunteer':
        abort(403)
    verification = user.volunteer_verification
    if not verification:
        abort(404)
    latest_action = verification.history[0].action if verification.history else None
    if verification.verification_status not in {'rejected', 'resubmitted'} and latest_action != 'information_requested':
        abort(403)

    document_type = request.form.get('id_document_type', '').strip()
    allowed_types = {'national_id', 'passport', 'drivers_license', 'other'}
    if document_type not in allowed_types:
        flash('Select a valid ID document type.', 'danger')
        return redirect(url_for('auth.volunteer_verification_status'))

    replaced_paths = [
        path for path in (verification.id_document_path, verification.certificate_path)
        if path
    ]
    try:
        id_document = read_validated_document(
            request.files.get('id_document'), required=True,
            max_bytes=current_app.config['VOLUNTEER_DOCUMENT_MAX_BYTES']
        )
        certificate = read_validated_document(
            request.files.get('volunteer_certificate'), required=False,
            max_bytes=current_app.config['VOLUNTEER_DOCUMENT_MAX_BYTES']
        )
    except InvalidDocumentError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('auth.volunteer_verification_status'))

    uploaded_paths = []
    replaced_paths = [verification.id_document_path] if verification.id_document_path else []
    if certificate and verification.certificate_path:
        replaced_paths.append(verification.certificate_path)
    try:
        id_path = _store_upload(user.id, 'id', id_document)
        uploaded_paths.append(id_path)
        certificate_path = _store_upload(user.id, 'certificate', certificate)
        if certificate_path:
            uploaded_paths.append(certificate_path)

        verification.id_document_type = document_type
        verification.id_document_path = id_path
        verification.id_document_name = id_document['filename']
        verification.id_document_content_type = id_document['content_type']
        verification.id_document_size = id_document['size']
        if certificate:
            verification.certificate_path = certificate_path
            verification.certificate_name = certificate['filename']
            verification.certificate_content_type = certificate['content_type']
            verification.certificate_size = certificate['size']
        experience = request.form.get('volunteering_experience', '').strip()
        if len(experience) > 2000:
            raise InvalidDocumentError('Experience must be 2000 characters or fewer.')
        verification.volunteering_experience = experience or verification.volunteering_experience
        verification.verification_status = 'resubmitted'
        verification.verification_submitted_at = datetime.now(timezone.utc)
        verification.verification_reviewed_at = None
        verification.verification_reviewed_by = None
        verification.verification_notes = None
        db.session.add(VolunteerVerificationHistory(
            verification_id=verification.id,
            action='documents_resubmitted',
            status='resubmitted',
            message='Corrected documents submitted for review.',
            actor_id=user.id
        ))
        create_notification(
            user_id=user.id,
            title='Documents resubmitted',
            message='Your corrected documents have been submitted for administrator review.',
            link=url_for('auth.volunteer_verification_status')
        )
        db.session.commit()
        _cleanup_uploaded(replaced_paths)
    except InvalidDocumentError as exc:
        db.session.rollback()
        _cleanup_uploaded(uploaded_paths)
        flash(str(exc), 'danger')
        return redirect(url_for('auth.volunteer_verification_status'))
    except (DocumentStorageError, SQLAlchemyError) as exc:
        db.session.rollback()
        _cleanup_uploaded(uploaded_paths)
        current_app.logger.error('Volunteer document resubmission failed: %s', exc)
        flash(str(exc) if isinstance(exc, DocumentStorageError) else
              'Your documents could not be saved. Please try again.', 'danger')
        return redirect(url_for('auth.volunteer_verification_status')), 503 if isinstance(exc, DocumentStorageError) else 500

    flash('Your updated documents have been submitted for review.', 'success')
    return redirect(url_for('auth.volunteer_verification_status'))


@auth_bp.route('/logout')
def logout():
    """Clear session and log user out."""
    session.clear()
    flash("You have been securely logged out.", "info")
    return redirect(url_for('index'))


@auth_bp.route('/notifications')
@login_required
def notifications():
    """Display in-app notifications for the current user."""
    Notification.query.filter_by(
        user_id=g.current_user.id,
        is_read=False
    ).update(
        {Notification.is_read: True},
        synchronize_session=False
    )
    db.session.commit()

    notifications_page = Notification.query.filter_by(
        user_id=g.current_user.id
    ).order_by(Notification.created_at.desc()).paginate(
        page=request.args.get('notifications_page', 1, type=int) or 1,
        per_page=20,
        error_out=False
    )
    return render_template(
        'notifications.html',
        notifications=notifications_page.items,
        notifications_page=notifications_page
    )


@auth_bp.route('/notifications/read/<int:notif_id>', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    """Mark a specific notification as read."""
    notif = Notification.query.filter_by(id=notif_id, user_id=g.current_user.id).first_or_404()
    notif.is_read = True
    db.session.commit()
    return redirect(url_for('auth.notifications'))
