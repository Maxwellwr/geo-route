from __future__ import annotations

import time
from threading import Thread

from werkzeug.serving import make_server

from app import create_app
from bindaddr import detect_iface_ipv4, detect_lan_ipv4

PORT = 8787
WG_IFACE = "nwg0"
WG_RETRY_SECONDS = 2


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
    threads = [start_listener(app, lan_host)]
    print(f"geo-ui: listening on http://{lan_host}:{PORT}", flush=True)

    while True:
        try:
            wg_host = detect_iface_ipv4(WG_IFACE)
            break
        except RuntimeError:
            time.sleep(WG_RETRY_SECONDS)

    if wg_host != lan_host:
        threads.append(start_listener(app, wg_host))
        print(f"geo-ui: listening on http://{wg_host}:{PORT}", flush=True)

    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
