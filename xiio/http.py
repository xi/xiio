# https://h11.readthedocs.io/en/latest/api.html
# https://docs.aiohttp.org/en/stable/client_reference.html

import socket
import ssl
import urllib.parse
from json import dumps as json_dumps

import h11

from .http_utils import Headers
from .http_utils import Request
from .http_utils import Response
from .http_utils import redirect_to_request
from .socket import create_connection
from .socket import recv
from .socket import sendall


class TooManyRedirectsError(Exception):
    pass


async def _request2(req: Request, sock: socket.socket, con: h11.Connection) -> Response:
    await sendall(sock, con.send(h11.Request(
        method=req.method,
        target=req.url.target,
        headers=list(req.headers.items()),
    )))
    if req.body:
        await sendall(sock, con.send(h11.Data(req.body)))
    await sendall(sock, con.send(h11.EndOfMessage()))

    resp = None
    body = b''
    while True:
        event = con.next_event()
        if event is h11.NEED_DATA:
            con.receive_data(await recv(sock, 2048))
        elif isinstance(event, h11.Response):
            resp = event
        elif isinstance(event, h11.Data):
            body += event.data
        else:
            assert isinstance(event, h11.EndOfMessage)
            break
    assert resp

    _headers = Headers(
        {key.decode(): value.decode() for key, value in resp.headers}
    )
    return Response(req, resp.status_code, resp.reason.decode(), body, _headers)


async def _request(
    req: Request,
    *,
    state: tuple[socket.socket, h11.Connection] | None = None,
    history: list[Response] = [],
    follow_redirects: bool = True,
    max_redirects: int = 10,
):
    if state:
        sock, con = state
    else:
        con = h11.Connection(our_role=h11.CLIENT)
        sock = await create_connection(req.url.host, req.url.port)
        if req.url.use_ssl:
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=req.url.host)

    with sock:  # sockets can be closed multiple times
        resp = await _request2(req, sock, con)

        if follow_redirects and resp.status_code in [301, 302, 303, 307, 308]:
            if len(history) >= max_redirects:
                resp.history = history
                raise TooManyRedirectsError(resp)

            history = [*history, resp]
            req = redirect_to_request(resp)

            if req.url.origin == resp.request.url.origin:
                con.start_next_cycle()
                new_state = (sock, con)
            else:
                sock.close()
                new_state = None

            return await _request(
                req,
                state=new_state,
                history=history,
                follow_redirects=follow_redirects,
                max_redirects=max_redirects,
            )

    resp.history = history
    return resp


async def request(
    method: str,
    url: str,
    *,
    params: dict[str, str] = {},
    body: bytes | None = None,
    json: dict | list | None = None,
    headers: dict[str, str] = {},
    follow_redirects: bool = True,
    max_redirects: int = 10,
    raise_for_status: bool = True,
):
    _headers = Headers(headers)

    if params:
        parsed = urllib.parse.urlparse(url)
        parsed = parsed._replace(query=urllib.parse.urlencode(params))
        url = urllib.parse.urlunparse(parsed)

    if json:
        body = json_dumps(json).encode('utf-8')
        _headers['Content-Type'] = 'application/json'
        _headers['Content-Encoding'] = 'utf-8'

    req = Request(method, url, body, _headers)
    response = await _request(
        req, follow_redirects=follow_redirects, max_redirects=max_redirects
    )
    if raise_for_status:
        response.raise_for_status()
    return response
