import os
from flask import Flask, render_template, session, g
from sqlalchemy import or_
from config import config_by_name
from extensions import db, csrf
from models import User, Notification, EmergencyEvent, HelpRequest, ResourceListing, Message, Conversation, SERVICE_CATEGORIES
from helpers import get_active_emergency


def create_app(config_name=None):
    """Application factory for Community Help Connect."""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')
    if config_name == 'production' and not os.getenv('SECRET_KEY'):
        raise RuntimeError('SECRET_KEY must be configured in the environment for production.')

    app = Flask(__name__)
    config_obj = config_by_name.get(config_name, config_by_name['default'])
    app.config.from_object(config_obj)
    if config_name == 'production':
        app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)

    # Register Blueprints
    from auth import auth_bp
    from help_requests import help_requests_bp
    from volunteers import volunteers_bp
    from donations import donations_bp
    from admin import admin_bp
    from messaging import messaging_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(help_requests_bp, url_prefix='/requests')
    app.register_blueprint(volunteers_bp, url_prefix='/volunteers')
    app.register_blueprint(donations_bp, url_prefix='/donations')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(messaging_bp, url_prefix='/messages')

    # Load current user before each request
    @app.before_request
    def load_logged_in_user():
        user_id = session.get('user_id')
        if user_id:
            g.current_user = db.session.get(User, user_id)
        else:
            g.current_user = None

    # Context processors to inject global data into templates
    @app.context_processor
    def inject_global_template_data():
        active_emergency = None
        unread_notifications_count = 0
        unread_message_count = 0
        try:
            active_emergency = get_active_emergency()
            if g.current_user:
                unread_notifications_count = Notification.query.filter_by(
                    user_id=g.current_user.id,
                    is_read=False
                ).count()
                if g.current_user.role in ('help_seeker', 'donor', 'volunteer'):
                    unread_message_count = Message.query.join(Conversation).filter(
                        Message.sender_id != g.current_user.id,
                        Message.is_read.is_(False),
                        or_(
                            Conversation.help_seeker_id == g.current_user.id,
                            Conversation.donor_id == g.current_user.id
                        )
                    ).count()
        except Exception:
            # Handle situations before database tables are created
            pass

        return {
            'active_emergency': active_emergency,
            'unread_notifications_count': unread_notifications_count,
            'unread_message_count': unread_message_count,
            'current_user': getattr(g, 'current_user', None),
            'SERVICE_CATEGORIES': SERVICE_CATEGORIES
        }

    # Top-level public routes
    @app.route('/')
    def index():
        """Home Page (Page 1): Introduction, categories, workflows, and disclaimers."""
        open_requests_count = 0
        active_resources_count = 0
        total_volunteers_count = 0
        try:
            open_requests_count = HelpRequest.query.filter_by(status='Pending').count()
            active_resources_count = ResourceListing.query.filter_by(status='Available').count()
            total_volunteers_count = User.query.filter_by(role='volunteer', is_suspended=False).count()
        except Exception:
            pass

        return render_template(
            'index.html',
            open_requests_count=open_requests_count,
            active_resources_count=active_resources_count,
            total_volunteers_count=total_volunteers_count
        )

    @app.route('/services')
    def services():
        """Detailed overview of the 6 community service categories."""
        return render_template('services.html')

    @app.route('/how-it-works')
    def how_it_works():
        """Step-by-step guidance for Help Seekers, Volunteers, and Donors."""
        return render_template('how_it_works.html')

    # Global Error Handlers
    @app.errorhandler(400)
    def bad_request_error(e):
        return render_template('error.html', error_code=400, title="Bad Request", message="Your request could not be processed, possibly due to an invalid or expired form token."), 400

    @app.errorhandler(403)
    def forbidden_error(e):
        return render_template('error.html', error_code=403, title="Access Forbidden", message="You do not have permission to access this resource or administrative page."), 403

    @app.errorhandler(404)
    def not_found_error(e):
        return render_template('error.html', error_code=404, title="Page Not Found", message="The page or record you requested does not exist or may have been moved."), 404

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return render_template('error.html', error_code=500, title="Internal Server Error", message="A server-side error occurred. The database transaction was safely rolled back."), 500

    return app


if __name__ == '__main__':
    app = create_app()
    # Runs locally on Windows, default port 5000
    app.run(host='127.0.0.1', port=5000, debug=True)
