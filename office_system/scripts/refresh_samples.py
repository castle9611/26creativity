# -*- coding: utf-8 -*-
"""Refresh OA demo content without changing user accounts."""
import json
import os
import sys
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app
from app.extensions import db
from app.models import (
    User, Task, Bulletin, Memo, OnlineDocument, Spreadsheet, File,
    QuickLink, BulletinCategory, Column,
)


BAD_TASKS = [
    '测试编辑任务', '为什么空调在印度难以普及？', '测试任务 - 功能验证',
    '空调', 'wf sf', '文件修改', 'asd afa s', '防诈骗', '记得发卡机',
    '打扫卫生', '更新在押人员档案信息', '准备下周教育改造课程',
]
BAD_BULLETINS = [
    '监狱公告近期工作安排', '政工通知近期工作安排', '规章制度近期工作安排',
    '会议通知近期工作安排', '值班日志近期工作安排', '巡查记录近期工作安排',
    '隐患排查近期工作安排', '1232恶趣味', '测试公示标题', '阿萨是否',
    '受到广泛', '啊如果爱人',
]
BAD_MEMOS = [
    '南开被骗', '11111', '没钱、不会语言，我还是来🇩🇪了',
    'HTTP/1.1" 304 -', '任务备忘：测试编辑任务', '任务备忘：wf sf', 'a',
]
BAD_DOCS = ['111', '提示他是t', '所谓的“生命最宝贵”是否本质上是一种社会规训？', 'aff']
BAD_SHEETS = ['1', '123', '11111111', 'sdad', '1232132']
BAD_FILE_NAMES = [
    'user_import_template.csv', 'png',
    'education_material_checklist.txt', 'risk_checklist.csv', 'drill_review_points.txt',
]

CATEGORY_SEEDS = [
    ('教育改造', 'cat-education', '#10b981', 1),
    ('监管改造', 'cat-prison-admin', '#0f766e', 2),
    ('劳动改造', 'cat-production', '#22c55e', 3),
    ('生活卫生', 'cat-kitchen', '#f59e0b', 4),
    ('狱内侦查', 'cat-patrol', '#8b5cf6', 5),
    ('安全警戒', 'gen-shield-star', '#dc2626', 6),
    ('队伍建设', 'users', '#0ea5e9', 7),
    ('综合保障', 'cat-logistics', '#64748b', 8),
]

COLUMN_SEEDS = {
    '教育改造': ['教育计划', '心理矫治', '技能培训'],
    '监管改造': ['监管动态', '秩序维护', '重点人员管理'],
    '劳动改造': ['生产安排', '安全生产', '质量检查'],
    '生活卫生': ['伙食管理', '医疗卫生', '环境整治'],
    '狱内侦查': ['线索核查', '风险研判', '专项排查'],
    '安全警戒': ['门禁巡查', '应急演练', '装备检查'],
    '队伍建设': ['学习培训', '值班安排', '考核提醒'],
    '综合保障': ['物资保障', '维修报修', '车辆安排'],
}


def first_user(role=None):
    query = User.query.filter_by(is_active=1)
    if role:
        query = query.filter_by(role=role)
    return query.order_by(User.id.asc()).first() or User.query.order_by(User.id.asc()).first()


def upsert(model, lookup, values):
    obj = model.query.filter_by(**lookup).first()
    if not obj:
        obj = model(**lookup)
        db.session.add(obj)
    for key, value in values.items():
        setattr(obj, key, value)
    return obj


def delete_noisy(model, field_name, bad_values):
    field = getattr(model, field_name)
    model.query.filter(field.in_(bad_values)).delete(synchronize_session=False)
    model.query.filter(field.like('%?%')).delete(synchronize_session=False)


def rich(title, lines):
    body = ''.join('<li>{}</li>'.format(line) for line in lines)
    return '<p><strong>{}</strong></p><ol>{}</ol><p>请相关单位按节点反馈办理情况。</p>'.format(title, body)


def sheet_payload(headers, rows):
    row_map = {'0': {'cells': {i: {'text': header} for i, header in enumerate(headers)}}}
    for row_index, row in enumerate(rows, 1):
        row_map[str(row_index)] = {'cells': {i: {'text': str(value)} for i, value in enumerate(row)}}
    return json.dumps([{
        'name': 'sheet1',
        'freeze': 'A1',
        'styles': [],
        'merges': [],
        'rows': row_map,
        'cols': {},
        'validations': [],
    }], ensure_ascii=False)


def main():
    app = create_app()
    with app.app_context():
        before_users = User.query.count()
        admin = first_user('super_admin')
        dept_admin = first_user('dept_admin') or admin
        normal = first_user('user') or dept_admin
        admin_id = admin.id if admin else None

        delete_noisy(Task, 'title', BAD_TASKS)
        delete_noisy(Bulletin, 'title', BAD_BULLETINS)
        delete_noisy(Memo, 'title', BAD_MEMOS)
        delete_noisy(OnlineDocument, 'title', BAD_DOCS)
        delete_noisy(Spreadsheet, 'name', BAD_SHEETS)
        delete_noisy(BulletinCategory, 'name', ['test'])
        delete_noisy(QuickLink, 'name', ['youtube', 'bilibili', '豆瓣', '观察者网'])
        File.query.filter(File.original_name.in_(BAD_FILE_NAMES)).delete(synchronize_session=False)
        File.query.filter(File.original_name.like('%?%')).delete(synchronize_session=False)

        db.session.flush()

        categories = {}
        for name, icon, color, order in CATEGORY_SEEDS:
            cat = upsert(BulletinCategory, {'name': name}, {
                'icon': icon,
                'color': color,
                'sort_order': order,
                'is_active': 1,
                'visible_roles': 'all',
                'created_by': admin_id,
            })
            db.session.flush()
            categories[name] = cat
            for index, column_name in enumerate(COLUMN_SEEDS[name], 1):
                upsert(Column, {'category_id': cat.id, 'name': column_name}, {
                    'description': column_name + '相关信息发布与归档',
                    'sort_order': index,
                    'is_active': 1,
                    'visible_roles': 'all',
                    'created_by': admin_id,
                })

        db.session.flush()
        columns = {(col.category.name if col.category else '', col.name): col for col in Column.query.all()}

        today = date.today()
        task_rows = [
            ('教育改造课堂资料更新', '整理本周法治教育、心理辅导和职业技能培训课件，上传至在线文档并通知各监区查阅。', 'medium', '教育改造科', '教育改造', dept_admin.id, today + timedelta(days=2), 'processing', 45),
            ('监管区夜间巡查闭环', '对重点区域夜间巡查记录进行复核，发现问题形成整改清单，次日上午前反馈处理结果。', 'high', '监管改造科', '监管改造', normal.id, today + timedelta(days=1), 'pending', 20),
            ('劳动现场安全提示更新', '检查车间安全提示牌、操作规程和工具清点台账，完成现场照片留存。', 'medium', '劳动改造科', '劳动改造', dept_admin.id, today + timedelta(days=4), 'processing', 65),
            ('生活卫生区域清洁检查', '重点查看食堂、医务室、公共走廊和仓储间卫生情况，发现问题当天整改。', 'normal', '生活卫生科', '生活卫生', normal.id, today + timedelta(days=3), 'processing', 50),
            ('应急装备月度盘点', '核对对讲设备、强光手电、防护器具和备用钥匙，缺失或损坏事项同步报综合保障。', 'high', '安全警戒科', '安全警戒', dept_admin.id, today + timedelta(days=5), 'pending', 10),
            ('队伍学习签到汇总', '汇总本周集中学习签到、请假和补学情况，形成部门简报。', 'low', '政治处', '队伍建设', admin_id, today + timedelta(days=6), 'pending', 0),
            ('综合保障报修复核', '对近期空调、门禁、照明报修事项进行复核，按紧急程度排序推进。', 'medium', '综合保障科', '综合保障', normal.id, today + timedelta(days=7), 'processing', 35),
            ('风险线索核查台账补录', '补录本周风险线索核查结果，关联相关附件和处置记录。', 'high', '狱内侦查科', '狱内侦查', dept_admin.id, today + timedelta(days=2), 'pending', 15),
        ]
        for title, content, priority, department, category_name, assignee_id, deadline, status, progress in task_rows:
            upsert(Task, {'title': title}, {
                'content': content,
                'priority': priority,
                'department': department,
                'category_id': categories[category_name].id,
                'assignee_id': assignee_id,
                'creator_id': admin_id,
                'deadline': deadline,
                'status': status,
                'progress': progress,
                'updated_at': datetime.utcnow(),
            })

        bulletin_rows = [
            ('关于开展教育改造课堂资料更新的通知', '教育改造', '教育计划', ['各监区于本周内核对课程表。', '课件、签到表和照片统一上传。', '未完成事项在周例会上说明。']),
            ('监管秩序专项提醒', '监管改造', '秩序维护', ['严格落实交接班点名。', '重点时段加强巡查。', '异常情况第一时间留痕上报。']),
            ('劳动现场安全生产提示', '劳动改造', '安全生产', ['班前十分钟开展安全提示。', '工具发放和回收双人核对。', '车间通道保持畅通。']),
            ('生活卫生检查安排', '生活卫生', '环境整治', ['食堂留样、消杀记录每日核查。', '公共区域卫生问题当天整改。', '检查结果纳入周通报。']),
            ('应急演练预通知', '安全警戒', '应急演练', ['本周组织一次无脚本应急演练。', '各岗位熟悉处置流程。', '演练结束后提交复盘材料。']),
            ('综合保障服务事项收集', '综合保障', '物资保障', ['各部门集中提交办公用品需求。', '维修类事项请注明地点和紧急程度。', '逾期事项转入下批处理。']),
        ]
        for index, (title, category_name, column_name, lines) in enumerate(bulletin_rows, 1):
            cat = categories[category_name]
            col = columns.get((category_name, column_name))
            upsert(Bulletin, {'title': title}, {
                'category_id': cat.id,
                'column_id': col.id if col else None,
                'content': rich(title, lines),
                'is_pinned': 1 if index <= 2 else 0,
                'is_active': 1,
                'status': 'published',
                'created_by': admin_id,
                'updated_at': datetime.utcnow(),
            })

        memo_rows = [
            ('本周重点跟进清单', '<p>1. 完成教育改造课堂资料核对。</p><p>2. 跟进夜间巡查闭环整改。</p><p>3. 汇总综合保障报修进展。</p>', 'public', admin_id),
            ('值班交接提醒', '<p>交接班时重点说明未闭环任务、临时通知和设备异常情况，交接双方签字确认。</p>', 'public', dept_admin.id),
            ('会议材料准备', '<p>周五例会前准备任务统计、公开公示更新、重点风险事项三类材料。</p>', 'private', admin_id),
            ('个人待办：文件归档', '<p>整理本周上传附件和在线文档，确保名称规范、关联对象正确。</p>', 'private', normal.id),
        ]
        for title, content, memo_type, creator_id in memo_rows:
            upsert(Memo, {'title': title}, {
                'content': content,
                'memo_type': memo_type,
                'visible_roles': 'all',
                'is_archived': 0,
                'created_by': creator_id,
                'updated_at': datetime.utcnow(),
            })

        doc_rows = [
            ('教育改造课堂资料更新说明', '<h2>教育改造课堂资料更新说明</h2><p>本文件用于说明课程资料更新范围、命名规则和反馈节点。</p><ul><li>课程表按周更新。</li><li>课件名称包含类别、日期和责任人。</li><li>反馈材料统一关联到对应任务。</li></ul>'),
            ('夜间巡查闭环记录模板', '<h2>夜间巡查闭环记录模板</h2><p>记录巡查时间、区域、发现问题、整改责任人和复核结论。</p>'),
            ('应急演练复盘提纲', '<h2>应急演练复盘提纲</h2><p>从响应速度、岗位协同、装备状态、信息报送四个维度复盘。</p>'),
            ('综合保障报修登记说明', '<h2>综合保障报修登记说明</h2><p>报修事项需包含地点、问题描述、照片、紧急程度和联系人。</p>'),
        ]
        docs = []
        for title, content in doc_rows:
            docs.append(upsert(OnlineDocument, {'title': title}, {
                'content': content,
                'doc_type': 'rich',
                'status': 'published',
                'view_roles': 'all',
                'edit_roles': '["super_admin","dept_admin"]',
                'is_active': 1,
                'created_by': admin_id,
                'updated_at': datetime.utcnow(),
            }))

        sheet_rows = [
            ('任务推进台账', ['事项', '责任部门', '责任人', '截止时间', '状态'], [
                ['教育改造课堂资料更新', '教育改造科', dept_admin.real_name or dept_admin.username, today + timedelta(days=2), '处理中'],
                ['应急装备月度盘点', '安全警戒科', dept_admin.real_name or dept_admin.username, today + timedelta(days=5), '待处理'],
                ['综合保障报修复核', '综合保障科', normal.real_name or normal.username, today + timedelta(days=7), '处理中'],
            ]),
            ('值班安排样例表', ['日期', '带班领导', '值班人员', '重点提醒'], [
                ['周一', '值班领导A', '一监区值班组', '夜间巡查'],
                ['周三', '值班领导B', '综合保障值班组', '设备报修跟进'],
                ['周五', '值班领导C', '教育改造值班组', '周例会材料'],
            ]),
            ('隐患排查清单', ['区域', '隐患描述', '整改措施', '复核状态'], [
                ['车间', '标识磨损', '更换提示牌', '待复核'],
                ['食堂', '消杀记录缺项', '补齐台账', '已完成'],
                ['门禁', '读卡器异常', '申请维修', '处理中'],
            ]),
        ]
        sheets = []
        for name, headers, rows in sheet_rows:
            sheets.append(upsert(Spreadsheet, {'name': name}, {
                'sheet_data': sheet_payload(headers, rows),
                'status': 'published',
                'view_roles': 'all',
                'edit_roles': '["super_admin","dept_admin"]',
                'is_active': 1,
                'created_by': admin_id,
                'updated_at': datetime.utcnow(),
            }))

        db.session.flush()
        first_task = Task.query.filter_by(title='教育改造课堂资料更新').first()
        first_bulletin = Bulletin.query.filter_by(title='关于开展教育改造课堂资料更新的通知').first()
        first_memo = Memo.query.filter_by(title='本周重点跟进清单').first()
        if first_task and docs:
            docs[0].related_type = 'task'
            docs[0].related_id = first_task.id
        if first_task and sheets:
            sheets[0].related_type = 'task'
            sheets[0].related_id = first_task.id
        if first_bulletin and len(docs) > 2:
            docs[2].related_type = 'bulletin'
            docs[2].related_id = first_bulletin.id
        if first_memo and len(docs) > 3:
            docs[3].related_type = 'memo'
            docs[3].related_id = first_memo.id

        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], datetime.utcnow().strftime('%Y-%m'))
        os.makedirs(upload_dir, exist_ok=True)
        sample_files = [
            ('教育改造资料清单.txt', 'education_material_checklist.txt', '教育改造资料清单\n- 课程表\n- 课件\n- 签到表\n- 反馈记录\n', 'task', first_task.id if first_task else 0, categories['教育改造'].id),
            ('隐患排查清单.csv', 'risk_checklist.csv', '区域,问题,责任人,状态\n车间,标识磨损,张三,待复核\n门禁,读卡异常,李四,处理中\n', '', 0, categories['安全警戒'].id),
            ('应急演练复盘要点.txt', 'drill_review_points.txt', '应急演练复盘要点\n1. 响应速度\n2. 岗位协同\n3. 装备状态\n4. 信息报送\n', 'bulletin', first_bulletin.id if first_bulletin else 0, categories['安全警戒'].id),
        ]
        for index, (original_name, disk_name, content, related_type, related_id, category_id) in enumerate(sample_files, 1):
            filename = 'sample_{}_{}'.format(index, disk_name)
            path = os.path.join(upload_dir, filename)
            with open(path, 'w', encoding='utf-8-sig') as handle:
                handle.write(content)
            record = File.query.filter_by(original_name=original_name).first()
            if not record:
                record = File(original_name=original_name, filename=filename)
                db.session.add(record)
            record.filename = filename
            record.file_path = os.path.relpath(path, ROOT)
            record.file_size = os.path.getsize(path)
            record.file_type = 'text/plain' if original_name.endswith('.txt') else 'text/csv'
            record.related_type = related_type
            record.related_id = related_id or 0
            record.category_id = category_id
            record.uploaded_by = admin_id
            record.is_deleted = 0

        quick_rows = [
            ('public', None, '政策法规库', 'https://www.gov.cn/zhengce/', 'globe', 1),
            ('public', None, '安全生产学习', 'https://www.mem.gov.cn/', 'gen-bookmark', 2),
            ('public', None, '办公资料下载', 'https://www.gov.cn/fuwu/', 'gen-link', 3),
        ]
        for user, offset in [(admin, 1), (dept_admin, 2), (normal, 3)]:
            if user:
                quick_rows.append(('user', user.id, '常用政策查询', 'https://www.gov.cn/zhengce/', 'globe', offset))
                quick_rows.append(('user', user.id, '工作资料库', 'https://www.gov.cn/fuwu/', 'gen-bookmark', offset + 10))
        for scope, user_id, name, url, icon, sort_order in quick_rows:
            upsert(QuickLink, {'scope': scope, 'user_id': user_id, 'name': name}, {
                'url': url,
                'icon': icon,
                'sort_order': sort_order,
                'is_active': 1,
                'created_by': admin_id,
            })

        db.session.commit()

        print('users_before=', before_users)
        print('users_after=', User.query.count())
        print('tasks=', Task.query.count())
        print('bulletins=', Bulletin.query.count())
        print('memos=', Memo.query.count())
        print('docs=', OnlineDocument.query.count())
        print('sheets=', Spreadsheet.query.count())
        print('files=', File.query.filter_by(is_deleted=0).count())
        print('quick_links=', QuickLink.query.count())


if __name__ == '__main__':
    main()
