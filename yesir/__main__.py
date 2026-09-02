"""Entry point: `python -m yesir [query]` for single-shot, `python -m yesir --web` for UI."""

import argparse

from yesir import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yesir",
        description="Psi — zero-dependency coding agent harness with a TriLayer agent system",
    )
    parser.add_argument("query", nargs="*", help="single-shot query (console mode)")
    parser.add_argument("--web", action="store_true", help="start the web UI")
    parser.add_argument("--port", type=int, default=None, help="web UI port (default: random)")
    parser.add_argument("--version", action="version", version=f"yesir {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.web:
        from yesir.server import run_server  # noqa: PLC0415 (lazy: keep --help dependency-free)

        run_server(port=args.port)
        return 0
    if args.query:
        from yesir.cli import run_single_shot  # noqa: PLC0415 (lazy: keep --help dependency-free)

        return run_single_shot(" ".join(args.query))
    build_parser().print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
