from functools import wraps
from flask import session, redirect, url_for, flash, g
from extensions import db
from models import User


def login_required(f):
    """Decorator ensuring that the user is logged into an active session and not suspended."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        
        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for('auth.login'))
            
        if user.is_suspended:
            session.clear()
            flash("Your account has been suspended by an administrator. Please contact support.", "danger")
            return redirect(url_for('auth.login'))
            
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """Decorator ensuring the user possesses one of the specified roles."""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            user = g.current_user
            if user.role not in allowed_roles:
                flash("Access denied: You do not have permission to view this resource.", "danger")
                # Redirect to user's appropriate role dashboard
                if user.role == 'help_seeker':
                    return redirect(url_for('help_requests.seeker_dashboard'))
                elif user.role == 'volunteer':
                    return redirect(url_for('volunteers.volunteer_dashboard'))
                elif user.role == 'donor':
                    return redirect(url_for('donations.donor_dashboard'))
                elif user.role == 'admin':
                    return redirect(url_for('admin.dashboard'))
                return redirect(url_for('index'))
            if user.role == 'volunteer':
                verification = user.volunteer_verification
                if not verification or verification.verification_status != 'approved':
                    flash("Volunteer features are available after administrator approval.", "info")
                    return redirect(url_for('auth.volunteer_verification_status'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Convenience decorator specifically for administrator-only routes."""
    return role_required('admin')(f)
