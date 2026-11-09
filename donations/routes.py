from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, request, g, abort
from sqlalchemy import func, update
from sqlalchemy.orm import joinedload
from extensions import db
from models import ResourceListing, ResourceRequest, StatusHistory, User, Conversation
from forms import ResourceListingForm, StatusUpdateForm
from decorators import login_required, role_required
from helpers import (
    record_status_change, validate_resource_transition, broadcast_to_volunteers,
    create_notification, withdraw_expired_resources
)
from . import donations_bp


@donations_bp.route('/dashboard')
@role_required('donor', 'admin')
def donor_dashboard():
    """
    Donor Dashboard displaying active resource listings, 
    automatic expiry auditing, and management controls.
    """
    user = g.current_user
    status_filter = request.args.get('status', '').strip()

    if withdraw_expired_resources(donor_id=user.id):
        db.session.commit()

    resource_counts = dict(db.session.query(
        ResourceListing.status,
        func.count(ResourceListing.id)
    ).filter_by(donor_id=user.id).group_by(ResourceListing.status).all())
    total_resources = sum(resource_counts.values())

    listings_query = ResourceListing.query.filter_by(donor_id=user.id)
    if status_filter in ['Available', 'Reserved', 'Collected', 'Distributed', 'Withdrawn']:
        listings_query = listings_query.filter_by(status=status_filter)
    listings_page = listings_query.order_by(
        ResourceListing.created_at.desc()
    ).paginate(
        page=request.args.get('listings_page', 1, type=int) or 1,
        per_page=20,
        error_out=False
    )
    resource_requests_page = ResourceRequest.query.options(
        joinedload(ResourceRequest.resource),
        joinedload(ResourceRequest.volunteer)
    ).join(ResourceListing).filter(
        ResourceListing.donor_id == user.id
    ).order_by(ResourceRequest.created_at.desc()).paginate(
        page=request.args.get('resource_requests_page', 1, type=int) or 1,
        per_page=20,
        error_out=False
    )
    pending_resource_requests_count = ResourceRequest.query.join(ResourceListing).filter(
        ResourceListing.donor_id == user.id,
        ResourceRequest.status == 'Pending'
    ).count()
    conversation_count = Conversation.query.filter_by(donor_id=user.id).count()

    return render_template(
        'donor_dashboard.html',
        listings=listings_page.items,
        listings_page=listings_page,
        total_resources=total_resources,
        available_count=resource_counts.get('Available', 0),
        distributed_count=resource_counts.get('Distributed', 0),
        reserved_count=resource_counts.get('Reserved', 0),
        resource_requests=resource_requests_page.items,
        resource_requests_page=resource_requests_page,
        pending_resource_requests_count=pending_resource_requests_count,
        conversation_count=conversation_count,
        current_filter=status_filter
    )


@donations_bp.route('/resource-requests/<int:resource_request_id>/decision', methods=['POST'])
@role_required('donor', 'admin')
def decide_resource_request(resource_request_id):
    """Approve or reject a volunteer request for the donor's own listing."""
    resource_request = ResourceRequest.query.filter_by(id=resource_request_id).with_for_update().first_or_404()
    resource = ResourceListing.query.filter_by(id=resource_request.resource_id).with_for_update().first_or_404()
    user = g.current_user

    if not user.is_admin and resource.donor_id != user.id:
        flash('Only the listing donor can respond to this item request.', 'danger')
        return redirect(url_for('donations.donor_dashboard'))
    if resource_request.status != 'Pending':
        flash('This item request has already been handled.', 'warning')
        return redirect(url_for('donations.donor_dashboard'))

    decision = request.form.get('decision', '').strip().lower()
    if decision == 'approve':
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
            flash('This resource has expired and can no longer be approved.', 'warning')
            return redirect(url_for('donations.donor_dashboard'))

        if resource.status != 'Available':
            flash('This resource listing is no longer available.', 'warning')
            return redirect(url_for('donations.donor_dashboard'))

        reservation = db.session.execute(
            update(ResourceListing)
            .where(
                ResourceListing.id == resource.id,
                ResourceListing.status == 'Available',
                ResourceListing.quantity >= resource_request.quantity
            )
            .values(quantity=ResourceListing.quantity - resource_request.quantity)
        )
        if reservation.rowcount != 1:
            db.session.rollback()
            flash('There is not enough stock remaining to approve this request.', 'warning')
            return redirect(url_for('donations.donor_dashboard'))
        new_status = 'Approved'
        db.session.expire(resource, ['quantity'])
    elif decision == 'reject':
        new_status = 'Rejected'
    else:
        flash('Choose Approve or Reject for this item request.', 'danger')
        return redirect(url_for('donations.donor_dashboard'))

    previous_status = resource_request.status
    resource_request.status = new_status
    record_status_change(
        entity_type='ResourceRequest',
        entity_id=resource_request.id,
        previous_status=previous_status,
        new_status=new_status,
        changed_by_id=user.id,
        notes=f'{new_status} by {user.full_name}.'
    )
    create_notification(
        user_id=resource_request.volunteer_id,
        title=f'Resource Request {new_status}',
        message=f'Your request for {resource_request.quantity:g} {resource.unit} of {resource.category} was {new_status.lower()}.',
        link=url_for('volunteers.volunteer_dashboard')
    )
    db.session.commit()
    flash(f'Item request {new_status.lower()}.', 'success')
    return redirect(url_for('donations.donor_dashboard'))


@donations_bp.route('/new', methods=['GET', 'POST'])
@role_required('donor', 'admin')
def new_resource():
    """Report a new available community resource."""
    form = ResourceListingForm()
    if request.method == 'GET' and not form.locality.data:
        form.locality.data = g.current_user.locality

    if form.validate_on_submit():
        avail_dt = None
        if form.available_until.data:
            avail_dt = datetime.combine(form.available_until.data, datetime.min.time()).replace(tzinfo=timezone.utc)

        exp_dt = None
        if form.expiry_date.data:
            exp_dt = datetime.combine(form.expiry_date.data, datetime.min.time()).replace(tzinfo=timezone.utc)

        res = ResourceListing(
            donor_id=g.current_user.id,
            category=form.category.data,
            name=form.name.data.strip(),
            description=form.description.data.strip(),
            quantity=float(form.quantity.data),
            unit=form.unit.data.strip(),
            locality=form.locality.data.strip(),
            available_until=avail_dt,
            expiry_date=exp_dt,
            pickup_instructions=form.pickup_instructions.data.strip() if form.pickup_instructions.data else None,
            contact_preference=form.contact_preference.data,
            status='Available'
        )
        db.session.add(res)
        db.session.flush()

        # Audit history log
        record_status_change(
            entity_type='ResourceListing',
            entity_id=res.id,
            previous_status='Created',
            new_status='Available',
            changed_by_id=g.current_user.id,
            notes='Initial resource offer published'
        )

        # Notify volunteers in the locality
        broadcast_to_volunteers(
            locality=(form.locality.data or '').strip(),
            title=f"New Resource Available: {res.category}",
            message=f"{res.quantity} {res.unit} reported available in {res.locality}.",
            link=url_for('donations.view_resource', resource_id=res.id)
        )

        db.session.commit()
        flash("Thank you! Your resource listing is now visible to community coordinators.", "success")
        return redirect(url_for('donations.donor_dashboard'))

    return render_template('resource_form.html', form=form)


@donations_bp.route('/<int:resource_id>')
@login_required
def view_resource(resource_id):
    """View resource listing details with privacy controls and audit timeline."""
    resource = ResourceListing.query.get_or_404(resource_id)
    
    # Auto-check expiry on access
    if resource.auto_check_expiry():
        record_status_change(
            entity_type='ResourceListing',
            entity_id=resource.id,
            previous_status='Available',
            new_status='Withdrawn',
            changed_by_id=resource.donor_id,
            notes='Automatically updated on view due to passed expiry date.'
        )
        db.session.commit()

    history = StatusHistory.query.filter_by(entity_type='ResourceListing', entity_id=resource_id)\
        .order_by(StatusHistory.created_at.desc()).all()

    user = g.current_user
    is_owner = (user.id == resource.donor_id)
    is_admin = user.is_admin

    # Contact visibility logic
    can_view_contact = False
    if is_owner or is_admin:
        can_view_contact = True
    elif resource.contact_preference == 'share_always':
        can_view_contact = True
    elif resource.contact_preference == 'share_on_accept' and user.role in ['volunteer', 'admin']:
        can_view_contact = True

    return render_template(
        'resource_detail.html',
        resource=resource,
        history=history,
        is_owner=is_owner,
        can_view_contact=can_view_contact
    )


@donations_bp.route('/<int:resource_id>/status', methods=['POST'])
@login_required
def update_resource_status(resource_id):
    """Update resource listing status with transition validation."""
    resource = ResourceListing.query.get_or_404(resource_id)
    user = g.current_user
    is_owner = (user.id == resource.donor_id)
    is_admin = user.is_admin

    if not (is_owner or is_admin):
        flash("Unauthorized: Only the donor or administrator can update this resource.", "danger")
        return redirect(url_for('donations.view_resource', resource_id=resource.id))

    new_status = request.form.get('new_status', '').strip()
    notes = request.form.get('notes', '').strip()

    is_valid, reason = validate_resource_transition(
        current_status=resource.status,
        new_status=new_status,
        user_role=user.role,
        is_owner=is_owner
    )

    if not is_valid:
        flash(f"Status transition rejected: {reason}", "danger")
        return redirect(url_for('donations.view_resource', resource_id=resource.id))

    prev_status = resource.status
    resource.status = new_status

    record_status_change(
        entity_type='ResourceListing',
        entity_id=resource.id,
        previous_status=prev_status,
        new_status=new_status,
        changed_by_id=user.id,
        notes=notes or f"Updated by {user.full_name}"
    )

    db.session.commit()
    flash(f"Resource status updated to '{new_status}'.", "success")
    return redirect(url_for('donations.view_resource', resource_id=resource.id))


@donations_bp.route('/<int:resource_id>/withdraw', methods=['POST'])
@login_required
def withdraw_resource(resource_id):
    """Convenience action to withdraw an active resource listing."""
    resource = ResourceListing.query.get_or_404(resource_id)
    user = g.current_user
    is_owner = (user.id == resource.donor_id)
    is_admin = user.is_admin

    if not (is_owner or is_admin):
        flash("Unauthorized: You do not have permission to withdraw this resource.", "danger")
        return redirect(url_for('donations.view_resource', resource_id=resource.id))

    prev_status = resource.status
    resource.status = 'Withdrawn'

    record_status_change(
        entity_type='ResourceListing',
        entity_id=resource.id,
        previous_status=prev_status,
        new_status='Withdrawn',
        changed_by_id=user.id,
        notes="Listing withdrawn by donor" if is_owner else "Listing withdrawn by administrator"
    )

    db.session.commit()
    flash("Resource listing has been withdrawn.", "info")
    return redirect(url_for('donations.donor_dashboard' if is_owner else 'admin.dashboard'))
