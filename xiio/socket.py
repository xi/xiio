import socket

from .core import READ
from .core import WRITE
from .core import Condition
from .core import Future
from .multiplex import TaskGroup
from .multiplex import timeout
from .threads import ThreadPool


async def recv(sock: socket.socket, size: int, flags: int = 0) -> bytes:
    await Condition(files={sock.fileno(): READ})
    return sock.recv(size, flags)


async def send(sock: socket.socket, data: bytes, flags: int = 0) -> int:
    await Condition(files={sock.fileno(): WRITE})
    return sock.send(data, flags)


async def sendall(sock: socket.socket, data: bytes, flags: int = 0) -> None:
    while data:
        size = await send(sock, data, flags)
        data = data[size:]


async def create_connection(host: str, port: int, delay: float = 0.25) -> socket.socket:
    winning_socket = None

    with ThreadPool() as tp:
        targets = await tp.run(
            socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM
        )
        failures = [Future() for target in targets]

        async def attempt(i, tg):
            nonlocal winning_socket

            if i > 0:
                async with timeout(delay, throw=False):
                    await failures[i - 1]

            if i + 1 < len(targets):
                tg.add_task(attempt(i + 1, tg))

            *config, _, target = targets[i]
            try:
                sock = socket.socket(*config)
                await tp.run(sock.connect, target)
            except BaseException:
                sock.close()
                failures[i].set_result(None)
            else:
                for task in tg.tasks:
                    task.cancel()
                winning_socket = sock

        if targets:
            async with TaskGroup() as tg:
                tg.add_task(attempt(0, tg))

    if winning_socket is None:
        raise OSError('connection failed')
    return winning_socket
