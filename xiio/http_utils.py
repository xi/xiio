import json
import urllib.parse
from collections.abc import MutableMapping


class Headers(MutableMapping):
    def __init__(self, data=None, **kwargs):
        self._store = {}
        self.update(data or {}, **kwargs)

    def __setitem__(self, key, value):
        self._store[key.casefold()] = value

    def __getitem__(self, key):
        return self._store[key.casefold()]

    def __delitem__(self, key):
        del self._store[key.casefold()]

    def __iter__(self):
        return self._store.__iter__()

    def __len__(self):
        return self._store.__len__()

    def __str__(self):
        return self._store.__str__()


class URL:
    def __init__(self, url: str) -> None:
        self.parsed = urllib.parse.urlparse(url)

    def __str__(self):
        return urllib.parse.urlunparse(self.parsed)

    @property
    def use_ssl(self) -> bool:
        return self.parsed.scheme == 'https'

    @property
    def host(self) -> str:
        assert self.parsed.hostname
        return self.parsed.hostname

    @property
    def port(self) -> int:
        if self.parsed.port is not None:
            return self.parsed.port
        elif self.use_ssl:
            return 443
        else:
            return 80

    @property
    def origin(self) -> str:
        return f'{self.parsed.scheme}://{self.host}:{self.port}'

    @property
    def target(self) -> str:
        target = self.parsed.path or '/'
        if self.parsed.query:
            target += '?' + self.parsed.query
        return target


class Request:
    def __init__(
        self,
        method: str,
        url: str,
        body: bytes | None,
        headers: Headers,
    ):
        self.method = method
        self.url = URL(url)
        self.body = body
        self._headers = headers

    def __repr__(self):
        return f'<Request {self.method} {self.url}>'

    @property
    def headers(self) -> Headers:
        headers = Headers(self._headers)
        headers['Host'] = self.url.host
        if self.body:
            headers['Content-Length'] = str(len(self.body))
        return headers


class Response:
    def __init__(
        self,
        request: Request,
        status_code: int,
        reason: str,
        body: bytes | None,
        headers: Headers[str, str],
    ):
        self.request = request
        self.status_code = status_code
        self.reason = reason
        self.body = body
        self.headers = headers
        self.history = []

    def __repr__(self):
        return f'<Response [{self.status_code}]>'

    def text(self) -> str:
        if self.body is None:
            raise ValueError(self.body)
        encoding = self.headers.get('Content-Encoding', 'utf-8')
        return self.body.decode(encoding)

    def json(self):
        return json.loads(self.text())

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HttpError(self)


class HttpError(Exception):
    def __init__(self, response: Response):
        self.response = response

    def __str__(self) -> str:
        return f'{self.response.status_code} {self.response.reason}'


def redirect_to_request(resp: Response) -> Request:
    req = Request(
        resp.request.method,
        urllib.parse.urljoin(str(resp.request.url), resp.headers.get('Location')),
        resp.request.body,
        Headers(resp.request._headers),
    )

    if (
        (resp.status_code == 303 and req.method != 'HEAD')
        or (resp.status_code in [301, 302] and req.method == 'POST')
    ):
        req.method = 'GET'
        req.body = None

    if req.url.origin != resp.request.url.origin:
        req._headers.pop('Authorization', None)
        req._headers.pop('Cookie', None)
        req._headers.pop('Proxy-Authorization', None)

    return req
