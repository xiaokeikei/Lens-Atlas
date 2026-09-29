import json
import sys
from pathlib import Path
from .metadata import extract, thumbnail


def main(args=None):
    args = args or sys.argv[1:]
    output = None
    if args[:1] == ['--output']:
        output = Path(args[1])
        args = args[2:]
    def emit(value):
        text = json.dumps(value, ensure_ascii=True)
        if output:
            output.write_text(text, encoding='utf-8')
        else:
            print(text)
    try:
        if args[0] == "metadata":
            result = extract(Path(args[1]))
        else:
            thumbnail(Path(args[1]), Path(args[2]))
            result = {"ok": True}
        emit(result)
    except Exception as e:
        emit({"error": str(e), "type": type(e).__name__})
        sys.exit(1)


if __name__ == "__main__":
    main()
