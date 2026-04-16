import socket

import xiio
from tests.utils import XiioTestCase


class TestSocket(XiioTestCase):
    async def test_socketpair(self):
        r, w = socket.socketpair()
        try:
            result = await xiio.gather([
                xiio.recv(r, 32),
                xiio.sendall(w, b'Hello World'),
            ])
        finally:
            w.close()
            r.close()

        self.assertEqual(result, [b'Hello World', None])
