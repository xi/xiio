import time


def run(gen):
    try:
        timeout = next(gen)
        while True:
            try:
                time.sleep(timeout)
            except BaseException as e:
                timeout = gen.throw(e)
            else:
                timeout = next(gen)
    except StopIteration as e:
        return e.value
