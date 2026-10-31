"""Real-name public comments and per-reply read receipts."""
from flask import abort, request, session, redirect, url_for, render_template, flash
from sqlalchemy.orm import aliased
from app.extensions import db
from app.models import Comment, User, Task, Bulletin
from app.decorators import login_required
from app.utils import add_log


class CommentRead(db.Model):
    __tablename__ = 'comment_reads'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'), primary_key=True)


def unread_replies():
    parent = aliased(Comment)
    return Comment.query.join(parent, Comment.parent_id == parent.id).outerjoin(
        CommentRead, db.and_(CommentRead.comment_id == Comment.id,
                             CommentRead.user_id == session.get('user_id'))
    ).filter(parent.created_by == session.get('user_id'), parent.is_deleted == 0,
             Comment.is_deleted == 0, Comment.created_by != session.get('user_id'),
             CommentRead.comment_id.is_(None), db.or_(
                 db.and_(Comment.target_type == 'task', db.exists().where(Task.id == Comment.target_id)),
                 db.and_(Comment.target_type == 'bulletin', db.exists().where(db.and_(
                     Bulletin.id == Comment.target_id, Bulletin.status == 'published', Bulletin.is_active == 1)))))


def detail_comments(kind, item_id):
    page = Comment.query.filter_by(target_type=kind, target_id=item_id, is_deleted=0).order_by(
        Comment.created_at.desc(), Comment.id.desc()).paginate(
            page=max(1, request.args.get('comment_page', 1, type=int)), per_page=20, error_out=False)
    if session.get('user_id'):
        ids = [item.id for item in page.items]
        for item in unread_replies().filter(Comment.id.in_(ids)).all():
            db.session.merge(CommentRead(user_id=session['user_id'], comment_id=item.id))
        db.session.commit()
    return page


def register_comments(app):
    @app.route('/public/<kind>/<int:item_id>/comments', methods=['POST'])
    @login_required
    def public_comment(kind, item_id):
        user = User.query.get(session['user_id'])
        if not user or not user.is_active or not (user.real_name or '').strip():
            abort(403, description='请使用已填写真实姓名的有效账号留言')
        if kind == 'task':
            Task.query.get_or_404(item_id)
        elif kind == 'bulletin':
            Bulletin.query.filter_by(id=item_id, status='published', is_active=1).first_or_404()
        else:
            abort(404)
        content = request.form.get('content', '').strip()
        if not content or len(content) > 2000:
            abort(400, description='留言须为1至2000字')
        parent_id = request.form.get('parent_id', type=int)
        if parent_id:
            Comment.query.filter_by(id=parent_id, target_type=kind, target_id=item_id, is_deleted=0).first_or_404()
        item = Comment(target_type=kind, target_id=item_id, parent_id=parent_id,
                       content=content, created_by=user.id)
        db.session.add(item)
        db.session.commit()
        add_log('reply_comment' if parent_id else 'add_comment', kind, item_id, 'Public real-name comment')
        flash('\u56de\u590d\u6210\u529f' if parent_id else '\u7559\u8a00\u53d1\u5e03\u6210\u529f', 'success')
        return redirect(url_for('index_bp.public_' + kind + '_detail', **{kind + '_id': item_id}) + '#comments')

    @app.route('/public/replies')
    @login_required
    def public_replies():
        page = unread_replies().order_by(Comment.id.desc()).paginate(
            page=max(1, request.args.get('page', 1, type=int)), per_page=20, error_out=False)
        def newer_count(reply):
            return Comment.query.filter_by(target_type=reply.target_type, target_id=reply.target_id,
                                           is_deleted=0).filter(Comment.id > reply.id).count()
        return render_template('public_replies.html', replies=page, replies_query_count=newer_count)
