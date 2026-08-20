from bindaddr import detect_lan_ipv4
from app import create_app


def main():
    host = detect_lan_ipv4()
    app = create_app()
    app.run(host=host, port=8787, threaded=True)


if __name__ == "__main__":
    main()
