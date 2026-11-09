from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


# 6 Defined Service Categories
SERVICE_CATEGORIES = [
    'Essential Items Assistance',
    'Surplus Food Sharing',
    'Medical Assistance',
    'Transportation Assistance',
    'Emergency Relief',
    'Lost and Found Assistance'
]

# Urgency Levels
URGENCY_LEVELS = ['Normal', 'Urgent', 'Critical']

# Request Statuses
REQUEST_STATUSES = [
    'Pending', 'Accepted', 'In Progress', 'awaiting_confirmation',
    'disputed', 'Completed', 'Cancelled'
]

# Resource Statuses
RESOURCE_STATUSES = ['Available', 'Reserved', 'Collected', 'Distributed', 'Withdrawn']

# Roles
USER_ROLES = ['help_seeker', 'volunteer', 'donor', 'admin']


class User(db.Model):
    """User Model representing Help Seekers, Volunteers, Donors, and Administrators."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False, default='')
    locality = db.Column(db.String(100), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default='help_seeker', index=True)
    is_verified = db.Column(db.Boolean, default=True, nullable=False)
    is_suspended = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    help_requests_created = db.relationship(
        'HelpRequest',
        foreign_keys='HelpRequest.seeker_id',
        backref='seeker',
        lazy=True,
        cascade='all, delete-orphan'
    )
    assigned_tasks = db.relationship(
        'HelpRequest',
        foreign_keys='HelpRequest.assigned_volunteer_id',
        backref='assigned_volunteer',
        lazy=True
    )
    resources_donated = db.relationship(
        'ResourceListing',
        backref='donor',
        lazy=True,
        cascade='all, delete-orphan'
    )
    resource_requests = db.relationship(
        'ResourceRequest',
        backref='volunteer',
        lazy=True,
        cascade='all, delete-orphan'
    )
    notifications = db.relationship(
        'Notification',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan'
    )
    volunteer_verification = db.relationship(
        'VolunteerVerification',
        foreign_keys='VolunteerVerification.volunteer_id',
        backref='volunteer',
        uselist=False,
        cascade='all, delete-orphan'
    )
    status_changes = db.relationship(
        'StatusHistory',
        backref='changed_by',
        lazy=True
    )

    def set_password(self, password: str) -> None:
        """Hash and save user password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify hashed password."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    @property
    def is_volunteer(self) -> bool:
        return self.role == 'volunteer'

    @property
    def is_help_seeker(self) -> bool:
        return self.role == 'help_seeker'

    @property
    def is_donor(self) -> bool:
        return self.role == 'donor'

    def __repr__(self) -> str:
        return f'<User {self.id}: {self.email} ({self.role})>'


class HelpRequest(db.Model):
    """Help Request model for community members seeking assistance."""
    __tablename__ = 'help_requests'

    id = db.Column(db.Integer, primary_key=True)
    seeker_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    category = db.Column(db.String(60), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    urgency = db.Column(db.String(20), nullable=False, default='Normal', index=True)
    locality = db.Column(db.String(100), nullable=False, index=True)
    deadline = db.Column(db.DateTime, nullable=True)
    contact_preference = db.Column(db.String(30), nullable=False, default='share_on_accept')
    status = db.Column(db.String(30), nullable=False, default='Pending', index=True)
    assigned_volunteer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    volunteer_completed_at = db.Column(db.DateTime, nullable=True)
    completion_note = db.Column(db.Text, nullable=True)
    seeker_confirmed_at = db.Column(db.DateTime, nullable=True)
    confirmed_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    dispute_reason = db.Column(db.Text, nullable=True)
    disputed_at = db.Column(db.DateTime, nullable=True)
    rating = db.Column(db.Integer, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    @property
    def age_in_hours(self) -> float:
        """Returns the age of the request in hours."""
        if not self.created_at:
            return 0
        now = datetime.now(timezone.utc)
        created = self.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        diff = now - created
        return round(diff.total_seconds() / 3600, 1)

    @property
    def is_open(self) -> bool:
        """A request is open for volunteers only when Pending and unassigned."""
        return self.status == 'Pending' and self.assigned_volunteer_id is None

    def __repr__(self) -> str:
        return f'<HelpRequest {self.id}: "{self.title}" [{self.status}]>'


class ResourceListing(db.Model):
    """Resource Listing model for donated supplies, meals, kits, and equipment."""
    __tablename__ = 'resource_listings'

    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    category = db.Column(db.String(60), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=True)
    description = db.Column(db.Text, nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=1.0)
    unit = db.Column(db.String(30), nullable=False, default='units')
    locality = db.Column(db.String(100), nullable=False, index=True)
    available_until = db.Column(db.DateTime, nullable=True)
    expiry_date = db.Column(db.DateTime, nullable=True)
    pickup_instructions = db.Column(db.Text, nullable=True)
    contact_preference = db.Column(db.String(30), nullable=False, default='share_always')
    status = db.Column(db.String(30), nullable=False, default='Available', index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    @property
    def is_expired(self) -> bool:
        """Checks if the resource has passed its expiry date or availability window."""
        now = datetime.now(timezone.utc)
        if self.expiry_date:
            exp = self.expiry_date if self.expiry_date.tzinfo else self.expiry_date.replace(tzinfo=timezone.utc)
            if now > exp:
                return True
        if self.available_until:
            avail = self.available_until if self.available_until.tzinfo else self.available_until.replace(tzinfo=timezone.utc)
            if now > avail:
                return True
        return False

    def auto_check_expiry(self) -> bool:
        """Automatically mark listing as Withdrawn or Expired if past date."""
        if self.status == 'Available' and self.is_expired:
            self.status = 'Withdrawn'
            return True
        return False

    def __repr__(self) -> str:
        return f'<ResourceListing {self.id}: {self.category} ({self.quantity} {self.unit}) [{self.status}]>'


class ResourceRequest(db.Model):
    """Volunteer request for a quantity from an existing donor resource listing."""
    __tablename__ = 'resource_requests'

    id = db.Column(db.Integer, primary_key=True)
    resource_id = db.Column(db.Integer, db.ForeignKey('resource_listings.id', ondelete='CASCADE'), nullable=False, index=True)
    volunteer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Pending', index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    resource = db.relationship('ResourceListing', backref=db.backref('requests', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self) -> str:
        return f'<ResourceRequest {self.id}: Resource {self.resource_id} ({self.quantity}) [{self.status}]>'


class Notification(db.Model):
    """In-app notifications for users, volunteers, and administrators."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f'<Notification {self.id} for User {self.user_id}>'


class VolunteerVerification(db.Model):
    """Private document metadata and current review state for a volunteer."""
    __tablename__ = 'volunteer_verifications'

    id = db.Column(db.Integer, primary_key=True)
    volunteer_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, unique=True, index=True
    )
    id_document_type = db.Column(db.String(40), nullable=True)
    id_document_path = db.Column(db.String(500), nullable=True)
    id_document_name = db.Column(db.String(255), nullable=True)
    id_document_content_type = db.Column(db.String(100), nullable=True)
    id_document_size = db.Column(db.Integer, nullable=True)
    certificate_path = db.Column(db.String(500), nullable=True)
    certificate_name = db.Column(db.String(255), nullable=True)
    certificate_content_type = db.Column(db.String(100), nullable=True)
    certificate_size = db.Column(db.Integer, nullable=True)
    volunteering_experience = db.Column(db.Text, nullable=True)
    verification_status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    verification_submitted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    verification_reviewed_at = db.Column(db.DateTime, nullable=True)
    verification_reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    verification_notes = db.Column(db.Text, nullable=True)

    reviewer = db.relationship('User', foreign_keys=[verification_reviewed_by])
    history = db.relationship(
        'VolunteerVerificationHistory',
        backref='verification',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='VolunteerVerificationHistory.created_at.desc()'
    )


class VolunteerVerificationHistory(db.Model):
    """Audit history for volunteer review and resubmission actions."""
    __tablename__ = 'volunteer_verification_history'

    id = db.Column(db.Integer, primary_key=True)
    verification_id = db.Column(
        db.Integer, db.ForeignKey('volunteer_verifications.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    action = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    actor = db.relationship('User', foreign_keys=[actor_id])


class Conversation(db.Model):
    """Private conversation between a resource donor and another participant."""
    __tablename__ = 'conversations'

    id = db.Column(db.Integer, primary_key=True)
    # This legacy participant column also stores volunteer IDs in donor-volunteer threads.
    help_seeker_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    resource_listing_id = db.Column(
        db.Integer, db.ForeignKey('resource_listings.id', ondelete='SET NULL'), nullable=True, index=True
    )
    status = db.Column(db.String(20), nullable=False, default='open', index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    help_seeker = db.relationship('User', foreign_keys=[help_seeker_id])
    donor = db.relationship('User', foreign_keys=[donor_id])
    resource_listing = db.relationship('ResourceListing')
    messages = db.relationship(
        'Message', backref='conversation', lazy=True,
        cascade='all, delete-orphan', order_by='Message.created_at.asc()'
    )


class Message(db.Model):
    """A message visible only to the two members of its conversation."""
    __tablename__ = 'messages'
    __table_args__ = (
        db.Index('ix_messages_conversation_id_id', 'conversation_id', 'id'),
        db.Index('ix_messages_conversation_unread', 'conversation_id', 'is_read', 'sender_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey('conversations.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    message_text = db.Column(db.String(2000), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    read_at = db.Column(db.DateTime, nullable=True)

    sender = db.relationship('User')


class ConversationReport(db.Model):
    """User reports about suspicious conversations, available to administrators."""
    __tablename__ = 'conversation_reports'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey('conversations.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    reason = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    conversation = db.relationship('Conversation')
    reporter = db.relationship('User', foreign_keys=[reporter_id])


class EmergencyEvent(db.Model):
    """Emergency Event coordination record managed by Administrators."""
    __tablename__ = 'emergency_events'

    id = db.Column(db.Integer, primary_key=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    emergency_type = db.Column(db.String(100), nullable=False)
    affected_locality = db.Column(db.String(100), nullable=False, index=True)
    severity = db.Column(db.String(30), nullable=False, default='Severe')
    description = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    activated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    deactivated_at = db.Column(db.DateTime, nullable=True)

    creator = db.relationship('User', foreign_keys=[created_by_id])

    def __repr__(self) -> str:
        return f'<EmergencyEvent {self.id}: {self.emergency_type} ({self.affected_locality}) Active={self.is_active}>'


class StatusHistory(db.Model):
    """Audit log capturing every status change for requests and resources."""
    __tablename__ = 'status_history'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(30), nullable=False, index=True)  # 'HelpRequest' or 'ResourceListing'
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    previous_status = db.Column(db.String(30), nullable=False)
    new_status = db.Column(db.String(30), nullable=False)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f'<StatusHistory {self.entity_type}#{self.entity_id}: {self.previous_status} -> {self.new_status}>'
