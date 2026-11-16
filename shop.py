"""Trusted local shopping CRUD operator for the Supabase REST API."""

import argparse
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


FIELDS = {
    'members': {'name': str, 'email': str, 'phone': str},
    'products': {'name': str, 'price': int, 'stock': int, 'description': str},
    'orders': {'member_id': int, 'product_id': int, 'quantity': int, 'unit_price': int, 'status': str},
}
REQUIRED = {
    'members': ('name', 'email'),
    'products': ('name', 'price'),
    'orders': ('member_id', 'product_id', 'quantity', 'unit_price'),
}
STATUSES = ('pending', 'paid', 'shipped', 'cancelled')


class ShopError(Exception):
    """A safe message that may be printed without exposing credentials."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ShopError('명령 인수를 확인하세요. 도움말: python -m shop --help')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Prevent forwarding API credentials to a redirect destination.
        return None


def parser():
    root = Parser(description='Supabase 쇼핑몰 CRUD (가격 단위: 원)')
    entities = root.add_subparsers(dest='entity', required=True)
    for entity, fields in FIELDS.items():
        actions = entities.add_parser(entity).add_subparsers(dest='action', required=True)
        for action in ('create', 'list', 'update', 'delete'):
            command = actions.add_parser(action)
            if action in ('update', 'delete'):
                command.add_argument('id', type=int, help='대상 PK')
            elif action == 'list':
                command.add_argument('--id', type=int, help='단일 PK 조회')
                command.add_argument('--limit', type=int, default=100, help='조회 개수 (1–1000)')
                command.add_argument('--offset', type=int, default=0, help='조회 시작 위치')
            if action in ('create', 'update'):
                for field, kind in fields.items():
                    command.add_argument('--' + field.replace('_', '-'), type=kind)
    return root


def validate(args):
    if getattr(args, 'id', None) is not None and args.id <= 0:
        raise ShopError('ID는 양의 정수여야 합니다.')
    if args.action == 'list':
        if not 1 <= args.limit <= 1000 or args.offset < 0:
            raise ShopError('limit은 1–1000, offset은 0 이상이어야 합니다.')
        return None
    if args.action == 'delete':
        return None
    data = {field: getattr(args, field) for field in FIELDS[args.entity] if getattr(args, field) is not None}
    if args.action == 'create' and any(field not in data for field in REQUIRED[args.entity]):
        raise ShopError('필수 필드가 누락되었습니다: ' + ', '.join(REQUIRED[args.entity]))
    if not data:
        raise ShopError('수정할 필드를 하나 이상 지정하세요.')
    if 'name' in data:
        data['name'] = data['name'].strip()
        if not 1 <= len(data['name']) <= 100:
            raise ShopError('이름은 공백을 제외하고 1–100자여야 합니다.')
    if 'email' in data:
        data['email'] = data['email'].strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', data['email']):
            raise ShopError('올바른 이메일을 입력하세요.')
    for field in ('price', 'stock', 'unit_price', 'quantity', 'member_id', 'product_id'):
        if field in data:
            minimum = 1 if field in ('quantity', 'member_id', 'product_id') else 0
            maximum = 9223372036854775807 if field.endswith('_id') else 2147483647
            if not minimum <= data[field] <= maximum:
                raise ShopError(f'{field} 값은 {minimum}–{maximum} 범위의 정수여야 합니다.')
    if 'status' in data and data['status'] not in STATUSES:
        raise ShopError('상태는 pending, paid, shipped, cancelled 중 하나여야 합니다.')
    return data


def request(args, data):
    url = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
    key = os.environ.get('SUPABASE_SECRET_KEY', '').strip()
    if not url or not key:
        raise ShopError('SUPABASE_URL과 SUPABASE_SECRET_KEY 환경 변수를 설정하세요.')
    parsed = urlsplit(url)
    local = parsed.hostname in ('127.0.0.1', 'localhost', '::1')
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path or not (parsed.scheme == 'https' or (parsed.scheme == 'http' and local)):
        raise ShopError('SUPABASE_URL은 HTTPS 프로젝트 기본 주소여야 합니다. 로컬 테스트만 HTTP를 허용합니다.')
    query = {'select': '*'}
    if args.action == 'list':
        query.update(order='id.asc', limit=args.limit, offset=args.offset)
    if getattr(args, 'id', None) is not None:
        query['id'] = f'eq.{args.id}'
    endpoint = f'{url}/rest/v1/shop_{args.entity}?{urlencode(query)}'
    headers = {'apikey': key, 'Content-Type': 'application/json', 'Prefer': 'return=representation'}
    if key.startswith('eyJ'):
        headers['Authorization'] = 'Bearer ' + key
    method = {'create': 'POST', 'list': 'GET', 'update': 'PATCH', 'delete': 'DELETE'}[args.action]
    payload = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
    try:
        with build_opener(NoRedirect()).open(Request(endpoint, data=payload, headers=headers, method=method), timeout=15) as response:
            result = json.load(response)
    except HTTPError as error:
        try:
            details = json.loads(error.read())
            code = details.get('code') if isinstance(details, dict) else None
        except (ValueError, OSError):
            code = None
        finally:
            error.close()
        messages = {
            '23503': '참조 관계 오류: 회원·상품 존재 여부를 확인하고, 삭제 전 연결된 주문을 먼저 삭제하세요.',
            '23505': '이미 등록된 값입니다. 이메일 중복 여부를 확인하세요.',
            '23514': '데이터베이스 제약 조건을 만족하지 않습니다.',
            '42501': '접근 권한이 없습니다. 관리자용 secret/service_role 키와 스키마 권한을 확인하세요.',
        }
        raise ShopError(messages.get(code, f'Supabase 요청 실패 (HTTP {error.code}). 프로젝트 주소, 키 및 스키마를 확인하세요.')) from None
    except (URLError, OSError, ValueError):
        raise ShopError('Supabase 연결 또는 응답 오류가 발생했습니다. 네트워크와 프로젝트 상태를 확인하세요.') from None
    if not isinstance(result, list):
        raise ShopError('Supabase 응답 형식이 올바르지 않습니다.')
    if args.action in ('update', 'delete') and not result:
        raise ShopError('대상 레코드를 찾을 수 없습니다.')
    return result


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        result = request(args, validate(args))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ShopError as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == '__main__':
    sys.exit(main())
