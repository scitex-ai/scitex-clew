"""Launch the leaf-owned GUI: python -m scitex_clew._django."""

import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="SciTeX Clew standalone GUI")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    os.environ["DJANGO_SETTINGS_MODULE"] = "scitex_clew._django.settings"
    try:
        import django
    except ModuleNotFoundError as exc:
        from scitex_clew._django._optional import gui_dependency_error

        gui_dependency_error(exc)

    django.setup()
    try:
        from scitex_sdk.app import embed
    except ModuleNotFoundError as exc:
        from scitex_clew._django._optional import gui_dependency_error

        gui_dependency_error(exc)

    embed.run_standalone(
        app_module="scitex_clew._django",
        host="127.0.0.1",
        port=args.port,
        open_browser=not args.no_browser,
    )


if __name__ == "__main__":
    main()
