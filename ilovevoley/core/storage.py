from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class ForgivingManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """Almacenamiento de archivos estáticos con hash que no falla ante archivos no presentes en el manifiesto.

    Hereda de ManifestStaticFilesStorage. Al establecer manifest_strict = False y capturar
    ValueError en stored_name, si un archivo no ha sido procesado por collectstatic (como
    en la ejecución de tests sin build previo) o no se encuentra en staticfiles.json, devuelve
    la ruta original sin hash en lugar de lanzar una excepción, garantizando resiliencia y
    evitando errores 500 en tiempo de ejecución.
    """

    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:
            return name
