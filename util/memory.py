import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from core.keyboard import Layout, Position

BASE = os.environ.get('LAYOUTAPI_URL', 'http://127.0.0.1:8080').rstrip('/')
TIMEOUT = 30

_ids_cache: list[str] | None = None
_all_cache: list[Layout] | None = None


def _invalidate():
    global _ids_cache, _all_cache
    _ids_cache = None
    _all_cache = None


def _write_token() -> str:
    token = os.environ.get('LAYOUTAPI_TOKEN', '').strip()
    if token:
        return token
    path = os.environ.get('LAYOUTAPI_CLIENT_TOKEN_FILE', 'layoutapi_token.txt')
    try:
        with open(path, encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ''


def _headers() -> dict[str, str]:
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    token = _write_token()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


def _owned(ll: Layout, *, id: int, admin: bool = False) -> bool:
    return admin or int(ll.user) == int(id)


def _layout_url(name: str) -> str:
    return f'{BASE}/v1/layouts/{quote(name.lower(), safe="")}'


def _request(method: str, url: str, *, data: dict | None = None, headers: dict | None = None, timeout: int = TIMEOUT) -> tuple[int, dict | list | None]:
    body = None if data is None else json.dumps(data).encode()
    req = Request(url, data=body, method=method, headers=headers or _headers())
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read()
            parsed = json.loads(raw) if raw else None
            return res.status, parsed
    except HTTPError as err:
        raw = err.read()
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = None
        return err.code, parsed
    except URLError as err:
        raise ConnectionError(f'layout api unreachable at {BASE}: {err.reason}') from err


def from_dict(data: dict) -> Layout:
    keys = {
        k: Position(
            row=v['row'],
            col=v['col'],
            finger=v['finger'],
        )
        for k, v in (data.get('keys') or {}).items()
    }
    return Layout(
        name=data['name'],
        user=data['user'],
        board=data['board'],
        keys=keys,
    )


def to_dict(ll: Layout) -> dict:
    return {
        'name': ll.name,
        'user': ll.user,
        'board': ll.board,
        'keys': {
            k: {'row': v.row, 'col': v.col, 'finger': v.finger}
            for k, v in ll.keys.items()
        },
    }


def summaries(*, user: int | None = None, q: str | None = None, board: str | None = None) -> list[dict]:
    params = {}
    if user is not None:
        params['user'] = user
    if q:
        params['q'] = q
    if board:
        params['board'] = board
    url = f'{BASE}/v1/layouts'
    if params:
        url += '?' + urlencode(params)
    status, payload = _request('GET', url)
    if status != 200:
        raise RuntimeError(f'layout api list failed: {status} {payload}')
    return payload['layouts']


def ids() -> list[str]:
    global _ids_cache
    if _ids_cache is None:
        _ids_cache = [item['id'] for item in summaries()]
    return _ids_cache


def count() -> int:
    status, payload = _request('GET', f'{BASE}/health')
    if status != 200:
        raise RuntimeError(f'layout api health failed: {status} {payload}')
    return payload['count']


def all_layouts() -> list[Layout]:
    global _all_cache
    if _all_cache is None:
        status, payload = _request('GET', f'{BASE}/v1/layouts?full=1', timeout=60)
        if status != 200:
            raise RuntimeError(f'layout api full list failed: {status} {payload}')
        items = payload['layouts']
        if items and 'keys' not in items[0]:
            _all_cache = [ll for item in items if (ll := get(item['id'])) is not None]
        else:
            _all_cache = [from_dict(item) for item in items]
    return _all_cache


def add(ll: Layout) -> bool:
    status, payload = _request('POST', f'{BASE}/v1/layouts', data=to_dict(ll))
    if status == 409:
        return False
    if status not in (200, 201):
        raise RuntimeError(f'layout api create failed: {status} {payload}')
    _invalidate()
    return True


def update(ll: Layout, *, id: int, admin: bool = False) -> bool:
    existing = get(ll.name)
    if existing is None:
        return False
    if not _owned(existing, id=id, admin=admin):
        return False
    status, payload = _request('PUT', _layout_url(ll.name), data=to_dict(ll))
    if status == 404:
        return False
    if status not in (200, 204):
        raise RuntimeError(f'layout api update failed: {status} {payload}')
    _invalidate()
    return True


def remove(name: str, *, id: int, admin: bool = False) -> bool:
    ll = get(name)
    if ll is None:
        return False
    if not _owned(ll, id=id, admin=admin):
        return False
    status, payload = _request('DELETE', _layout_url(name))
    if status in (404, 403):
        return False
    if status not in (200, 204):
        raise RuntimeError(f'layout api delete failed: {status} {payload}')
    _invalidate()
    return True


def get(name: str) -> Layout | None:
    status, payload = _request('GET', _layout_url(name))
    if status == 404:
        return None
    if status != 200:
        raise RuntimeError(f'layout api get failed: {status} {payload}')
    return from_dict(payload)


def parse_file(file: str) -> Layout:
    name = os.path.splitext(os.path.basename(file))[0]
    ll = get(name)
    if ll is None:
        raise FileNotFoundError(file)
    return ll


def find(name: str) -> Layout:
    name = name.lower()
    ll = get(name)
    if ll is not None:
        return ll

    from jellyfish import damerau_levenshtein_distance as lev

    names = sorted(ids(), key=lambda x: len(x))
    if not names:
        raise FileNotFoundError(name)

    closest = min(names, key=lambda x: lev(''.join(y for y in x.lower() if y in name), name))
    ll = get(closest)
    if ll is None:
        raise FileNotFoundError(name)
    return ll
