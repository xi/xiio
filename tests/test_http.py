import unittest

from tests.utils import XiioTestCase

try:
    import xiio
    import xiio.http
    from xiio.http_utils import HttpError
except ImportError as e:
    raise unittest.SkipTest('no HTTP support') from e


class TestRequest(XiioTestCase):
    async def test_get(self):
        response = await xiio.http.request('GET', 'https://httpbin.org/get')
        self.assertEqual(response.status_code, 200)

    async def test_http(self):
        response = await xiio.http.request('GET', 'http://httpbin.org/get')
        self.assertEqual(response.request.url.use_ssl, False)

    async def test_params(self):
        response = await xiio.http.request(
            'GET', 'https://httpbin.org/get', params={'foo': 1}
        )
        self.assertEqual(str(response.request.url), 'https://httpbin.org/get?foo=1')

    async def test_json(self):
        response = await xiio.http.request(
            'GET', 'https://httpbin.org/get', json={'foo': 1}
        )
        self.assertEqual(response.request.body, b'{"foo": 1}')

    async def test_raise_for_status(self):
        with self.assertRaises(HttpError):
            await xiio.http.request('GET', 'https://httpbin.org/status/400')

    async def test_no_raise_for_status(self):
        response = await xiio.http.request(
            'GET', 'https://httpbin.org/status/400', raise_for_status=False
        )
        self.assertEqual(response.status_code, 400)


class TestFollowRedirects(XiioTestCase):
    async def test_no_follow(self):
        response = await xiio.http.request(
            'GET',
            'https://httpbin.org/redirect-to',
            params={'url': '/get'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(response.history), 0)

    async def test_302(self):
        response = await xiio.http.request(
            'GET', 'https://httpbin.org/redirect-to', params={'url': '/get'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.request.url), 'https://httpbin.org/get')
        self.assertEqual(len(response.history), 1)

    async def test_too_many(self):
        with self.assertRaises(xiio.http.TooManyRedirectsError):
            await xiio.http.request(
                'GET', 'https://httpbin.org/redirect/3', max_redirects=2
            )
