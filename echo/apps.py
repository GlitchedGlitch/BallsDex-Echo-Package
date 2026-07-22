from django.apps import AppConfig


class EchoConfig(AppConfig):
    name = "echo"
    verbose_name = "Echo"
    default_auto_field = "django.db.models.BigAutoField"
    dpy_package = "echo.echo"  
