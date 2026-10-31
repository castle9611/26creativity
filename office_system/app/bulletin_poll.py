"""Shared bulletin poll data for public and workbench detail pages."""
import secrets
from flask import session, request
from app.extensions import db
from app.models import BulletinPoll, BulletinVote, User


def save_poll(bulletin, enabled, mode):
    if mode not in ('named', 'anonymous'):
        raise ValueError('Invalid voting mode')
    poll = bulletin.poll
    anonymous = mode == 'anonymous'
    if poll and poll.is_anonymous != anonymous and bulletin.poll_votes.first():
        raise ValueError('Voting mode is locked after the first vote')
    if poll is None:
        poll = BulletinPoll(bulletin=bulletin)
        db.session.add(poll)
    poll.enabled = enabled
    poll.is_anonymous = anonymous


def poll_info(bulletin):
    enabled = bool(bulletin.poll and bulletin.poll.enabled)
    anonymous = bool(not bulletin.poll or bulletin.poll.is_anonymous)
    counts = dict(db.session.query(BulletinVote.choice, db.func.count(BulletinVote.user_id)).filter_by(
        bulletin_id=bulletin.id).group_by(BulletinVote.choice).all())
    vote = BulletinVote.query.get((bulletin.id, session.get('user_id'))) if session.get('user_id') else None
    if 'poll_token' not in session:
        session['poll_token'] = secrets.token_hex(24)
    voters = None
    if enabled and not anonymous:
        voters = db.session.query(User.real_name, User.department, BulletinVote.choice, BulletinVote.created_at).join(
            BulletinVote, BulletinVote.user_id == User.id).filter(BulletinVote.bulletin_id == bulletin.id).order_by(
                BulletinVote.created_at.desc(), BulletinVote.user_id.desc()).paginate(
                    page=max(1, request.args.get('vote_page', 1, type=int)), per_page=15, error_out=False)
    return {'enabled': enabled, 'is_anonymous': anonymous, 'voters': voters, 'counts': counts,
            'choice': vote.choice if vote else '', 'total': sum(counts.values()),
            'token': session['poll_token']}
