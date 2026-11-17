"""TCP connect probe. Exit 0 connected, 124 timeout, 111 refused."""

import socket
import sys


def main() -> None:
    host, port, timeout = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except socket.timeout:
        print("timeout")
        raise SystemExit(124)
    except ConnectionRefusedError:
        print("refused")
        raise SystemExit(111)
    except OSError as exc:
        print(type(exc).__name__)
        raise SystemExit(1)
    else:
        print("connected")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
