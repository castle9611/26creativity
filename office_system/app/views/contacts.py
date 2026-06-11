# -*- coding: utf-8 -*-
"""
Contacts blueprint - Internal directory.
"""
from flask import Blueprint, render_template, request, session
from app.extensions import db
from app.decorators import login_required
from app.models import User
from app.utils import get_pagination

contacts_bp = Blueprint('contacts', __name__)


@contacts_bp.route('/contacts')
@login_required
def index():
    """Contacts directory page."""
    page, per_page = get_pagination()
    search = request.args.get('search', '').strip()
    dept_filter = request.args.get('department', '').strip()

    query = User.query.filter(User.is_active == 1)

    if search:
        query = query.filter(
            db.or_(
                User.username.like('%' + search + '%'),
                User.real_name.like('%' + search + '%')
            )
        )

    if dept_filter:
        query = query.filter(User.department == dept_filter)

    query = query.order_by(User.department.asc(), User.real_name.asc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    contacts = pagination.items

    # Get all departments for filter
    departments = db.session.query(User.department).filter(
        User.department != '',
        User.is_active == 1
    ).distinct().order_by(User.department).all()
    departments = [d[0] for d in departments]

    return render_template('contacts/index.html',
                          contacts=contacts,
                          pagination=pagination,
                          search=search,
                          dept_filter=dept_filter,
                          departments=departments)
