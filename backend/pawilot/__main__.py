import json
import os
import socket
import sys
import threading
from pathlib import Path

import uvicorn

from .app import create_app
from .vault import KeychainVault


def main():
    os.umask(0o077)
    # The native app sends bootstrap configuration over a private stdin pipe.
    # The token never appears in process arguments, files, or the environment.
    config = json.loads(sys.stdin.readline())
    token = config["token"]
    data_dir = Path(config["data_dir"])
    app = create_app(data_dir / "pawilot.sqlite3", token, KeychainVault())
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="warning", host="127.0.0.1"))

    # A crash/quit of the native owner closes stdin. Avoid orphan agent processes.
    def watch_parent():
        sys.stdin.read()
        server.should_exit = True
    threading.Thread(target=watch_parent, daemon=True).start()
    print(json.dumps({"port": port}), flush=True)
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()

