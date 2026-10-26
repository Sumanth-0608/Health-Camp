from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort
from ..models import db, User, SupportConversation, SupportMessage
from ..auth import login_required

support_bp = Blueprint('support', __name__, url_prefix='/support')

@support_bp.route('/')
@login_required
def index():
    user = g.current_user
    conversations = SupportConversation.query.filter_by(participant_id=user.id).order_by(SupportConversation.last_message_at.desc()).all()
    return render_template('support/index.html', user=user, conversations=conversations)

@support_bp.route('/new', methods=['POST'])
@login_required
def new_conversation():
    user = g.current_user
    subject = request.form.get('subject', '').strip()
    message_text = request.form.get('message', '').strip()
    
    if not subject:
        flash("Please provide a question subject.", "danger")
        return redirect(url_for('support.index'))
    if not message_text:
        flash("Message cannot be blank.", "danger")
        return redirect(url_for('support.index'))
        
    convo = SupportConversation(
        participant_id=user.id,
        subject=subject,
        status='Open',
        last_message_at=datetime.utcnow()
    )
    db.session.add(convo)
    db.session.flush()
    
    first_msg = SupportMessage(
        conversation_id=convo.id,
        sender_id=user.id,
        message=message_text,
        is_admin_reply=False
    )
    db.session.add(first_msg)
    db.session.commit()
    
    flash("Your support ticket has been submitted! Our coaching team will reply shortly.", "success")
    return redirect(url_for('support.view', conversation_id=convo.id))

@support_bp.route('/<int:conversation_id>', methods=['GET', 'POST'])
@login_required
def view(conversation_id):
    user = g.current_user
    convo = SupportConversation.query.get_or_404(conversation_id)
    
    # Strict ownership check: Only owner participant or admin can view
    if convo.participant_id != user.id and not user.is_admin:
        abort(403)
        
    if request.method == 'POST':
        reply_text = request.form.get('message', '').strip()
        if not reply_text:
            flash("Message cannot be empty.", "warning")
            return redirect(url_for('support.view', conversation_id=convo.id))
            
        msg = SupportMessage(
            conversation_id=convo.id,
            sender_id=user.id,
            message=reply_text,
            is_admin_reply=user.is_admin
        )
        db.session.add(msg)
        
        # Update conversation status and timestamp
        convo.last_message_at = datetime.utcnow()
        if user.is_admin:
            convo.status = 'Replied'
        else:
            convo.status = 'Open'
            
        db.session.commit()
        flash("Message sent successfully.", "success")
        return redirect(url_for('support.view', conversation_id=convo.id))
        
    messages = convo.messages.all()
    return render_template('support/view.html', user=user, convo=convo, messages=messages)
