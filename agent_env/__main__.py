import sys

if len(sys.argv) > 1 and sys.argv[1] == "home":
    from .home import main
    raise SystemExit(main(sys.argv[2:]))
else:
    from .bootstrap import main
    raise SystemExit(main())
