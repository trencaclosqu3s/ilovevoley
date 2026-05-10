def configure(dsn, debug, traces_sample_rate):
    if debug or not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
    except ImportError:
        # sentry_sdk not installed, skip initialization
        return

    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
        environment='production',
    )
