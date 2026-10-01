from scitex_sdk.app import embed


class ClewAppConfig(embed.ScitexAppConfig):
    default = True
    name = "scitex_clew._django"
    label = "clew_app"
    verbose_name = "Clew"
