# -*- coding: utf-8 -*-
"""
Database initialization script.
Creates all tables and inserts default data on first run.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from app import create_app
from app.extensions import db
from app.models import User, Tab
from werkzeug.security import generate_password_hash


def init_database():
    """Initialize database: create tables + seed default data."""
    app = create_app()

    with app.app_context():
        db.create_all()
        print('[OK] 数据库表创建完成')

        if User.query.count() > 0:
            print('[INFO] 用户已存在，跳过种子数据')
            return

        cfg = app.config

        # Default super admin
        admin = User(
            username=cfg.get('DEFAULT_ADMIN', {}).get('username', 'admin'),
            password_hash=generate_password_hash(cfg.get('DEFAULT_ADMIN', {}).get('password', 'admin123')),
            real_name=cfg.get('DEFAULT_ADMIN', {}).get('real_name', '系统管理员'),
            role='super_admin',
            department=cfg.get('DEFAULT_ADMIN', {}).get('department', '信息技术科'),
            is_active=1
        )
        db.session.add(admin)

        # Default dept admin
        dept_admin = User(
            username=cfg.get('DEFAULT_DEPT_ADMIN', {}).get('username', 'dept_admin'),
            password_hash=generate_password_hash(cfg.get('DEFAULT_DEPT_ADMIN', {}).get('password', 'admin123')),
            real_name=cfg.get('DEFAULT_DEPT_ADMIN', {}).get('real_name', '监区管理员'),
            role='dept_admin',
            department=cfg.get('DEFAULT_DEPT_ADMIN', {}).get('department', '一监区'),
            is_active=1
        )
        db.session.add(dept_admin)

        # Default normal user
        normal_user = User(
            username=cfg.get('DEFAULT_USER', {}).get('username', 'user'),
            password_hash=generate_password_hash(cfg.get('DEFAULT_USER', {}).get('password', 'admin123')),
            real_name=cfg.get('DEFAULT_USER', {}).get('real_name', '监区民警'),
            role='user',
            department=cfg.get('DEFAULT_USER', {}).get('department', '一监区'),
            is_active=1
        )
        db.session.add(normal_user)

        # Bulk flush to get IDs
        db.session.flush()

        # Bulletin tabs with columns (prison context)
        from app.models import Tab, Column, Bulletin
        bulletin_tabs = [
            {'name': '监狱通知', 'icon': '\U0001f4e2', 'sort_order': 1, 'is_pinned': 1, 'columns': [
                '监狱公告', '政工通知', '规章制度', '会议通知'
            ]},
            {'name': '监区动态', 'icon': '\U0001f4cb', 'sort_order': 2, 'is_pinned': 0, 'columns': [
                '一监区', '二监区', '三监区', '四监区', '五监区'
            ]},
            {'name': '科室专栏', 'icon': '\U0001f4ca', 'sort_order': 3, 'is_pinned': 0, 'columns': [
                '狱政管理科', '教育改造科', '刑罚执行科', '生活卫生科', '狱内侦查科'
            ]},
            {'name': '工作台账', 'icon': '\U0001f4d3', 'sort_order': 4, 'is_pinned': 0, 'columns': [
                '值班日志', '巡查记录', '谈话记录', '隐患排查', '考核评比'
            ]},
        ]
        sample_texts = [
            '请各单位按要求落实相关工作，及时报送材料。',
            '本周工作重点已发布，请各监区认真组织学习。',
            '根据上级通知要求，开展专项排查整治行动。',
            '会议定于本周五上午9时在机关三楼会议室召开。',
        ]

        for td in bulletin_tabs:
            tab = Tab(
                name=td['name'], tab_type='bulletin', icon=td['icon'],
                sort_order=td['sort_order'], is_pinned=td['is_pinned'],
                is_active=1, visible_roles='all', created_by=admin.id
            )
            db.session.add(tab)
            db.session.flush()

            for i, col_name in enumerate(td['columns']):
                col = Column(
                    tab_id=tab.id, name=col_name, description='',
                    sort_order=i + 1, is_active=1,
                    visible_roles='all', created_by=admin.id
                )
                db.session.add(col)
                db.session.flush()

                bulletin = Bulletin(
                    column_id=col.id,
                    title=col_name + '近期工作安排',
                    content='<p>各监区、科室：</p><p>根据监狱工作部署，现将<b>' + col_name + '</b>近期重点工作安排如下：</p><p>' + sample_texts[i % len(sample_texts)] + '</p><p>请各单位高度重视，抓好贯彻落实。</p>',
                    is_pinned=1 if i == 0 else 0,
                    status='published', created_by=admin.id
                )
                db.session.add(bulletin)

        # Default task categories (using BulletinCategory for both tasks and bulletins)
        from app.models import BulletinCategory
        default_categories = [
            {'name': '日常管理', 'icon': '\U0001f4cb', 'color': '#3b82f6', 'sort_order': 1},
            {'name': '安全检查', 'icon': '\U0001f50d', 'color': '#ef4444', 'sort_order': 2},
            {'name': '教育改造', 'icon': '\U0001f4da', 'color': '#10b981', 'sort_order': 3},
            {'name': '应急处置', 'icon': '\U0001f6a8', 'color': '#f59e0b', 'sort_order': 4},
            {'name': '行政事务', 'icon': '\U0001f4c4', 'color': '#8b5cf6', 'sort_order': 5},
        ]
        for cat in default_categories:
            tc = BulletinCategory(
                name=cat['name'], icon=cat['icon'], color=cat['color'],
                sort_order=cat['sort_order'], created_by=admin.id
            )
            db.session.add(tc)

        # Default bulletin categories
        from app.models import BulletinCategory
        bulletin_cats = [
            {'name': '通知公告', 'icon': '\U0001f4e2', 'color': '#3b82f6', 'tab_id': None, 'sort_order': 1},
            {'name': '制度文件', 'icon': '\U0001f4dc', 'color': '#f59e0b', 'tab_id': None, 'sort_order': 2},
            {'name': '工作简报', 'icon': '\U0001f4c4', 'color': '#10b981', 'tab_id': None, 'sort_order': 3},
        ]
        for bc in bulletin_cats:
            bcat = BulletinCategory(
                name=bc['name'], icon=bc['icon'], color=bc['color'],
                tab_id=bc['tab_id'], sort_order=bc['sort_order'],
                visible_roles='all', created_by=admin.id
            )
            db.session.add(bcat)

        # Sample memos
        from app.models import Memo
        sample_memos = [
            {'title': '本周值班安排确认', 'content': '确认本周值班表：\n周一：张三\n周二：李四\n周三：王五\n周四：赵六\n周五：钱七\n\n请各监区按时到岗。', 'memo_type': 'public', 'created_by': admin.id},
            {'title': '监区安全巡查重点', 'content': '1. 重点区域：监舍、车间、食堂\n2. 巡查频次：每2小时一次\n3. 异常情况立即上报\n4. 做好巡查记录', 'memo_type': 'public', 'created_by': dept_admin.id},
            {'title': '个人待办事项', 'content': '- 整理上月工作台账\n- 提交下月物资申领\n- 更新在押人员信息\n- 完成安全培训考核', 'memo_type': 'private', 'created_by': admin.id},
            {'title': '工作注意事项', 'content': '1. 进出监区须刷卡登记\n2. 通讯设备存放指定位置\n3. 按时参加周例会\n4. 及时处理OA任务', 'memo_type': 'private', 'created_by': dept_admin.id},
            {'title': '本周工作要点', 'content': '本周重点：\n1. 完成安全隐患排查\n2. 组织消防演练\n3. 更新应急预案\n4. 提交月度报告', 'memo_type': 'private', 'created_by': normal_user.id},
        ]
        for m in sample_memos:
            memo = Memo(
                title=m['title'], content=m['content'],
                memo_type=m['memo_type'], visible_roles='all',
                created_by=m['created_by']
            )
            db.session.add(memo)

        # Sample tasks
        from app.models import Task
        from datetime import date, timedelta
        sample_tasks = [
            {'title': '完成监区安全大检查', 'content': '对一监区所有区域进行安全大检查，重点排查消防设施、监控设备、门窗锁具。检查完成后填写安全检查表并上报。', 'priority': 'high', 'department': '一监区', 'assignee_id': dept_admin.id, 'deadline': date.today() + timedelta(days=3), 'status': 'pending'},
            {'title': '更新在押人员档案信息', 'content': '核对并更新在押人员基本信息、刑期变动、健康档案等，确保信息准确无误。', 'priority': 'medium', 'department': '狱政管理科', 'assignee_id': normal_user.id, 'deadline': date.today() + timedelta(days=7), 'status': 'processing'},
            {'title': '准备下周教育改造课程', 'content': '根据本月教育改造计划，准备下周课程教案和教学材料，包括法制教育、心理辅导、职业技能培训等内容。', 'priority': 'medium', 'department': '教育改造科', 'assignee_id': dept_admin.id, 'deadline': date.today() + timedelta(days=5), 'status': 'pending'},
        ]
        for t in sample_tasks:
            task = Task(
                title=t['title'], content=t['content'],
                priority=t['priority'], department=t['department'],
                assignee_id=t['assignee_id'], creator_id=admin.id,
                deadline=t['deadline'], status=t['status']
            )
            db.session.add(task)

        # Link tabs for sidebar quick access
        link_tabs = [
            {'name': '数据故事', 'icon': '\U0001f4ca', 'url': '/stats/story', 'sort_order': 1, 'visible_roles': 'all'},
            {'name': '系统设置', 'icon': '\U00002699', 'url': '/settings', 'sort_order': 2, 'visible_roles': '["super_admin","dept_admin"]'},
        ]
        for lt in link_tabs:
            link_tab = Tab(
                name=lt['name'], tab_type='link', icon=lt['icon'], url=lt['url'],
                sort_order=lt['sort_order'], is_pinned=0, is_active=1,
                visible_roles=lt['visible_roles'], created_by=admin.id
            )
            db.session.add(link_tab)

        db.session.commit()
        print('[OK] 种子数据创建完成')
        print('  admin      / admin123 (超级管理员)')
        print('  dept_admin / admin123 (监区管理员)')
        print('  user       / admin123 (干警)')
        print('  4个公示Tab + 19个栏目 + 19条示例内容')
        print('  5个任务类别 + 3个公示类别')
        print('  5条示例备忘 + 3条示例任务')
        print('  3个快捷链接')


if __name__ == '__main__':
    init_database()
