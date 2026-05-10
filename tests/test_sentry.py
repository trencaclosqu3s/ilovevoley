from unittest.mock import patch


def test_configure_does_not_init_when_debug_true():
    from config.sentry import configure
    with patch('sentry_sdk.init') as mock_init:
        configure(dsn='https://test@sentry.io/1', debug=True, traces_sample_rate=0.1)
        mock_init.assert_not_called()


def test_configure_does_not_init_when_dsn_empty():
    from config.sentry import configure
    with patch('sentry_sdk.init') as mock_init:
        configure(dsn='', debug=False, traces_sample_rate=0.1)
        mock_init.assert_not_called()


def test_configure_inits_in_production():
    from config.sentry import configure
    with patch('sentry_sdk.init') as mock_init:
        configure(dsn='https://test@sentry.io/1', debug=False, traces_sample_rate=0.1)
        mock_init.assert_called_once()
        kwargs = mock_init.call_args.kwargs
        assert kwargs['dsn'] == 'https://test@sentry.io/1'
        assert kwargs['traces_sample_rate'] == 0.1
        assert kwargs['send_default_pii'] is False
        assert kwargs['environment'] == 'production'


def test_configure_includes_django_and_celery_integrations():
    from config.sentry import configure
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    with patch('sentry_sdk.init') as mock_init:
        configure(dsn='https://test@sentry.io/1', debug=False, traces_sample_rate=0.1)
        integrations = mock_init.call_args.kwargs['integrations']
        integration_types = [type(i) for i in integrations]
        assert DjangoIntegration in integration_types
        assert CeleryIntegration in integration_types
