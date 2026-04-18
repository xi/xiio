import unittest

from xiio.http_utils import URL
from xiio.http_utils import Headers
from xiio.http_utils import HttpError
from xiio.http_utils import Request
from xiio.http_utils import Response
from xiio.http_utils import redirect_to_request


class TestHeaders(unittest.TestCase):
    def test_init(self):
        d = Headers(FOO='1')
        self.assertEqual(d['foo'], '1')

    def test_setitem(self):
        d = Headers()
        d['FOO'] = '1'
        self.assertEqual(d['foo'], '1')

    def test_delitem(self):
        d = Headers(FOO='1')
        del d['FOO']

    def test_get(self):
        d = Headers(FOO='1')
        self.assertEqual(d.get('foo'), '1')
        self.assertEqual(d.get('bar'), None)

    def test_iter(self):
        d = Headers(FOO='1')
        for key in d:
            self.assertEqual(d[key], '1')

    def test_len(self):
        d = Headers(FOO='1')
        d['foo'] = '2'
        self.assertEqual(len(d), 1)

    def test_str(self):
        d = Headers(FOO='1')
        self.assertEqual(str(d), "{'foo': '1'}")


class TestURL(unittest.TestCase):
    def test_url(self):
        url = URL('https://example.com')
        self.assertEqual(url.use_ssl, True)
        self.assertEqual(url.host, 'example.com')
        self.assertEqual(url.port, 443)
        self.assertEqual(url.origin, 'https://example.com:443')
        self.assertEqual(url.target, '/')

    def test_port_http(self):
        url = URL('http://example.com')
        self.assertEqual(url.use_ssl, False)
        self.assertEqual(url.port, 80)

    def test_port_explicit(self):
        url = URL('https://example.com:123')
        self.assertEqual(url.use_ssl, True)
        self.assertEqual(url.port, 123)

    def test_query(self):
        url = URL('https://example.com?foo=bar')
        self.assertEqual(url.target, '/?foo=bar')


class TestRequest(unittest.TestCase):
    def test_repr(self):
        req = Request('GET', 'https://example.com', None, Headers())
        self.assertEqual(repr(req), '<Request GET https://example.com>')

    def test_headers(self):
        req = Request('GET', 'https://example.com', None, Headers({
            'X-Test': '123',
        }))
        self.assertEqual(req.headers, Headers({
            'X-Test': '123',
            'Host': 'example.com',
            'Connection': 'close',
        }))

    def test_headers_with_body(self):
        req = Request('GET', 'https://example.com', b'abc', Headers())
        self.assertEqual(req.headers.get('Content-Length'), '3')


class TestResponse(unittest.TestCase):
    REQ = Request('GET', 'https://example.com', None, Headers())

    def test_repr(self):
        resp = Response(self.REQ, 200, 'OK', None, Headers())
        self.assertEqual(repr(resp), '<Response [200]>')

    def test_raise_for_status_200(self):
        resp = Response(self.REQ, 200, 'OK', None, Headers())
        resp.raise_for_status()

    def test_raise_for_status_400(self):
        resp = Response(self.REQ, 400, 'Bad Request', None, Headers())
        with self.assertRaises(HttpError) as cm:
            resp.raise_for_status()
        self.assertEqual(str(cm.exception), '400 Bad Request')

    def test_text(self):
        resp = Response(self.REQ, 200, 'OK', b'Hello', Headers())
        self.assertEqual(resp.text(), 'Hello')

    def test_text_latin1(self):
        headers = Headers({'Content-Encoding': 'latin-1'})
        resp = Response(self.REQ, 200, 'OK', b'H\xe4ll\xf6', headers)
        self.assertEqual(resp.text(), 'Hällö')

    def test_text_none(self):
        resp = Response(self.REQ, 200, 'OK', None, Headers())
        with self.assertRaises(ValueError):
            resp.text()

    def test_json(self):
        resp = Response(self.REQ, 200, 'OK', b'{"foo": 1}', Headers())
        self.assertEqual(resp.json(), {'foo': 1})

    def test_json_none(self):
        resp = Response(self.REQ, 200, 'OK', None, Headers())
        with self.assertRaises(ValueError):
            resp.json()


class Testredirect(unittest.TestCase):
    def test_302_get(self):
        loc = 'https://example.com/test/'
        req1 = Request(
            'GET',
            'https://example.com',
            b'abc',
            Headers({'Authorization': 'Bearer test'}),
        )
        resp = Response(req1, 302, 'Found', None, Headers({'Location': loc}))
        req2 = redirect_to_request(resp)

        self.assertEqual(req2.method, 'GET')
        self.assertEqual(str(req2.url), loc)
        self.assertEqual(req2.body, b'abc')
        self.assertEqual(req2.headers.get('Content-Length'), '3')
        self.assertEqual(req2.headers.get('Authorization'), 'Bearer test')

    def test_303_post(self):
        loc = 'https://example.com/test/'
        req1 = Request(
            'POST',
            'https://example.com',
            b'abc',
            Headers({'Authorization': 'Bearer test'}),
        )
        resp = Response(req1, 303, 'See Other', None, Headers({'Location': loc}))
        req2 = redirect_to_request(resp)

        self.assertEqual(req2.method, 'GET')
        self.assertEqual(str(req2.url), loc)
        self.assertEqual(req2.body, None)
        self.assertEqual(req2.headers.get('Content-Length'), None)
        self.assertEqual(req2.headers.get('Authorization'), 'Bearer test')

    def test_303_head(self):
        loc = 'https://example.com/test/'
        req1 = Request(
            'HEAD',
            'https://example.com',
            b'abc',
            Headers({'Authorization': 'Bearer test'}),
        )
        resp = Response(req1, 303, 'See Other', None, Headers({'Location': loc}))
        req2 = redirect_to_request(resp)

        self.assertEqual(req2.method, 'HEAD')
        self.assertEqual(str(req2.url), loc)
        self.assertEqual(req2.body, b'abc')
        self.assertEqual(req2.headers.get('Content-Length'), '3')
        self.assertEqual(req2.headers.get('Authorization'), 'Bearer test')

    def test_301_post(self):
        loc = 'https://example.com/test/'
        req1 = Request(
            'POST',
            'https://example.com',
            b'abc',
            Headers({'Authorization': 'Bearer test'}),
        )
        resp = Response(
            req1, 301, 'Moved Permanently', None, Headers({'Location': loc})
        )
        req2 = redirect_to_request(resp)

        self.assertEqual(req2.method, 'GET')
        self.assertEqual(str(req2.url), loc)
        self.assertEqual(req2.body, None)
        self.assertEqual(req2.headers.get('Content-Length'), None)
        self.assertEqual(req2.headers.get('Authorization'), 'Bearer test')

    def test_cross_origin_auth(self):
        loc = 'http://example.com/test/'
        req1 = Request(
            'GET',
            'https://example.com',
            b'abc',
            Headers({'Authorization': 'Bearer test'}),
        )
        resp = Response(req1, 302, 'Found', None, Headers({'Location': loc}))
        req2 = redirect_to_request(resp)

        self.assertEqual(req2.headers.get('Authorization'), None)

