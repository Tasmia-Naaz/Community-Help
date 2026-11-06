from datetime import datetime, timezone
from flask import current_app, render_template, redirect, url_for, flash, request, g, abort
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload
from extensions import db
from models import (
    User, HelpRequest, ResourceListing, EmergencyEvent, StatusHistory, Notification,
    VolunteerVerification, VolunteerVerificationHistory, Conversation, ConversationReport, Message
)
from forms import EmergencyEventForm
from decorators import admin_required
from helpers import get_active_emergency, broadcast_to_volunteers, record_status_change, create_notification
from document_storage import DocumentStorageError, create_document_signed_url
from . import admin_bp


@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """
    Administrator Dashboard:
    Metrics, user management, request/resource oversight, and emergency control center.
    """
    # 1. Total KPI Metrics
    total_users = User.query.count()
    request_counts = dict(db.session.query(
        HelpRequest.status,
        func.count(HelpRequest.id)
    ).group_by(HelpRequest.status).all())
    total_requests = sum(request_counts.values())
    open_requests = request_counts.get('Pending', 0)
    in_progress_requests = request_counts.get('In Progress', 0)
    completed_requests = request_counts.get('Completed', 0)
    resource_counts = dict(db.session.query(
        ResourceListing.status,
        func.count(ResourceListing.id)
    ).group_by(ResourceListing.status).all())
    total_resources = sum(resource_counts.values())
    active_resources = resource_counts.get('Available', 0)

    # 2. Search & Filtering for Users
    user_search = request.args.get('user_search', '').strip()
    user_query = User.query
    if user_search:
        user_query = user_query.filter(
            (User.full_name.ilike(f"%{user_search}%")) |
            (User.email.ilike(f"%{user_search}%")) |
            (User.locality.ilike(f"%{user_search}%"))
        )
    users_list = user_query.options(
        joinedload(User.volunteer_verification)
    ).order_by(User.created_at.desc()).limit(50).all()

    # 3. Recent Requests
    recent_requests = HelpRequest.query.options(
        joinedload(HelpRequest.seeker),
        joinedload(HelpRequest.assigned_volunteer)
    ).order_by(HelpRequest.created_at.desc()).limit(30).all()

    # 4. Recent Resources
    recent_resources = ResourceListing.query.options(
        joinedload(ResourceListing.donor)
    ).order_by(ResourceListing.created_at.desc()).limit(30).all()

    # 5. Active Emergency & Event Logs
    active_emergency = get_active_emergency()
    past_emergencies = EmergencyEvent.query.order_by(EmergencyEvent.activated_at.desc()).limit(10).all()

    # 6. Recent Audit Status History
    recent_history = StatusHistory.query.options(
        joinedload(StatusHistory.changed_by)
    ).order_by(StatusHistory.created_at.desc()).limit(20).all()
    volunteer_verifications = VolunteerVerification.query.join(
        User, User.id == VolunteerVerification.volunteer_id
    ).filter(
        User.role == 'volunteer'
    ).options(
        joinedload(VolunteerVerification.volunteer),
        selectinload(VolunteerVerification.history).joinedload(VolunteerVerificationHistory.actor)
    ).order_by(VolunteerVerification.verification_submitted_at.desc()).limit(100).all()

    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        total_requests=total_requests,
        open_requests=open_requests,
        in_progress_requests=in_progress_requests,
        completed_requests=completed_requests,
        total_resources=total_resources,
        active_resources=active_resources,
        users=users_list,
        requests=recent_requests,
        resources=recent_resources,
        active_emergency=active_emergency,
        past_emergencies=past_emergencies,
        recent_history=recent_history,
        volunteer_verifications=volunteer_verifications,
        user_search=user_search
    )


@admin_bp.route('/conversation-reports')
@admin_required
def conversation_reports():
    page = request.args.get('page', 1, type=int)
    reports = ConversationReport.query.options(
        joinedload(ConversationReport.reporter),
        joinedload(ConversationReport.conversation).joinedload(Conversation.help_seeker),
        joinedload(ConversationReport.conversation).joinedload(Conversation.donor),
        joinedload(ConversationReport.conversation).joinedload(Conversation.resource_listing)
    ).order_by(ConversationReport.created_at.desc()).paginate(
        page=page,
        per_page=20,
        error_out=False
    )

    report_id = request.args.get('report', type=int)
    selected_report = None
    recent_messages = []
    if report_id:
        selected_report = ConversationReport.query.options(
            joinedload(ConversationReport.reporter),
            joinedload(ConversationReport.conversation).joinedload(Conversation.help_seeker),
            joinedload(ConversationReport.conversation).joinedload(Conversation.donor),
            joinedload(ConversationReport.conversation).joinedload(Conversation.resource_listing)
        ).filter_by(id=report_id).first_or_404()
        recent_messages = Message.query.options(
            joinedload(Message.sender)
        ).filter_by(
            conversation_id=selected_report.conversation_id
        ).order_by(Message.id.desc()).limit(50).all()
        recent_messages.reverse()

    return render_template(
        'admin_conversation_reports.html',
        reports=reports,
        selected_report=selected_report,
        recent_messages=recent_messages
    )


@admin_bp.route('/volunteers/<int:volunteer_id>/verification/<action>', methods=['POST'])
@admin_required
def review_volunteer(volunteer_id, action):
    verification = VolunteerVerification.query.join(
        User, User.id == VolunteerVerification.volunteer_id
    ).filter(
        VolunteerVerification.volunteer_id == volunteer_id,
        User.role == 'volunteer'
    ).first_or_404()
    if verification.verification_status == 'suspended':
        flash('This volunteer is suspended and cannot be reviewed further.', 'warning')
        return redirect(url_for('admin.dashboard'))

    message = request.form.get('message', '').strip()
    allowed_actions = {'approve', 'reject', 'request-information', 'suspend'}
    if action not in allowed_actions:
        abort(404)
    if action in {'reject', 'request-information', 'suspend'} and not message:
        flash('A reason or message is required for this action.', 'danger')
        return redirect(url_for('admin.dashboard'))
    if action == 'suspend' and verification.verification_status != 'approved':
        flash('Only an approved volunteer can be suspended.', 'warning')
        return redirect(url_for('admin.dashboard'))
    if action == 'approve' and (not verification.id_document_path or not verification.id_document_type):
        flash('A volunteer must have an ID document on file before approval.', 'warning')
        return redirect(url_for('admin.dashboard'))
    if action in {'reject', 'request-information'} and verification.verification_status == 'approved':
        flash('An approved volunteer must be suspended rather than reviewed as an application.', 'warning')
        return redirect(url_for('admin.dashboard'))

    now = datetime.now(timezone.utc)
    if action == 'approve':
        verification.verification_status = 'approved'
        verification.verification_notes = None
        history_action = 'approved'
        notice_title = 'Volunteer application approved'
        notice_message = 'Your volunteer account has been verified. You can now access volunteer features.'
    elif action == 'reject':
        verification.verification_status = 'rejected'
        verification.verification_notes = message
        history_action = 'rejected'
        notice_title = 'Volunteer application not approved'
        notice_message = message
    elif action == 'request-information':
        verification.verification_notes = message
        history_action = 'information_requested'
        notice_title = 'Additional volunteer documents requested'
        notice_message = message
    else:
        verification.verification_status = 'suspended'
        verification.verification_notes = message
        history_action = 'suspended'
        notice_title = 'Volunteer account suspended'
        notice_message = message

    verification.verification_reviewed_at = now
    verification.verification_reviewed_by = g.current_user.id
    db.session.add(VolunteerVerificationHistory(
        verification_id=verification.id,
        action=history_action,
        status=verification.verification_status,
        message=message or notice_message,
        actor_id=g.current_user.id
    ))
    create_notification(
        user_id=volunteer_id,
        title=notice_title,
        message=notice_message,
        link=url_for('auth.volunteer_verification_status')
    )
    db.session.commit()
    flash('Volunteer verification action recorded.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/volunteers/<int:volunteer_id>/documents/<document_type>')
@admin_required
def volunteer_document(volunteer_id, document_type):
    verification = VolunteerVerification.query.filter_by(volunteer_id=volunteer_id).first_or_404()
    paths = {
        'id': verification.id_document_path,
        'certificate': verification.certificate_path
    }
    if document_type not in paths or not paths[document_type]:
        abort(404)
    try:
        signed_url = create_document_signed_url(paths[document_type], expires_in=60)
    except DocumentStorageError as exc:
        current_app.logger.error('Could not create volunteer document preview URL: %s', exc)
        flash('The private document preview is temporarily unavailable.', 'danger')
        return redirect(url_for('admin.dashboard')), 503
    return redirect(signed_url)


@admin_bp.route('/users/<int:user_id>/toggle-suspend', methods=['POST'])
@admin_required
def toggle_user_suspension(user_id):
    """Suspend or reactivate a user account."""
    user = User.query.get_or_404(user_id)
    
    # Safeguard: Prevent admin from suspending themselves
    if user.id == g.current_user.id:
        flash("You cannot suspend your own administrator account.", "warning")
        return redirect(url_for('admin.dashboard'))

    user.is_suspended = not user.is_suspended
    db.session.commit()

    action = "suspended" if user.is_suspended else "reactivated"
    flash(f"User {user.email} has been {action}.", "info")
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/users/<int:user_id>/toggle-verify', methods=['POST'])
@admin_required
def toggle_user_verification(user_id):
    """Mark a user account as verified or unverified."""
    user = User.query.get_or_404(user_id)
    user.is_verified = not user.is_verified
    db.session.commit()

    action = "verified" if user.is_verified else "unverified"
    flash(f"User {user.email} marked as {action}.", "info")
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/emergency/new', methods=['GET', 'POST'])
@admin_required
def declare_emergency():
    """
    WORKFLOW G: Emergency Mode Activation.
    Declares a community emergency, prioritizes relief in affected locality,
    and dispatches broadcast notifications to volunteers.
    """
    form = EmergencyEventForm()

    if form.validate_on_submit():
        # Deactivate any previous active emergencies
        EmergencyEvent.query.filter_by(is_active=True).update({'is_active': False, 'deactivated_at': datetime.now(timezone.utc)})

        event = EmergencyEvent(
            created_by_id=g.current_user.id,
            emergency_type=form.emergency_type.data.strip(),
            affected_locality=form.affected_locality.data.strip(),
            severity=form.severity.data,
            description=form.description.data.strip(),
            is_active=True,
            activated_at=datetime.now(timezone.utc)
        )
        db.session.add(event)
        db.session.commit()

        # Broadcast high-priority notification to all volunteers in the locality
        notif_count = broadcast_to_volunteers(
            locality=event.affected_locality,
            title=f"EMERGENCY ALERT [{event.severity.upper()}]: {event.emergency_type}",
            message=f"Community emergency declared in {event.affected_locality}. Urgent assistance required: {event.description[:120]}...",
            link=url_for('volunteers.volunteer_dashboard')
        )

        flash(f"Emergency Mode ACTIVATED for {event.affected_locality}. In-app alert dispatched to {notif_count} volunteers.", "danger")
        return redirect(url_for('admin.dashboard'))

    return render_template('emergency_form.html', form=form)


@admin_bp.route('/emergency/<int:event_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_emergency(event_id):
    """Deactivate an active emergency mode."""
    event = EmergencyEvent.query.get_or_404(event_id)
    event.is_active = False
    event.deactivated_at = datetime.now(timezone.utc)
    db.session.commit()

    flash(f"Emergency '{event.emergency_type}' in {event.affected_locality} has been DEACTIVATED.", "success")
    return redirect(url_for('admin.dashboard'))
