import pytest
from unittest.mock import patch
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.checks import Warning
from django.core.checks.registry import registry as check_registry
from django.db import connection, transaction
from django.test import TestCase

from ilovevoley.core.checks import check_socialauth_config


class CheckSocialauthConfigTests(TestCase):
    def test_registered_as_deployment_check(self):
        """Verify check_socialauth_config is registered as deploy=True and not in registered_checks."""
        deployment_checks = check_registry.get_checks(include_deployment_checks=True)
        regular_checks = check_registry.get_checks(include_deployment_checks=False)

        assert check_socialauth_config in deployment_checks
        assert check_socialauth_config not in regular_checks

    def test_core_apps_ready_registers_checks(self):
        """Verify CoreConfig.ready imports and registers core checks."""
        from ilovevoley.core.apps import CoreConfig
        from django.apps import apps

        app_config = apps.get_app_config("core")
        app_config.ready()

        deployment_checks = check_registry.get_checks(include_deployment_checks=True)
        assert check_socialauth_config in deployment_checks

    def test_unmigrated_database_returns_warning_cleanly(self):
        """When django_site table does not exist, return W012 without raising DB exceptions."""
        with patch.object(connection.introspection, "table_names", return_value=[]):
            warnings = check_socialauth_config(None)

        assert len(warnings) == 1
        assert warnings[0].id == "ilovevoley.W012"

    def test_unmigrated_table_does_not_abort_atomic_transaction(self):
        """Introspecting missing table inside an atomic transaction must not abort the transaction."""
        with transaction.atomic():
            with patch.object(connection.introspection, "table_names", return_value=[]):
                warnings = check_socialauth_config(None)
            assert len(warnings) == 1
            assert warnings[0].id == "ilovevoley.W012"

            # Must still be able to execute queries in this transaction
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                row = cursor.fetchone()
                assert row == (1,)

    def test_database_filtering_skips_when_site_db_not_targeted(self):
        """When databases is specified and does not include the site router db, skip checks."""
        warnings = check_socialauth_config(None, databases=["non_existent_db"])
        assert warnings == []

    def test_site_domain_default_triggers_warning(self):
        """Site with domain example.com or localhost generates W004 warning."""
        Site.objects.filter(id=settings.SITE_ID).update(domain="example.com")

        warnings = check_socialauth_config(None)
        warning_ids = [w.id for w in warnings]
        assert "ilovevoley.W004" in warning_ids

    def test_missing_google_socialapp_triggers_warning(self):
        """Valid domain but no Google SocialApp generates W005 warning."""
        Site.objects.filter(id=settings.SITE_ID).update(domain="ilovevoley.es")
        from allauth.socialaccount.models import SocialApp

        SocialApp.objects.filter(provider="google").delete()

        warnings = check_socialauth_config(None)
        warning_ids = [w.id for w in warnings]
        assert "ilovevoley.W005" in warning_ids

    def test_google_socialapp_not_linked_to_site_triggers_warning(self):
        """Google SocialApp exists but not linked to site generates W006 warning."""
        site = Site.objects.get(id=settings.SITE_ID)
        site.domain = "ilovevoley.es"
        site.save()

        from allauth.socialaccount.models import SocialApp

        app = SocialApp.objects.create(
            provider="google",
            name="Google Test",
            client_id="test-client-id",
            secret="test-secret",
        )
        app.sites.clear()

        warnings = check_socialauth_config(None)
        warning_ids = [w.id for w in warnings]
        assert "ilovevoley.W006" in warning_ids

    def test_valid_configuration_returns_no_warnings(self):
        """Valid domain and linked SocialApp returns no warnings."""
        site = Site.objects.get(id=settings.SITE_ID)
        site.domain = "ilovevoley.es"
        site.save()

        from allauth.socialaccount.models import SocialApp

        app, _ = SocialApp.objects.get_or_create(
            provider="google",
            defaults={"name": "Google Prod", "client_id": "cid", "secret": "sec"},
        )
        app.sites.add(site)

        warnings = check_socialauth_config(None)
        assert warnings == []

    def test_site_does_not_exist_triggers_w007(self):
        """When Site table exists but Site record does not exist, return W007."""
        Site.objects.filter(id=settings.SITE_ID).delete()

        warnings = check_socialauth_config(None)
        warning_ids = [w.id for w in warnings]
        assert "ilovevoley.W007" in warning_ids

    def test_manage_check_does_not_execute_socialauth_check(self):
        """Standard manage.py check does not run check_socialauth_config because it is a deploy check."""
        import io
        from django.core.management import call_command

        stderr = io.StringIO()
        call_command("check", stderr=stderr)
        output = stderr.getvalue()

        assert "ilovevoley.W004" not in output
        assert "ilovevoley.W005" not in output
        assert "ilovevoley.W006" not in output
        assert "ilovevoley.W007" not in output
        assert "ilovevoley.W012" not in output

    def test_manage_check_deploy_executes_socialauth_check(self):
        """Deployment check (manage.py check --deploy) executes check_socialauth_config."""
        import io
        from django.core.management import call_command

        Site.objects.filter(id=settings.SITE_ID).update(domain="example.com")

        stderr = io.StringIO()
        call_command("check", deploy=True, stderr=stderr)
        output = stderr.getvalue()

        assert "ilovevoley.W004" in output

