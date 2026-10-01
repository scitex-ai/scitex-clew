"""Launch the leaf-owned GUI: python -m scitex_clew._django."""

import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="SciTeX Clew standalone GUI")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    os.environ["DJANGO_SETTINGS_MODULE"] = "scitex_clew._django.settings"
    import django

    django.setup()
    from scitex_sdk.app import embed

    embed.run_standalone(
        app_module="scitex_clew._django",
        host="127.0.0.1",
        port=args.port,
        open_browser=not args.no_browser,
    )


if __name__ == "__main__":
    main()
