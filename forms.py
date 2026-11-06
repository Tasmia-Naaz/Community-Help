from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SelectField, TextAreaField,
    FloatField, DateField, SubmitField, FileField
)
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, ValidationError, NumberRange, Optional
)

# Constants imported at module level (no app context needed)
SERVICE_CATEGORIES = [
    'Essential Items Assistance',
    'Surplus Food Sharing',
    'Medical Assistance',
    'Transportation Assistance',
    'Emergency Relief',
    'Lost and Found Assistance'
]
URGENCY_LEVELS = ['Normal', 'Urgent', 'Critical']


class RegistrationForm(FlaskForm):
    """User Registration Form with strict validation and no public admin option."""
    full_name = StringField('Full Name', validators=[
        DataRequired(message="Full name is required."),
        Length(min=2, max=120, message="Name must be between 2 and 120 characters.")
    ])
    email = StringField('Email Address', validators=[
        DataRequired(message="Email is required."),
        Email(message="Please enter a valid email address."),
        Length(max=120)
    ])
    phone = StringField('Phone Number', validators=[
        DataRequired(message="Phone number is required."),
        Length(min=7, max=30, message="Please enter a valid contact phone number.")
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required."),
        Length(min=6, max=128, message="Password must be at least 6 characters.")
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message="Please confirm your password."),
        EqualTo('password', message="Passwords must match.")
    ])
    locality = StringField('Locality / Neighborhood / City', validators=[
        DataRequired(message="Locality is required for proximity matching."),
        Length(min=2, max=100, message="Locality must be between 2 and 100 characters.")
    ])
    role = SelectField('Register As', choices=[
        ('help_seeker', 'Help Seeker (I need community assistance)'),
        ('volunteer', 'Volunteer (I want to help neighbors in need)'),
        ('donor', 'Resource Donor (I have supplies, food, or gear to share)')
    ], validators=[DataRequired(message="Please select your role.")])
    id_document_type = SelectField('ID Document Type', choices=[
        ('', 'Select document type'),
        ('national_id', 'National ID'),
        ('passport', 'Passport'),
        ('drivers_license', "Driver's license"),
        ('other', 'Other government-issued ID')
    ], validators=[Optional()])
    id_document = FileField('ID Document (PDF, JPG, JPEG, or PNG)')
    volunteer_certificate = FileField('Volunteer Certificate (Optional)')
    volunteering_experience = TextAreaField('Volunteering Experience (Optional)', validators=[
        Optional(),
        Length(max=2000, message="Experience must be 2000 characters or fewer.")
    ])
    submit = SubmitField('Create Account')

    def validate_email(self, field):
        """Ensure email is unique across the platform."""
        from models import User
        user = User.query.filter_by(email=(field.data or '').strip().lower()).first()
        if user:
            raise ValidationError("This email address is already registered. Please login instead.")


class LoginForm(FlaskForm):
    """User Login Form with email and password."""
    email = StringField('Email Address', validators=[
        DataRequired(message="Email is required."),
        Email(message="Please enter a valid email address.")
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required.")
    ])
    submit = SubmitField('Login')


class HelpRequestForm(FlaskForm):
    """Help Request Submission Form."""
    category = SelectField('Service Category', choices=[(c, c) for c in SERVICE_CATEGORIES], validators=[
        DataRequired(message="Please select a service category.")
    ])
    title = StringField('Request Title', validators=[
        DataRequired(message="A brief title is required."),
        Length(min=3, max=150, message="Title must be between 3 and 150 characters.")
    ])
    description = TextAreaField('Detailed Description', validators=[
        DataRequired(message="Please describe the assistance needed in detail."),
        Length(min=10, max=2000, message="Description must be between 10 and 2000 characters.")
    ])
    urgency = SelectField('Urgency Level', choices=[(u, u) for u in URGENCY_LEVELS], validators=[
        DataRequired(message="Please select an urgency level.")
    ])
    locality = StringField('Locality / Area', validators=[
        DataRequired(message="Locality is required for matching nearby volunteers."),
        Length(min=2, max=100)
    ])
    deadline = DateField('Needed By (Optional)', validators=[Optional()])
    contact_preference = SelectField('Contact Sharing Preference', choices=[
        ('share_on_accept', 'Share phone & email only after a volunteer accepts this task (Recommended)'),
        ('share_always', 'Share contact details openly with all community members'),
        ('hide_private', 'Keep private (Coordinate solely through verified platform updates)')
    ], validators=[DataRequired()])
    submit = SubmitField('Submit Help Request')


class ResourceListingForm(FlaskForm):
    """Resource Listing Form for Donors."""
    category = SelectField('Resource Category', choices=[(c, c) for c in SERVICE_CATEGORIES], validators=[
        DataRequired(message="Please select a category.")
    ])
    name = StringField('Resource Name', validators=[
        DataRequired(message="Please provide a resource name."),
        Length(min=2, max=150)
    ])
    description = TextAreaField('Resource Description', validators=[
        DataRequired(message="Please provide a clear description of the items."),
        Length(min=5, max=2000)
    ])
    quantity = FloatField('Quantity', validators=[
        DataRequired(message="Quantity must be specified."),
        NumberRange(min=0.01, message="Quantity must be greater than zero.")
    ])
    unit = StringField('Unit (e.g. meals, boxes, kg, kits, units)', validators=[
        DataRequired(message="Unit of measurement is required."),
        Length(min=1, max=30)
    ], default='units')
    locality = StringField('Pickup Locality', validators=[
        DataRequired(message="Pickup locality is required."),
        Length(min=2, max=100)
    ])
    available_until = DateField('Available Until (Optional)', validators=[Optional()])
    expiry_date = DateField('Expiry / Best Before Date (Required for food/perishables)', validators=[Optional()])
    pickup_instructions = TextAreaField('Pickup & Handling Instructions', validators=[
        Optional(),
        Length(max=1000)
    ])
    contact_preference = SelectField('Contact Sharing Preference', choices=[
        ('share_always', 'Share contact details with verified community volunteers'),
        ('share_on_accept', 'Share contact details only upon resource reservation'),
        ('hide_private', 'Do not share contact details publicly')
    ], validators=[DataRequired()])
    submit = SubmitField('Publish Resource Listing')


class EmergencyEventForm(FlaskForm):
    """Administrator Emergency Mode Form."""
    emergency_type = StringField('Emergency Type (e.g. Flash Flood, Severe Storm, Heatwave)', validators=[
        DataRequired(message="Emergency type is required."),
        Length(min=3, max=100)
    ])
    affected_locality = StringField('Affected Locality / Zone', validators=[
        DataRequired(message="Affected locality is required."),
        Length(min=2, max=100)
    ])
    severity = SelectField('Severity Level', choices=[
        ('Low', 'Low - Advisory Alert'),
        ('Moderate', 'Moderate - Heightened Vigilance'),
        ('Severe', 'Severe - High Priority Community Response'),
        ('Catastrophic', 'Catastrophic - Full Mobilization Required')
    ], validators=[DataRequired()])
    description = TextAreaField('Emergency Description & Instructions', validators=[
        DataRequired(message="Detailed emergency instructions required."),
        Length(min=10, max=2000)
    ])
    submit = SubmitField('Declare & Broadcast Emergency')


class StatusUpdateForm(FlaskForm):
    """Generic Status Update Form with optional notes."""
    new_status = SelectField('Update Status', validators=[DataRequired()])
    notes = TextAreaField('Status Change Notes (Optional)', validators=[
        Optional(),
        Length(max=500)
    ])
    submit = SubmitField('Update Status')
