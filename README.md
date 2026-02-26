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

## Design

I spent quite some time creating meaningful commits. So if you want to
understand why all the individual pieces are there and how they fit together, I
encourage you to check the commit history.
