"""Double-fork a process so it keeps running after docker exec returns."""

import os
import sys


def main() -> None:
    pidfile, logfile, *command = sys.argv[1:]
    if not command:
        raise SystemExit("usage: daemon.py PIDFILE LOGFILE COMMAND...")
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    with open(pidfile, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    null_fd = os.open("/dev/null", os.O_RDWR)
    log_fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(null_fd, 0)
    os.dup2(log_fd, 1)
    os.dup2(log_fd, 2)
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
