from datetime import datetime, timedelta, timezone

from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, or_, update
from sqlalchemy.orm import joinedload

from decorators import role_required
from extensions import db
from helpers import create_notification
from models import (
    Conversation, ConversationReport, Message, ResourceListing, ResourceRequest,
    User, VolunteerVerification
)
from . import messaging_bp


def _conversation_for_user(conversation_id, user):
    return Conversation.query.filter(
        Conversation.id == conversation_id,
        or_(
            Conversation.help_seeker_id == user.id,
            Conversation.donor_id == user.id
        )
    ).options(
        joinedload(Conversation.help_seeker),
        joinedload(Conversation.donor),
        joinedload(Conversation.resource_listing)
    ).first_or_404()


def _conversation_list(user):
    return Conversation.query.options(
        joinedload(Conversation.help_seeker),
        joinedload(Conversation.donor),
        joinedload(Conversation.resource_listing)
    ).filter(
        or_(
            Conversation.help_seeker_id == user.id,
            Conversation.donor_id == user.id
        )
    ).order_by(Conversation.updated_at.desc()).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=20,
        error_out=False
    )


def _serialize_message(message, user_id):
    return {
        'id': message.id,
        'text': message.message_text,
        'sender': message.sender.full_name,
        'created_at': message.created_at.isoformat(),
        'is_mine': message.sender_id == user_id,
        'is_read': message.is_read
    }


def _render_messages(conversations, selected=None, recent_messages=(), has_older=False):
    conversation_ids = [conversation.id for conversation in conversations.items]
    unread_by_conversation = dict.fromkeys(conversation_ids, 0)
    latest_messages = {}
    if conversation_ids:
        unread_counts = db.session.query(
            Message.conversation_id,
            func.count(Message.id)
        ).filter(
            Message.conversation_id.in_(conversation_ids),
            Message.sender_id != g.current_user.id,
            Message.is_read.is_(False)
        ).group_by(Message.conversation_id).all()
        unread_by_conversation.update(dict(unread_counts))

        latest_message_ids = db.session.query(
            func.max(Message.id).label('message_id')
        ).filter(
            Message.conversation_id.in_(conversation_ids)
        ).group_by(Message.conversation_id).subquery()
        latest_messages = {
            message.conversation_id: message
            for message in Message.query.join(
                latest_message_ids,
                Message.id == latest_message_ids.c.message_id
            ).all()
        }

    return render_template(
        'messages.html',
        conversations=conversations,
        selected=selected,
        unread_by_conversation=unread_by_conversation,
        latest_messages=latest_messages,
        recent_messages=recent_messages,
        has_older=has_older
    )


@messaging_bp.route('/')
@role_required('help_seeker', 'donor', 'volunteer')
def inbox():
    conversations = _conversation_list(g.current_user)
    conversation_id = request.args.get('conversation', type=int)
    selected = _conversation_for_user(conversation_id, g.current_user) if conversation_id else None
    recent_messages = []
    has_older = False
    if selected:
        now = datetime.now(timezone.utc)
        result = db.session.execute(update(Message).where(
            Message.conversation_id == selected.id,
            Message.sender_id != g.current_user.id,
            Message.is_read.is_(False)
        ).values(is_read=True, read_at=now).execution_options(synchronize_session=False))
        if result.rowcount:
            db.session.commit()
        page = Message.query.options(joinedload(Message.sender)).filter_by(
            conversation_id=selected.id
        ).order_by(Message.id.desc()).limit(51).all()
        has_older = len(page) > 50
        recent_messages = list(reversed(page[:50]))
    return _render_messages(conversations, selected, recent_messages, has_older)


@messaging_bp.route('/resources')
@role_required('help_seeker', 'volunteer')
def browse_resources():
    resources = ResourceListing.query.options(
        joinedload(ResourceListing.donor)
    ).filter_by(status='Available').filter(
        ResourceListing.quantity > 0
    ).order_by(ResourceListing.created_at.desc()).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=20,
        error_out=False
    )
    return render_template('message_resources.html', resources=resources)


@messaging_bp.route('/contact/<int:resource_id>', methods=['POST'])
@role_required('help_seeker', 'volunteer')
def contact_donor(resource_id):
    resource = ResourceListing.query.options(
        joinedload(ResourceListing.donor)
    ).filter_by(id=resource_id).first_or_404()
    if resource.status != 'Available' or resource.quantity <= 0 or resource.is_expired:
        flash('This resource is no longer available for new conversations.', 'warning')
        return redirect(url_for('messaging.browse_resources'))
    if resource.donor_id == g.current_user.id or resource.donor.role != 'donor' or resource.donor.is_suspended:
        abort(403)

    conversation = Conversation.query.filter_by(
        help_seeker_id=g.current_user.id,
        donor_id=resource.donor_id,
        resource_listing_id=resource.id,
        status='open'
    ).first()
    if not conversation:
        conversation = Conversation(
            help_seeker_id=g.current_user.id,
            donor_id=resource.donor_id,
            resource_listing_id=resource.id,
            status='open'
        )
        db.session.add(conversation)
        db.session.flush()
        create_notification(
            user_id=resource.donor_id,
            title='New resource conversation',
            message=f'{g.current_user.full_name} contacted you about {resource.name or resource.category}.',
            link=url_for('messaging.inbox', conversation=conversation.id)
        )
        db.session.commit()
    return redirect(url_for('messaging.inbox', conversation=conversation.id))


@messaging_bp.route('/resource-requests/<int:resource_request_id>/contact', methods=['POST'])
@role_required('donor', 'volunteer')
def contact_resource_request_participant(resource_request_id):
    """Start or resume a private conversation about a volunteer's item request."""
    user = g.current_user
    resource_request = ResourceRequest.query.options(
        joinedload(ResourceRequest.resource)
    ).filter_by(id=resource_request_id).first_or_404()
    resource = resource_request.resource

    if user.role == 'donor':
        if resource.donor_id != user.id:
            abort(403)
        participant = User.query.filter_by(
            id=resource_request.volunteer_id,
            role='volunteer',
            is_suspended=False
        ).first_or_404()
        verification = VolunteerVerification.query.filter_by(
            volunteer_id=participant.id,
            verification_status='approved'
        ).first()
        if not verification:
            abort(403)
        donor = user
        recipient = participant
    else:
        if resource_request.volunteer_id != user.id:
            abort(403)
        participant = user
        donor = User.query.filter_by(
            id=resource.donor_id,
            role='donor',
            is_suspended=False
        ).first_or_404()
        recipient = donor

    conversation = Conversation.query.filter_by(
        help_seeker_id=participant.id,
        donor_id=donor.id,
        resource_listing_id=resource.id,
        status='open'
    ).first()
    if not conversation:
        conversation = Conversation(
            help_seeker_id=participant.id,
            donor_id=donor.id,
            resource_listing_id=resource.id,
            status='open'
        )
        db.session.add(conversation)
        db.session.flush()
        create_notification(
            user_id=recipient.id,
            title='New resource conversation',
            message=f'{user.full_name} started a conversation about {resource.name or resource.category}.',
            link=url_for('messaging.inbox', conversation=conversation.id)
        )
        db.session.commit()
    return redirect(url_for('messaging.inbox', conversation=conversation.id))


@messaging_bp.route('/conversations/<int:conversation_id>/send', methods=['POST'])
@role_required('help_seeker', 'donor', 'volunteer')
def send_message(conversation_id):
    user = g.current_user
    conversation = _conversation_for_user(conversation_id, user)
    wants_json = request.accept_mimetypes.best == 'application/json' or request.is_json
    if conversation.status != 'open':
        if wants_json:
            return jsonify({'error': 'This conversation is closed and cannot receive messages.'}), 409
        flash('This conversation is closed and cannot receive messages.', 'warning')
        return redirect(url_for('messaging.inbox', conversation=conversation.id))

    payload = request.get_json(silent=True) or {}
    text = (payload.get('message_text') if request.is_json else request.form.get('message_text', ''))
    text = text.strip() if isinstance(text, str) else ''
    if not text or len(text) > 2000:
        if wants_json:
            return jsonify({'error': 'Messages must contain 1 to 2000 characters.'}), 400
        flash('Messages must contain 1 to 2000 characters.', 'danger')
        return redirect(url_for('messaging.inbox', conversation=conversation.id))

    now = datetime.now(timezone.utc)
    recent_count = Message.query.filter(
        Message.sender_id == user.id,
        Message.created_at >= now - timedelta(seconds=60)
    ).count()
    if recent_count >= 10:
        if wants_json:
            return jsonify({'error': 'You are sending messages too quickly. Please wait a moment.'}), 429
        flash('You are sending messages too quickly. Please wait a moment.', 'warning')
        return redirect(url_for('messaging.inbox', conversation=conversation.id))

    recipient_id = conversation.donor_id if user.id == conversation.help_seeker_id else conversation.help_seeker_id
    message = Message(
        conversation_id=conversation.id,
        sender_id=user.id,
        message_text=text,
        created_at=now
    )
    message.sender = user
    conversation.updated_at = now
    db.session.add(message)
    resource_name = (
        conversation.resource_listing.name or conversation.resource_listing.category
        if conversation.resource_listing else 'your conversation'
    )
    create_notification(
        user_id=recipient_id,
        title='New message received',
        message=f'New message about {resource_name}.',
        link=url_for('messaging.inbox', conversation=conversation.id)
    )
    db.session.flush()
    serialized_message = _serialize_message(message, user.id)
    db.session.commit()
    if wants_json:
        return jsonify({'message': serialized_message}), 201
    return redirect(url_for('messaging.inbox', conversation=conversation.id))


@messaging_bp.route('/conversations/<int:conversation_id>/poll')
@role_required('help_seeker', 'donor', 'volunteer')
def poll_messages(conversation_id):
    conversation = _conversation_for_user(conversation_id, g.current_user)
    after_id = request.args.get('after', default=0, type=int)
    messages = Message.query.options(
        joinedload(Message.sender)
    ).filter(
        Message.conversation_id == conversation.id,
        Message.id > after_id
    ).order_by(Message.id.asc()).limit(100).all()
    now = datetime.now(timezone.utc)
    new_message_ids = [message.id for message in messages if message.sender_id != g.current_user.id and not message.is_read]
    if new_message_ids:
        db.session.execute(update(Message).where(
            Message.id.in_(new_message_ids)
        ).values(is_read=True, read_at=now))
        db.session.commit()
    return jsonify({
        'status': conversation.status,
        'messages': [_serialize_message(message, g.current_user.id) for message in messages]
    })


@messaging_bp.route('/conversations/<int:conversation_id>/history')
@role_required('help_seeker', 'donor', 'volunteer')
def older_messages(conversation_id):
    conversation = _conversation_for_user(conversation_id, g.current_user)
    before_id = request.args.get('before', type=int)
    if not before_id or before_id < 1:
        return jsonify({'error': 'A valid message cursor is required.'}), 400
    page = Message.query.options(joinedload(Message.sender)).filter(
        Message.conversation_id == conversation.id,
        Message.id < before_id
    ).order_by(Message.id.desc()).limit(51).all()
    has_more = len(page) > 50
    return jsonify({
        'messages': [
            _serialize_message(message, g.current_user.id)
            for message in reversed(page[:50])
        ],
        'has_more': has_more
    })


@messaging_bp.route('/conversations/<int:conversation_id>/close', methods=['POST'])
@role_required('donor')
def close_conversation(conversation_id):
    conversation = _conversation_for_user(conversation_id, g.current_user)
    if conversation.donor_id != g.current_user.id:
        abort(403)
    if conversation.status == 'open':
        conversation.status = 'closed'
        conversation.updated_at = datetime.now(timezone.utc)
        create_notification(
            user_id=conversation.help_seeker_id,
            title='Conversation closed',
            message='The donor has resolved and closed this resource conversation.',
            link=url_for('messaging.inbox', conversation=conversation.id)
        )
        db.session.commit()
    return redirect(url_for('messaging.inbox', conversation=conversation.id))


@messaging_bp.route('/conversations/<int:conversation_id>/reopen', methods=['POST'])
@role_required('donor')
def reopen_conversation(conversation_id):
    conversation = _conversation_for_user(conversation_id, g.current_user)
    if conversation.donor_id != g.current_user.id:
        abort(403)
    if conversation.status == 'closed':
        conversation.status = 'open'
        conversation.updated_at = datetime.now(timezone.utc)
        create_notification(
            user_id=conversation.help_seeker_id,
            title='Conversation reopened',
            message='The donor reopened this conversation.',
            link=url_for('messaging.inbox', conversation=conversation.id)
        )
        db.session.commit()
    return redirect(url_for('messaging.inbox', conversation=conversation.id))


@messaging_bp.route('/conversations/<int:conversation_id>/report', methods=['POST'])
@role_required('help_seeker', 'donor', 'volunteer')
def report_conversation(conversation_id):
    conversation = _conversation_for_user(conversation_id, g.current_user)
    reason = request.form.get('reason', '').strip()
    if not reason or len(reason) > 1000:
        flash('Please provide a report reason of 1 to 1000 characters.', 'danger')
        return redirect(url_for('messaging.inbox', conversation=conversation.id))

    report = ConversationReport(
        conversation_id=conversation.id,
        reporter_id=g.current_user.id,
        reason=reason
    )
    db.session.add(report)
    admins = User.query.filter_by(role='admin', is_suspended=False).all()
    for admin in admins:
        create_notification(
            user_id=admin.id,
            title='Conversation reported',
            message=f'A conversation was reported: {reason[:300]}',
            link=url_for('admin.dashboard')
        )
    db.session.commit()
    flash('Your report has been sent to the administrators.', 'success')
    return redirect(url_for('messaging.inbox', conversation=conversation.id))
