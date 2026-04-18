import os
import queue
import threading
import typing
from collections.abc import Callable

from .core import READ
from .core import Condition
from .core import Future

T = typing.TypeVar('T')


async def future_with_fd(future: Future[T], fd: int) -> T:
    while not future.done:
        await Condition(files={fd: READ})
    os.read(fd, 1)
    return future.unwrap()


class ThreadPool:
    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers or min(32, (os.cpu_count() or 1) + 4)
        self.queue = queue.Queue()
        self.workers = []

    def __enter__(self) -> 'ThreadPool':
        self.r, self.w = os.pipe()
        return self

    def __exit__(self, *args, **kwargs):
        for worker in self.workers:
            worker.join()
        os.close(self.r)
        os.close(self.w)

    def _worker(self) -> None:
        while True:
            try:
                fn = self.queue.get(block=False)
            except queue.Empty:
                break
            fn()
            self.queue.task_done()

    async def run(self, fn: Callable[..., T], *args, **kwargs) -> T:
        future = Future()

        def wrapper() -> None:
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                future.set_exception(e)
            else:
                future.set_result(result)
            finally:
                os.write(self.w, b'\0')

        self.queue.put(wrapper)

        self.workers = [w for w in self.workers if w.is_alive()]
        if len(self.workers) < self.max_workers:
            worker = threading.Thread(target=self._worker)
            self.workers.append(worker)
            worker.start()

        return await future_with_fd(future, self.r)


async def in_thread(fn: Callable[..., T], *args, **kwargs) -> T:
    with ThreadPool() as pool:
        return await pool.run(fn, *args, **kwargs)
