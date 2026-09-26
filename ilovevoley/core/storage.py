from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class ForgivingManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """Manifest storage resilient to missing static files at runtime.

    ``manifest_strict = False`` only covers names absent from
    ``staticfiles.json``. ``hashed_name`` still raises ``ValueError`` when the
    source file is not on disk (e.g. tests without ``collectstatic``). Catching
    that keeps ``{% static %}`` from turning into a 500.
    """

    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:
            return name
