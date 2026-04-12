import os
import subprocess
import typing

from .core import READ
from .core import Condition


def kill_process(proc: subprocess.Popen, timeout: float = 1) -> None:
    proc.terminate()
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:  # pragma: no cover
        proc.kill()


async def run_process(
    cmd: list[str], *, capture_output: bool = False, check: bool = False, **kwargs
) -> subprocess.CompletedProcess:
    if capture_output:
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.PIPE

    with subprocess.Popen(cmd, **kwargs) as proc:
        try:
            # concurrency: as long as no one reaps the process (e.g. by
            # calling `waitpid()`) it is safe to use `pidfd_open()`
            pidfd = os.pidfd_open(proc.pid)
            await Condition(files={pidfd: READ})
            retcode = typing.cast(int, proc.poll())
            stdout, stderr = proc.communicate()
        except:
            kill_process(proc)
            raise

    result = subprocess.CompletedProcess(cmd, retcode, stdout, stderr)
    if check:
        result.check_returncode()
    return result
