try:
    from django.apps import AppConfig
    from scitex_sdk.app import embed

    _sdk_app_config: type[AppConfig] = embed.ScitexAppConfig

    class ClewAppConfig(_sdk_app_config):
        default = True
        name = "scitex_clew._django"
        label = "clew_app"
        verbose_name = "Clew"
except ModuleNotFoundError as exc:
    from scitex_clew._django._optional import gui_dependency_error

    gui_dependency_error(exc)
