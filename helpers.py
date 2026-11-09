from datetime import datetime, timezone, timedelta
from flask import g, request
from sqlalchemy import or_
from extensions import db
from models import (
    Notification, StatusHistory, EmergencyEvent, HelpRequest, ResourceListing,
    User, VolunteerVerification
)

# In-memory dictionary for login rate limiting: {ip_or_email: [timestamp1, timestamp2, ...]}
_login_attempts = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_PERIOD_MINUTES = 15


def check_login_rate_limit(identifier):
    """
    Checks if too many failed login attempts have been made.
    Returns (is_allowed, minutes_remaining).
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=LOCKOUT_PERIOD_MINUTES)
    
    attempts = _login_attempts.get(identifier, [])
    # Filter attempts within the lockout window
    recent_attempts = [ts for ts in attempts if ts > cutoff]
    _login_attempts[identifier] = recent_attempts
    
    if len(recent_attempts) >= MAX_LOGIN_ATTEMPTS:
        oldest_attempt = min(recent_attempts)
        retry_after = (oldest_attempt + timedelta(minutes=LOCKOUT_PERIOD_MINUTES)) - now
        minutes_left = max(1, int(retry_after.total_seconds() / 60) + 1)
        return False, minutes_left
        
    return True, 0


def record_failed_login(identifier):
    """Record a failed login attempt for the given identifier."""
    now = datetime.now(timezone.utc)
    if identifier not in _login_attempts:
        _login_attempts[identifier] = []
    _login_attempts[identifier].append(now)


def clear_failed_logins(identifier):
    """Clear failed login attempts on successful login."""
    if identifier in _login_attempts:
        del _login_attempts[identifier]


def create_notification(user_id, title, message, link=None):
    """Create and persist an in-app notification for a specific user."""
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        link=link
    )
    db.session.add(notif)
    return notif


def broadcast_to_volunteers(locality, title, message, link=None):
    """
    Broadcasts an in-app notification to all active volunteers in a specific locality,
    or to all volunteers if locality is 'ALL'.
    """
    query = User.query.join(
        VolunteerVerification, User.id == VolunteerVerification.volunteer_id
    ).filter(
        User.role == 'volunteer',
        User.is_suspended.is_(False),
        VolunteerVerification.verification_status == 'approved'
    )
    if locality and locality.upper() != 'ALL':
        # Exact or case-insensitive locality match
        query = query.filter(User.locality.ilike(f"%{locality}%"))
        
    volunteers = query.all()
    count = 0
    for vol in volunteers:
        create_notification(vol.id, title, message, link)
        count += 1
    return count


def record_status_change(entity_type, entity_id, previous_status, new_status, changed_by_id, notes=None):
    """Record an audit trail entry in the StatusHistory table."""
    history = StatusHistory(
        entity_type=entity_type,
        entity_id=entity_id,
        previous_status=previous_status,
        new_status=new_status,
        changed_by_id=changed_by_id,
        notes=notes
    )
    db.session.add(history)
    return history


def withdraw_expired_resources(donor_id=None, category=None, locality=None):
    """Withdraw expired available listings and record their status changes."""
    now = datetime.now(timezone.utc)
    query = ResourceListing.query.filter_by(status='Available').filter(
        or_(
            ResourceListing.expiry_date < now,
            ResourceListing.available_until < now
        )
    )
    if donor_id is not None:
        query = query.filter_by(donor_id=donor_id)
    if category:
        query = query.filter(ResourceListing.category == category)
    if locality:
        query = query.filter(ResourceListing.locality.ilike(f'%{locality}%'))

    expired = query.with_for_update().all()
    changed = 0
    for resource in expired:
        if not resource.auto_check_expiry():
            continue
        record_status_change(
            entity_type='ResourceListing',
            entity_id=resource.id,
            previous_status='Available',
            new_status='Withdrawn',
            changed_by_id=resource.donor_id,
            notes='Automatically marked Withdrawn after resource availability expired.'
        )
        changed += 1
    return changed


def get_active_emergency():
    """Retrieve the latest active emergency event if one exists."""
    if getattr(g, '_active_emergency_loaded', False):
        return g._active_emergency

    g._active_emergency = EmergencyEvent.query.filter_by(
        is_active=True
    ).order_by(EmergencyEvent.activated_at.desc()).first()
    g._active_emergency_loaded = True
    return g._active_emergency


def validate_request_transition(current_status, new_status, user_role, is_owner=False, is_assignee=False):
    """
    Validates server-side whether a help request status transition is permitted.
    """
    if user_role == 'admin':
        return True, "Admin authorized"
        
    if current_status == new_status:
        return False, "Request is already in this status."

    # Seeker (Owner) transitions
    if is_owner:
        if current_status in ['Pending', 'Accepted'] and new_status == 'Cancelled':
            return True, "Owner can cancel unstarted request"
        if current_status == 'In Progress' and new_status == 'Cancelled':
            return True, "Owner cancelled in-progress request"
        return False, "Help seekers can only cancel their own requests."

    # Volunteer (Assignee) transitions
    if is_assignee:
        if current_status == 'Accepted' and new_status == 'In Progress':
            return True, "Volunteer started task"
        if current_status == 'In Progress' and new_status == 'awaiting_confirmation':
            return True, "Volunteer marked task as completed"
        if current_status in ['Accepted', 'In Progress'] and new_status == 'Pending':
            return True, "Volunteer released task back to community"
        return False, f"Volunteers cannot transition from {current_status} to {new_status}."

    return False, "Unauthorized to change status."


def validate_resource_transition(current_status, new_status, user_role, is_owner=False):
    """
    Validates server-side whether a resource listing status transition is permitted.
    """
    if user_role == 'admin':
        return True, "Admin authorized"

    if current_status == new_status:
        return False, "Resource is already in this status."

    # Donor (Owner) or Admin transitions
    if is_owner:
        allowed_from = {
            'Available': ['Reserved', 'Withdrawn'],
            'Reserved': ['Collected', 'Available', 'Withdrawn'],
            'Collected': ['Distributed', 'Withdrawn'],
            'Distributed': [],
            'Withdrawn': ['Available']  # Re-list if still valid
        }
        if new_status in allowed_from.get(current_status, []):
            return True, "Valid transition"
        return False, f"Cannot transition resource from {current_status} to {new_status}."

    return False, "Unauthorized to update resource status."


def calculate_matching_score(request_obj, volunteer_locality, active_emergency=None):
    """
    Transparent Rule-Based Matching Algorithm:
    - Urgency: Critical = +100, Urgent = +50, Normal = +10
    - Locality: Exact match = +40, partial match = +20
    - Emergency Boost: If request locality matches an active emergency zone = +60
    - Request Age: Older requests get +1 point per 2 hours (up to +20)
    """
    score = 0
    
    # 1. Urgency score
    urgency_map = {'Critical': 100, 'Urgent': 50, 'Normal': 10}
    score += urgency_map.get(request_obj.urgency, 10)
    
    # 2. Locality proximity
    if volunteer_locality and request_obj.locality:
        vol_loc = volunteer_locality.strip().lower()
        req_loc = request_obj.locality.strip().lower()
        if vol_loc == req_loc:
            score += 40
        elif vol_loc in req_loc or req_loc in vol_loc:
            score += 20
            
    # 3. Emergency zone boost
    if active_emergency and active_emergency.is_active:
        em_loc = active_emergency.affected_locality.strip().lower()
        req_loc = request_obj.locality.strip().lower()
        if em_loc == req_loc or em_loc in req_loc or req_loc in em_loc:
            score += 60
            
    # 4. Age factor (hours)
    age = request_obj.age_in_hours
    age_points = min(20, int(age / 2))
    score += age_points
    
    return score
