# xiio - really simple async runtime

xiio (Ξ-I/O) is yet another async runtime for Python, like
[asyncio](https://docs.python.org/3/library/asyncio.html) or
[trio](https://github.com/python-trio/trio/). Both of these libraries have ~10k
lines of code, while this one has less than 200. So I guess it is fair to say
that it is *really simple*.

## Usage

```python
import sys
import xiio


async def greet(name):
    await xiio.sleep(len(name) / 10)
    print(f'Hello, {name}!')


async def main():
    name1 = (await xiio.read(sys.stdin, 32)).decode()
    name2 = (await xiio.read(sys.stdin, 32)).decode()

    await xiio.gather([
        greet(name1),
        greet(name2),
    ])


xiio.run(main())
```

## Structured Concurrency

Similar to [nurseries in
trio](https://vorpus.org/blog/notes-on-structured-concurrency-or-go-statement-considered-harmful/)
and [task groups in
asyncio](https://docs.python.org/3/library/asyncio-task.html#asyncio.TaskGroup),
xiio provides a low level primitive that controls the lifetime of subtasks.
For example, `gather()` is just a higher level abstraction on top of that:

```python
async def gather(coros):
    async with TaskGroup() as tg:
        tasks = [tg.add_task(coro) for coro in coros]
    return [task.result for task in tasks]
```

Task groups in xiio have the following properties:

-   All subtasks are guaranteed to have finished when the task group exits.
-   Subtasks are not started immediately. They have a chance to get started the
    next time the main task awaits.
-   If any task in a task group raises an exception, a `xiio.CancelledError` is
    raised in all other tasks. The tasks are then responsible for cleaning up
    quickly. They may still await async functions if necessary.
-   Any exceptions that are raised after cancellation are lost. Only the first
    one is raised after cleanup is done.
-   Tasks are removed from the task group once they are done. If you need their
    results, keep the reference that is returned by `TaskGroup.add_task()`.
-   It is possible to add new tasks while the task group is already running,
    and even after cancellation.

## Design

I spent quite some time creating meaningful commits. So if you want to
understand why all the individual pieces are there and how they fit together, I
encourage you to check the commit history.
