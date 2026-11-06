from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, request, g, abort
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from extensions import db
from models import HelpRequest, StatusHistory, User, ResourceListing
from forms import HelpRequestForm, StatusUpdateForm
from decorators import login_required, role_required
from helpers import (
    record_status_change, broadcast_to_volunteers, 
    validate_request_transition, create_notification, get_active_emergency
)
from . import help_requests_bp


@help_requests_bp.route('/dashboard')
@role_required('help_seeker', 'admin')
def seeker_dashboard():
    """Help Seeker Dashboard showing summary statistics and own submitted requests."""
    status_filter = request.args.get('status', '').strip()
    
    query = HelpRequest.query.filter_by(seeker_id=g.current_user.id)
    if status_filter and status_filter in ['Pending', 'Accepted', 'In Progress', 'Completed', 'Cancelled']:
        query = query.filter_by(status=status_filter)
        
    requests_list = query.options(
        joinedload(HelpRequest.assigned_volunteer)
    ).order_by(HelpRequest.created_at.desc()).all()

    request_counts = db.session.query(
        HelpRequest.status,
        func.count(HelpRequest.id)
    ).filter_by(seeker_id=g.current_user.id).group_by(HelpRequest.status).all()
    counts_by_status = dict(request_counts)
    total_count = sum(counts_by_status.values())
    pending_count = counts_by_status.get('Pending', 0)
    active_count = counts_by_status.get('Accepted', 0) + counts_by_status.get('In Progress', 0)
    completed_count = counts_by_status.get('Completed', 0)
    available_resources = ResourceListing.query.filter_by(status='Available').filter(
        ResourceListing.quantity > 0
    ).order_by(ResourceListing.created_at.desc()).limit(6).all()

    return render_template(
        'help_seeker_dashboard.html',
        requests=requests_list,
        total_count=total_count,
        pending_count=pending_count,
        active_count=active_count,
        completed_count=completed_count,
        available_resources=available_resources,
        current_filter=status_filter
    )


@help_requests_bp.route('/new', methods=['GET', 'POST'])
@role_required('help_seeker', 'admin')
def new_request():
    """Create a new Help Request."""
    form = HelpRequestForm()
    # Pre-fill locality if available
    if request.method == 'GET' and not form.locality.data:
        form.locality.data = g.current_user.locality

    if form.validate_on_submit():
        deadline_val = None
        if form.deadline.data:
            deadline_val = datetime.combine(form.deadline.data, datetime.min.time()).replace(tzinfo=timezone.utc)

        help_req = HelpRequest(
            seeker_id=g.current_user.id,
            category=form.category.data,
            title=form.title.data.strip(),
            description=form.description.data.strip(),
            urgency=form.urgency.data,
            locality=form.locality.data.strip(),
            deadline=deadline_val,
            contact_preference=form.contact_preference.data,
            status='Pending'
        )
        db.session.add(help_req)
        db.session.flush()  # Flush to obtain generated primary key ID

        # Record initial status in audit trail
        record_status_change(
            entity_type='HelpRequest',
            entity_id=help_req.id,
            previous_status='Created',
            new_status='Pending',
            changed_by_id=g.current_user.id,
            notes='Initial help request created'
        )

        # Notify nearby volunteers
        urgent_badge = f"[{form.urgency.data.upper()}] " if form.urgency.data in ['Urgent', 'Critical'] else ""
        broadcast_to_volunteers(
            locality=(form.locality.data or '').strip(),
            title=f"{urgent_badge}New Help Request in {(form.locality.data or '').strip()}",
            message=f"{g.current_user.full_name} needs assistance with '{(form.title.data or '').strip()}'.",
            link=url_for('help_requests.view_request', request_id=help_req.id)
        )

        db.session.commit()
        flash("Your help request has been posted successfully! Nearby volunteers have been notified.", "success")
        return redirect(url_for('help_requests.seeker_dashboard'))

    return render_template('request_form.html', form=form, is_edit=False)


@help_requests_bp.route('/<int:request_id>')
@login_required
def view_request(request_id):
    """
    View help request details with privacy protections and audit status history.
    """
    help_req = HelpRequest.query.get_or_404(request_id)
    history = StatusHistory.query.filter_by(entity_type='HelpRequest', entity_id=request_id)\
        .order_by(StatusHistory.created_at.desc()).all()

    user = g.current_user
    is_owner = (user.id == help_req.seeker_id)
    is_assignee = (user.id == help_req.assigned_volunteer_id)
    is_admin = user.is_admin

    # Access control: volunteers and donors can only view requests if they are open, or if they are assigned, or if they are admin/owner
    if user.role == 'help_seeker' and not is_owner and not is_admin:
        flash("You are not authorized to view another seeker's private request details.", "danger")
        return redirect(url_for('help_requests.seeker_dashboard'))

    # Privacy Protection Check for Contact Information
    can_view_contact = False
    if is_owner or is_admin:
        can_view_contact = True
    elif help_req.contact_preference == 'share_always':
        can_view_contact = True
    elif help_req.contact_preference == 'share_on_accept' and is_assignee:
        can_view_contact = True

    # Active emergency for highlighting
    active_emergency = get_active_emergency()

    return render_template(
        'request_detail.html',
        request_obj=help_req,
        history=history,
        is_owner=is_owner,
        is_assignee=is_assignee,
        can_view_contact=can_view_contact,
        active_emergency=active_emergency
    )


@help_requests_bp.route('/<int:request_id>/cancel', methods=['POST'])
@login_required
def cancel_request(request_id):
    """Cancel a help request (allowed only for the seeker or admin)."""
    help_req = HelpRequest.query.get_or_404(request_id)
    user = g.current_user
    is_owner = (user.id == help_req.seeker_id)
    is_admin = user.is_admin

    if not (is_owner or is_admin):
        flash("Unauthorized: Only the creator or an administrator can cancel this request.", "danger")
        return redirect(url_for('help_requests.view_request', request_id=request_id))

    is_valid, msg = validate_request_transition(help_req.status, 'Cancelled', user.role, is_owner=is_owner)
    if not is_valid:
        flash(f"Cannot cancel request: {msg}", "warning")
        return redirect(url_for('help_requests.view_request', request_id=request_id))

    previous_status = help_req.status
    help_req.status = 'Cancelled'
    
    # Notify volunteer if one was assigned
    if help_req.assigned_volunteer_id:
        create_notification(
            user_id=help_req.assigned_volunteer_id,
            title="Task Cancelled by Seeker",
            message=f"The task '{help_req.title}' has been cancelled by the requestor.",
            link=url_for('help_requests.view_request', request_id=help_req.id)
        )

    record_status_change(
        entity_type='HelpRequest',
        entity_id=help_req.id,
        previous_status=previous_status,
        new_status='Cancelled',
        changed_by_id=user.id,
        notes="Cancelled by requestor" if is_owner else "Cancelled by administrator"
    )
    db.session.commit()

    flash("Help request has been cancelled.", "info")
    return redirect(url_for('help_requests.seeker_dashboard' if is_owner else 'admin.dashboard'))
