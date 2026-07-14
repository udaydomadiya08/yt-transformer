#!/usr/bin/env python3
import asyncio
import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="yttransformer",
        description="Transform YouTube clips into AI-powered videos",
    )
    parser.add_argument("topic", nargs="?", help="Topic or description for the video")
    parser.add_argument("--orientation", "-o", choices=["horizontal", "vertical", "square"], default="horizontal")
    parser.add_argument("--output", "-out", default=str(Path.home() / "YTTransformer"), help="Output directory")
    parser.add_argument("--api-key", "-k", help="Gemini API key (or set GEMINI_API_KEY env var)")
    parser.add_argument("--demo", "-d", action="store_true", help="Run with hardcoded demo scenes (no API key needed)")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="Path to ffmpeg")

    args = parser.parse_args()

    if not args.demo and not args.api_key and not __import__("os").environ.get("GEMINI_API_KEY"):
        parser.print_help()
        print("\nError: Provide --api-key, set GEMINI_API_KEY env var, or use --demo")
        sys.exit(1)

    key = args.api_key or __import__("os").environ.get("GEMINI_API_KEY", "")
    topic = args.topic or ("quantum computing explained" if args.demo else "")

    if not topic:
        print("Error: provide a topic or use --demo")
        sys.exit(1)

    if args.demo:
        import brain.director as dr_mod
        from brain.demo_director import DemoDirector
        dr_mod.Director = DemoDirector
        key = "demo"

    from pipeline import VideoPipeline

    pipeline = VideoPipeline(key, args.output, args.ffmpeg, args.orientation)
    pipeline.on_progress(_on_progress)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        output = loop.run_until_complete(pipeline.run(topic))
        print(f"\nDone: {output}")
    except KeyboardInterrupt:
        pipeline.cancel()
        print("\nCancelled.")
    finally:
        loop.close()


def _on_progress(d):
    pct = d.get("percent", 0)
    msg = d.get("message", "")
    bar = "█" * int(pct * 30) + "░" * (30 - int(pct * 30))
    print(f"\r  [{bar}] {pct*100:5.1f}%  {msg}", end="")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
