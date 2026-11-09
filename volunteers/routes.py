from datetime import datetime, timezone
import math
from flask import render_template, redirect, url_for, flash, request, g, abort
from sqlalchemy import update
from sqlalchemy.orm import joinedload
from extensions import db
from models import HelpRequest, ResourceListing, ResourceRequest, StatusHistory, User
from forms import StatusUpdateForm
from decorators import role_required
from helpers import (
    calculate_matching_score, record_status_change, 
    create_notification, validate_request_transition, get_active_emergency
)
from . import volunteers_bp


@volunteers_bp.route('/dashboard')
@role_required('volunteer', 'admin')
def volunteer_dashboard():
    """
    Volunteer Dashboard displaying rule-matched open community requests 
    and the volunteer's assigned tasks.
    """
    user = g.current_user
    category_filter = request.args.get('category', '').strip()
    locality_filter = request.args.get('locality', '').strip()
    resource_category_filter = request.args.get('resource_category', '').strip()
    resource_locality_filter = request.args.get('resource_locality', '').strip()

    active_emergency = get_active_emergency()

    # Query all currently open requests (Pending and unassigned)
    open_query = HelpRequest.query.filter_by(status='Pending', assigned_volunteer_id=None)
    
    if category_filter:
        open_query = open_query.filter(HelpRequest.category == category_filter)
    if locality_filter:
        open_query = open_query.filter(HelpRequest.locality.ilike(f"%{locality_filter}%"))
        
    all_open_requests = open_query.all()

    # Apply transparent Rule-Based Matching Algorithm
    # Prioritizes by urgency, locality match, emergency status, and request age
    scored_requests = []
    for req in all_open_requests:
        score = calculate_matching_score(req, user.locality, active_emergency)
        scored_requests.append((score, req))

    # Sort descending by calculated matching score
    scored_requests.sort(key=lambda x: x[0], reverse=True)
    open_requests = [item[1] for item in scored_requests]

    # Volunteer's assigned tasks
    assigned_tasks = HelpRequest.query.options(
        joinedload(HelpRequest.seeker)
    ).filter_by(assigned_volunteer_id=user.id)\
        .order_by(HelpRequest.updated_at.desc()).all()

    resource_query = ResourceListing.query.filter(
        ResourceListing.status == 'Available',
        ResourceListing.quantity > 0
    )
    if resource_category_filter:
        resource_query = resource_query.filter(ResourceListing.category == resource_category_filter)
    if resource_locality_filter:
        resource_query = resource_query.filter(ResourceListing.locality.ilike(f"%{resource_locality_filter}%"))

    available_resources = resource_query.order_by(ResourceListing.created_at.desc()).all()
    expired_resources = [resource for resource in available_resources if resource.auto_check_expiry()]
    if expired_resources:
        for resource in expired_resources:
            record_status_change(
                entity_type='ResourceListing',
                entity_id=resource.id,
                previous_status='Available',
                new_status='Withdrawn',
                changed_by_id=resource.donor_id,
                notes='Automatically marked Withdrawn after resource availability expired.'
            )
        db.session.commit()
        available_resources = [resource for resource in available_resources if resource.status == 'Available']

    resource_categories = [row[0] for row in db.session.query(ResourceListing.category).distinct().order_by(ResourceListing.category).all()]
    resource_requests = ResourceRequest.query.options(
        joinedload(ResourceRequest.resource)
    ).filter_by(volunteer_id=user.id)\
        .order_by(ResourceRequest.updated_at.desc()).all()

    # Metrics
    pending_tasks_count = sum(1 for t in assigned_tasks if t.status in ['Accepted', 'In Progress'])
    completed_tasks_count = sum(1 for t in assigned_tasks if t.status == 'Completed')

    return render_template(
        'volunteer_dashboard.html',
        open_requests=open_requests,
        assigned_tasks=assigned_tasks,
        pending_tasks_count=pending_tasks_count,
        completed_tasks_count=completed_tasks_count,
        active_emergency=active_emergency,
        selected_category=category_filter,
        selected_locality=locality_filter,
        available_resources=available_resources,
        resource_categories=resource_categories,
        resource_requests=resource_requests,
        selected_resource_category=resource_category_filter,
        selected_resource_locality=resource_locality_filter
    )


@volunteers_bp.route('/resources/<int:resource_id>/request', methods=['POST'])
@role_required('volunteer')
def request_resource(resource_id):
    """Submit one active request for available items from a donor listing."""
    user = g.current_user
    try:
        requested_quantity = float(request.form.get('quantity', ''))
    except (TypeError, ValueError):
        requested_quantity = 0

    if not math.isfinite(requested_quantity) or requested_quantity <= 0:
        flash('Enter a valid quantity greater than zero.', 'danger')
        return redirect(url_for('volunteers.volunteer_dashboard'))

    resource = ResourceListing.query.filter_by(id=resource_id).with_for_update().first_or_404()
    if resource.auto_check_expiry():
        record_status_change(
            entity_type='ResourceListing',
            entity_id=resource.id,
            previous_status='Available',
            new_status='Withdrawn',
            changed_by_id=resource.donor_id,
            notes='Automatically marked Withdrawn after resource availability expired.'
        )
        db.session.commit()
        flash('This resource is no longer available.', 'warning')
        return redirect(url_for('volunteers.volunteer_dashboard'))

    if resource.status != 'Available' or requested_quantity > resource.quantity:
        flash('The requested quantity exceeds the available stock or this listing is unavailable.', 'warning')
        return redirect(url_for('volunteers.volunteer_dashboard'))

    active_request = ResourceRequest.query.filter(
        ResourceRequest.resource_id == resource.id,
        ResourceRequest.volunteer_id == user.id,
        ResourceRequest.status.in_(['Pending', 'Approved', 'Collected'])
    ).first()
    if active_request:
        flash('You already have an active request for this resource.', 'warning')
        return redirect(url_for('volunteers.volunteer_dashboard'))

    resource_request = ResourceRequest(
        resource_id=resource.id,
        volunteer_id=user.id,
        quantity=requested_quantity,
        status='Pending'
    )
    db.session.add(resource_request)
    db.session.flush()
    record_status_change(
        entity_type='ResourceRequest',
        entity_id=resource_request.id,
        previous_status='Created',
        new_status='Pending',
        changed_by_id=user.id,
        notes=f'Requested {requested_quantity:g} {resource.unit} from resource listing {resource.id}.'
    )
    create_notification(
        user_id=resource.donor_id,
        title='New Volunteer Resource Request',
        message=f'{user.full_name} requested {requested_quantity:g} {resource.unit} of your {resource.category} listing.',
        link=url_for('donations.donor_dashboard')
    )
    db.session.commit()
    flash('Your item request was sent to the donor for approval.', 'success')
    return redirect(url_for('volunteers.volunteer_dashboard'))


@volunteers_bp.route('/resource-requests/<int:resource_request_id>/status', methods=['POST'])
@role_required('volunteer', 'admin')
def update_resource_request_status(resource_request_id):
    """Let the requesting volunteer track approved items through delivery."""
    resource_request = ResourceRequest.query.get_or_404(resource_request_id)
    user = g.current_user
    if user.role != 'admin' and resource_request.volunteer_id != user.id:
        flash('You can only update your own item requests.', 'danger')
        return redirect(url_for('volunteers.volunteer_dashboard'))

    new_status = request.form.get('new_status', '').strip()
    allowed_transitions = {'Approved': 'Collected', 'Collected': 'Delivered'}
    if allowed_transitions.get(resource_request.status) != new_status:
        flash('That item request status change is not allowed.', 'danger')
        return redirect(url_for('volunteers.volunteer_dashboard'))

    previous_status = resource_request.status
    resource_request.status = new_status
    record_status_change(
        entity_type='ResourceRequest',
        entity_id=resource_request.id,
        previous_status=previous_status,
        new_status=new_status,
        changed_by_id=user.id,
        notes=f'Updated by volunteer {user.full_name}.'
    )
    create_notification(
        user_id=resource_request.resource.donor_id,
        title=f'Resource Request {new_status}',
        message=f'{user.full_name} marked the request for {resource_request.resource.category} as {new_status.lower()}.',
        link=url_for('donations.donor_dashboard')
    )
    db.session.commit()
    flash(f'Item request marked {new_status.lower()}.', 'success')
    return redirect(url_for('volunteers.volunteer_dashboard'))


@volunteers_bp.route('/accept/<int:request_id>', methods=['POST'])
@role_required('volunteer', 'admin')
def accept_request(request_id):
    """
    WORKFLOW D: Duplicate Acceptance Prevention.
    Uses an atomic database transaction with row-level locking (with_for_update)
    to guarantee that only ONE volunteer can successfully accept an open request.
    """
    user = g.current_user

    try:
        # Atomic query: Lock the row and check that status is STILL Pending and unassigned
        req = HelpRequest.query.filter_by(
            id=request_id,
            status='Pending',
            assigned_volunteer_id=None
        ).with_for_update().first()

        if not req:
            db.session.rollback()
            flash("Sorry! This request was just accepted by another volunteer or is no longer available.", "warning")
            return redirect(url_for('volunteers.volunteer_dashboard'))

        # Assign task to current volunteer
        req.assigned_volunteer_id = user.id
        req.status = 'Accepted'

        # Record audit trail
        record_status_change(
            entity_type='HelpRequest',
            entity_id=req.id,
            previous_status='Pending',
            new_status='Accepted',
            changed_by_id=user.id,
            notes=f"Accepted by volunteer {user.full_name} ({user.email})"
        )

        # Notify the Help Seeker
        create_notification(
            user_id=req.seeker_id,
            title="Volunteer Accepted Your Request!",
            message=f"{user.full_name} has accepted your request '{req.title}'. They will coordinate assistance shortly.",
            link=url_for('help_requests.view_request', request_id=req.id)
        )

        db.session.commit()
        flash(f"You have successfully accepted the task: '{req.title}'. Thank you for supporting your community!", "success")
        return redirect(url_for('help_requests.view_request', request_id=req.id))

    except Exception as e:
        db.session.rollback()
        flash("A database concurrency conflict occurred. Please try again.", "danger")
        return redirect(url_for('volunteers.volunteer_dashboard'))


@volunteers_bp.route('/update-status/<int:request_id>', methods=['POST'])
@role_required('volunteer', 'admin')
def update_task_status(request_id):
    """
    Update status of an assigned task.
    Enforces that volunteers can ONLY modify tasks assigned to themselves.
    Valid transitions: Accepted -> In Progress -> Completed (or release back to Pending).
    """
    req = HelpRequest.query.get_or_404(request_id)
    user = g.current_user
    is_assignee = (user.id == req.assigned_volunteer_id)
    is_admin = user.is_admin

    if not (is_assignee or is_admin):
        flash("Unauthorized: You cannot update status for a task assigned to someone else.", "danger")
        return redirect(url_for('volunteers.volunteer_dashboard'))

    new_status = request.form.get('new_status', '').strip()
    notes = request.form.get('notes', '').strip()

    if new_status == 'Completed':
        flash("Tasks must be confirmed by the Help Seeker before they can be completed.", "warning")
        return redirect(url_for('help_requests.view_request', request_id=req.id))

    if new_status == 'awaiting_confirmation':
        completion_note = request.form.get('completion_note', '').strip()
        if not user.is_volunteer or not is_assignee:
            flash("Only the assigned volunteer can submit a task for confirmation.", "danger")
            return redirect(url_for('help_requests.view_request', request_id=req.id))
        if len(completion_note) > 2000:
            flash("Completion notes must be 2,000 characters or fewer.", "danger")
            return redirect(url_for('help_requests.view_request', request_id=req.id))

        completed_at = datetime.now(timezone.utc)
        changed = HelpRequest.query.filter_by(
            id=req.id,
            status='In Progress',
            assigned_volunteer_id=user.id
        ).update({
            HelpRequest.status: 'awaiting_confirmation',
            HelpRequest.volunteer_completed_at: completed_at,
            HelpRequest.completion_note: completion_note or None
        }, synchronize_session=False)
        if changed != 1:
            db.session.rollback()
            flash("This task has already changed and cannot be submitted again.", "warning")
            return redirect(url_for('help_requests.view_request', request_id=req.id))

        record_status_change(
            entity_type='HelpRequest',
            entity_id=req.id,
            previous_status='In Progress',
            new_status='awaiting_confirmation',
            changed_by_id=user.id,
            notes=completion_note or 'Volunteer reported the task complete.'
        )
        create_notification(
            user_id=req.seeker_id,
            title="Please Confirm Your Help Request",
            message=f"{user.full_name} marked '{req.title}' as completed. Please confirm whether you received the help.",
            link=url_for('help_requests.view_request', request_id=req.id)
        )
        db.session.commit()
        flash("The task is awaiting Help Seeker confirmation.", "success")
        return redirect(url_for('help_requests.view_request', request_id=req.id))

    is_valid, reason = validate_request_transition(
        current_status=req.status,
        new_status=new_status,
        user_role=user.role,
        is_owner=False,
        is_assignee=is_assignee
    )

    if not is_valid:
        flash(f"Status transition rejected: {reason}", "danger")
        return redirect(url_for('help_requests.view_request', request_id=req.id))

    previous_status = req.status
    req.status = new_status

    # If volunteer releases the task back to Pending
    if new_status == 'Pending':
        req.assigned_volunteer_id = None
        notify_msg = f"{user.full_name} had to release your task '{req.title}' back to the community pool for other volunteers."
    elif new_status == 'In Progress':
        notify_msg = f"{user.full_name} has started working on your request '{req.title}'."
    else:
        notify_msg = f"Task '{req.title}' status changed to {new_status}."

    # Record audit log
    record_status_change(
        entity_type='HelpRequest',
        entity_id=req.id,
        previous_status=previous_status,
        new_status=new_status,
        changed_by_id=user.id,
        notes=notes or f"Updated by volunteer {user.full_name}"
    )

    # Notify seeker
    create_notification(
        user_id=req.seeker_id,
        title=f"Task Status Update: {new_status}",
        message=notify_msg,
        link=url_for('help_requests.view_request', request_id=req.id)
    )

    db.session.commit()
    flash(f"Task status updated to '{new_status}'.", "success")
    return redirect(url_for('help_requests.view_request', request_id=req.id))
