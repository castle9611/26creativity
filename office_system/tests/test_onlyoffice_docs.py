# -*- coding: utf-8 -*-
import io
import os
import shutil
import tempfile
import unittest
import zipfile
import sys
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import File, OnlineDocument, User
from app.onlyoffice import (build_content_token, build_document_key, office_type_from_extension,
                            validate_office_file, verify_content_token)


class OnlyOfficeDocsTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        class TestConfig(Config):
            TESTING = True
            SECRET_KEY = 'test-onlyoffice-secret'
            SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(self.root, 'test.db').replace('\\', '/')
            DOCUMENT_STORAGE_FOLDER = os.path.join(self.root, 'documents')
            DOCUMENT_VERSION_FOLDER = os.path.join(self.root, 'versions')
            ONLYOFFICE_ENABLED = False
            ONLYOFFICE_SERVER_URL = ''
            APP_PUBLIC_URL = 'https://app.example.test'
            ONLYOFFICE_JWT_ENABLED = False
            ONLYOFFICE_DOWNLOAD_HOSTS = ('docs.example.test',)
            DOCUMENT_URL_TOKEN_MAX_AGE = 600
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.drop_all(); db.create_all()
            admin = User(username='admin-test', password_hash='x', real_name='管理员', role='dept_admin')
            user = User(username='user-test', password_hash='x', real_name='用户', role='user')
            db.session.add_all([admin, user]); db.session.commit()
            self.admin_id, self.user_id = admin.id, user.id

    def tearDown(self):
        with self.app.app_context(): db.session.remove(); db.drop_all()
        shutil.rmtree(self.root)

    def login(self, user_id, role):
        with self.client.session_transaction() as sess:
            sess.update(user_id=user_id, role=role, username=role, real_name=role)

    @staticmethod
    def ooxml(ext):
        required = {'docx': 'word/document.xml', 'xlsx': 'xl/workbook.xml', 'pptx': 'ppt/presentation.xml'}[ext]
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr(required, '<xml/>'); archive.writestr('[Content_Types].xml', '<Types/>')
        return data.getvalue()

    def test_login_required(self):
        self.assertEqual(self.client.get('/docs/').status_code, 302)

    def test_regular_user_cannot_create_or_upload(self):
        self.login(self.user_id, 'user')
        self.assertEqual(self.client.post('/docs/create-office', data={'file_ext': 'docx'}).status_code, 302)
        self.assertEqual(self.client.post('/docs/upload', data={'file': (io.BytesIO(b'x'), 'x.docx')}).status_code, 302)
        with self.app.app_context(): self.assertEqual(OnlineDocument.query.count(), 0)

    def test_admin_creates_all_office_types(self):
        self.login(self.admin_id, 'dept_admin')
        def fake_create(path, ext):
            with open(path, 'wb') as out: out.write(self.ooxml(ext))
            return validate_office_file(path, ext)
        with patch('app.views.docs.create_blank_office_file', side_effect=fake_create):
            for ext in ('docx', 'xlsx', 'pptx'):
                self.client.post('/docs/create-office', data={'file_ext': ext})
        with self.app.app_context(): self.assertEqual(OnlineDocument.query.filter_by(editor_kind='onlyoffice').count(), 3)

    def test_disguised_upload_rejected_and_valid_upload_accepted(self):
        self.login(self.admin_id, 'dept_admin')
        self.client.post('/docs/upload', data={'file': (io.BytesIO(b'not zip'), 'bad.docx')}, content_type='multipart/form-data')
        self.client.post('/docs/upload', data={'file': (io.BytesIO(self.ooxml('docx')), 'good.docx')}, content_type='multipart/form-data')
        with self.app.app_context(): self.assertEqual(OnlineDocument.query.count(), 1)

    def test_tokens_are_bound_and_bad_token_is_403(self):
        with self.app.app_context():
            token = build_content_token(12)
            self.assertTrue(verify_content_token(token, 12)); self.assertFalse(verify_content_token(token, 13))
        self.assertEqual(self.client.get('/docs/999/content?token=bad').status_code, 404)

    def test_content_download_and_no_session_required(self):
        with self.app.app_context():
            rel = '2026-01/a.docx'; path = os.path.join(self.root, 'documents', '2026-01', 'a.docx')
            os.makedirs(os.path.dirname(path))
            with open(path, 'wb') as output: output.write(self.ooxml('docx'))
            doc = OnlineDocument(title='a', editor_kind='onlyoffice', office_type='word', file_ext='docx',
                storage_relpath=rel, file_size=os.path.getsize(path), file_version=1, created_by=self.admin_id)
            db.session.add(doc); db.session.commit(); token = build_content_token(doc.id); doc_id = doc.id
        response = self.client.get('/docs/{}/content?token={}'.format(doc_id, token))
        self.assertEqual(response.status_code, 200); response.close()
        self.assertEqual(self.client.get('/docs/{}/content?token=bad'.format(doc_id)).status_code, 403)

    def test_type_mapping_and_stable_key(self):
        self.assertEqual([office_type_from_extension(x) for x in ('docx','xlsx','pptx')], ['word','cell','slide'])
        self.assertEqual(build_document_key(1, 1, 'abc'), build_document_key(1, 1, 'abc'))
        self.assertNotEqual(build_document_key(1, 1, 'abc'), build_document_key(1, 2, 'abc'))

    def test_legacy_html_still_views_and_downloads(self):
        with self.app.app_context():
            doc = OnlineDocument(title='旧文档', content='<p>内容</p>', created_by=self.admin_id, view_roles='all')
            db.session.add(doc); db.session.commit(); doc_id = doc.id
        self.login(self.user_id, 'user')
        self.assertEqual(self.client.get('/docs/{}'.format(doc_id)).status_code, 200)
        self.assertIn('application/msword', self.client.get('/docs/{}/download'.format(doc_id)).content_type)

    def test_unconfigured_onlyoffice_falls_back(self):
        with self.app.app_context():
            doc = OnlineDocument(title='Office', editor_kind='onlyoffice', office_type='word', file_ext='docx',
                                 storage_relpath='missing.docx', created_by=self.admin_id, view_roles='all')
            db.session.add(doc); db.session.commit(); doc_id = doc.id
        self.login(self.user_id, 'user')
        response = self.client.get('/docs/{}/view'.format(doc_id))
        self.assertEqual(response.status_code, 200); self.assertIn('尚未配置'.encode('utf-8'), response.data)

    def make_media(self, ext, content=b'0123456789abcdef'):
        path = os.path.join(self.root, 'media.' + ext)
        with open(path, 'wb') as output: output.write(content)
        with self.app.app_context():
            record = File(filename='stored.' + ext, original_name='media.' + ext,
                          file_path='data/uploads/stored.' + ext, file_size=len(content),
                          file_type=ext, uploaded_by=self.admin_id)
            db.session.add(record); db.session.commit(); return record.id, path

    def test_image_audio_video_preview_and_download(self):
        self.login(self.admin_id, 'dept_admin')
        for ext, marker in (('png', b'image-preview'), ('mp3', b'<audio'), ('mp4', b'<video')):
            file_id, path = self.make_media(ext)
            with patch('app.views.files.safe_file_path', return_value=path):
                preview = self.client.get('/files/{}/preview'.format(file_id))
                self.assertEqual(preview.status_code, 200); self.assertIn(marker, preview.data)
                download = self.client.get('/files/{}/download'.format(file_id))
                self.assertEqual(download.status_code, 200); self.assertIn('attachment', download.headers['Content-Disposition'])
                download.close()

    def test_media_stream_supports_range_and_permissions(self):
        file_id, path = self.make_media('mp4')
        self.login(self.admin_id, 'dept_admin')
        with patch('app.views.files.safe_file_path', return_value=path):
            response = self.client.get('/files/{}/stream'.format(file_id), headers={'Range': 'bytes=2-5'})
            self.assertEqual(response.status_code, 206); self.assertEqual(response.data, b'2345')
            self.assertEqual(response.headers.get('Accept-Ranges'), 'bytes')
            self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
            response.close()
        self.login(self.user_id, 'user')
        self.assertEqual(self.client.get('/files/{}/stream'.format(file_id)).status_code, 403)

    def test_public_home_media_preview_stream_and_download_need_no_login(self):
        file_id, path = self.make_media('mp4')
        with patch('app.views.files.safe_file_path', return_value=path):
            preview = self.client.get('/public/file/{}/preview'.format(file_id))
            self.assertEqual(preview.status_code, 200); self.assertIn(b'<video', preview.data)
            stream = self.client.get('/public/file/{}/stream'.format(file_id), headers={'Range': 'bytes=1-3'})
            self.assertEqual(stream.status_code, 206); self.assertEqual(stream.data, b'123'); stream.close()
            download = self.client.get('/public/file/{}/download'.format(file_id))
            self.assertEqual(download.status_code, 200); self.assertIn('attachment', download.headers['Content-Disposition']); download.close()


if __name__ == '__main__': unittest.main()
