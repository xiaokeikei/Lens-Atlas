import argparse
import uvicorn
from .app import create_app
from .config import Config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=52032)
    args = parser.parse_args()
    uvicorn.run(create_app(Config()),host=args.host,port=args.port,access_log=False)


if __name__ == "__main__":
    main()
