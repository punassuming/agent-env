import argparse
import json
from pathlib import Path
import sys

if len(sys.argv) > 1 and sys.argv[1] == "home":
    from .home import main
    raise SystemExit(main(sys.argv[2:]))
if len(sys.argv) > 1 and sys.argv[1] == "registry":
    from .registry import deploy
    parser = argparse.ArgumentParser(description="Deploy registered skills and agents")
    parser.add_argument("action", choices=("plan", "install"))
    parser.add_argument("target", type=Path)
    parser.add_argument("--select", action="append", help="Registry item; repeat for multiple items")
    args = parser.parse_args(sys.argv[2:])
    try:
        result = deploy(Path(__file__).resolve().parents[1], args.target,
                        selected=set(args.select) if args.select else None, write=args.action == "install")
        print(json.dumps(result, indent=2))
        raise SystemExit(2 if result["conflicts"] else 0)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"agent-env registry: {exc}", file=sys.stderr)
        raise SystemExit(2)
from .bootstrap import main
raise SystemExit(main())
