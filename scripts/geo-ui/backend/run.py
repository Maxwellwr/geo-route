from __future__ import annotations

from threading import Thread

from werkzeug.serving import make_server

from app import create_app
from bindaddr import detect_lan_ipv4

PORT = 8787
LOOPBACK = "127.0.0.1"


def serve(app, host: str) -> None:
    server = make_server(host, PORT, app, threaded=True)
    server.serve_forever()


def start_listener(app, host: str) -> Thread:
    thread = Thread(target=serve, args=(app, host), name=f"geo-ui-{host}")
    thread.start()
    return thread


def main() -> None:
    app = create_app()

    lan_host = detect_lan_ipv4()
    hosts = list(dict.fromkeys((lan_host, LOOPBACK)))

    threads = []
    for host in hosts:
        threads.append(start_listener(app, host))
        print(f"geo-ui: listening on http://{host}:{PORT}", flush=True)

    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
