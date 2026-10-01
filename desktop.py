"""Windows desktop entry point, also used by the frozen backend child."""

from src.desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
