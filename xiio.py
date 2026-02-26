import time


class Timeout:
    def __init__(self, seconds):
        self.seconds = seconds

    def __await__(self):
        yield self

    def wait(self):
        time.sleep(self.seconds)


def run(coro):
    gen = coro.__await__()
    try:
        timeout = next(gen)
        while True:
            try:
                timeout.wait()
            except BaseException as e:
                timeout = gen.throw(e)
            else:
                timeout = next(gen)
    except StopIteration as e:
        return e.value
