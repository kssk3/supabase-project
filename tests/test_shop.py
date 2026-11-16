import io
import gc
import warnings
import json
import os
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from unittest.mock import patch

import shop


class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        payload = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.server.requests.append((self.command, self.path, dict(self.headers), json.loads(payload) if payload else None))
        self.send_response(self.server.status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(self.server.response).encode())

    do_GET = do_POST = do_PATCH = do_DELETE = handle_request


class ShopContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), RequestHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.server.requests = []
        self.server.status = 200
        self.server.response = [{'id': 7}]
        self.env = {'SUPABASE_URL': f'http://127.0.0.1:{self.server.server_port}', 'SUPABASE_SECRET_KEY': 'sb_secret_example'}

    def run_cli(self, *args):
        output = io.StringIO()
        with patch.dict(os.environ, self.env, clear=True), redirect_stdout(output):
            code = shop.main(list(args))
        return code, json.loads(output.getvalue())

    def test_all_entities_support_crud_with_precise_id_filter(self):
        samples = {
            'members': ['--name', '민수', '--email', 'minsu@example.com'],
            'products': ['--name', '키보드', '--price', '30000'],
            'orders': ['--member-id', '1', '--product-id', '2', '--quantity', '2', '--unit-price', '30000'],
        }
        for entity, fields in samples.items():
            for action, extra, method in [('create', fields, 'POST'), ('list', [], 'GET'), ('update', ['7'] + fields, 'PATCH'), ('delete', ['7'], 'DELETE')]:
                with self.subTest(entity=entity, action=action):
                    code, result = self.run_cli(entity, action, *extra)
                    self.assertEqual(code, 0)
                    self.assertEqual(result, [{'id': 7}])
                    request_method, path, headers, body = self.server.requests[-1]
                    self.assertEqual(request_method, method)
                    self.assertTrue(path.startswith('/rest/v1/shop_' + entity))
                    self.assertEqual(headers['Apikey'], 'sb_secret_example')
                    self.assertNotIn('Authorization', headers)
                    if action in ('update', 'delete'):
                        self.assertIn('id=eq.7', path)
                    if action in ('create', 'update'):
                        self.assertEqual(headers['Prefer'], 'return=representation')
                        self.assertNotIn('id', body)

    def test_invalid_values_do_not_reach_supabase(self):
        for args in [
            ['products', 'create', '--name', 'x', '--price', '-1'],
            ['orders', 'create', '--member-id', '1', '--product-id', '1', '--quantity', '0', '--unit-price', '1'],
            ['members', 'create', '--name', '  ', '--email', 'bad'],
            ['members', 'update', '1'],
            ['members', 'delete', '0'],
        ]:
            with self.subTest(args=args):
                code, result = self.run_cli(*args)
                self.assertNotEqual(code, 0)
                self.assertIn('error', result)
        self.assertEqual(self.server.requests, [])

    def test_missing_record_is_reported_for_update_and_delete(self):
        self.server.response = []
        for args in [('members', 'update', '99', '--name', '민수'), ('products', 'delete', '99')]:
            code, result = self.run_cli(*args)
            self.assertEqual(code, 1)
            self.assertIn('찾을 수', result['error'])

    def test_database_conflict_is_safe_and_not_success(self):
        self.server.status = 409
        self.server.response = {'code': '23503', 'message': 'private server detail sb_secret_example'}
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter('always', ResourceWarning)
            code, result = self.run_cli('members', 'delete', '7')
            gc.collect()
        self.assertEqual([w for w in recorded if issubclass(w.category, ResourceWarning)], [])
        self.assertEqual(code, 1)
        self.assertIn('참조', result['error'])
        self.assertNotIn('sb_secret_example', json.dumps(result))

    def test_missing_credentials_and_insecure_url_are_rejected(self):
        for env in [{}, {'SUPABASE_URL': 'http://example.com', 'SUPABASE_SECRET_KEY': 'secret'}]:
            self.env = env
            code, result = self.run_cli('members', 'list')
            self.assertEqual(code, 1)
            self.assertIn('error', result)
        self.assertEqual(self.server.requests, [])

    def test_read_one_filters_by_id_and_legacy_jwt_uses_bearer(self):
        self.env['SUPABASE_SECRET_KEY'] = 'eyJ.legacy.jwt'
        code, result = self.run_cli('members', 'list', '--id', '7')
        self.assertEqual(code, 0)
        self.assertIn('id=eq.7', self.server.requests[-1][1])
        self.assertEqual(self.server.requests[-1][2]['Authorization'], 'Bearer eyJ.legacy.jwt')


if __name__ == '__main__':
    unittest.main()
