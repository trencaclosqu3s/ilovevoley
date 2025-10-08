"""
Management command to check and fix calendar token issues.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialToken, SocialAccount
from videosvoley.core.services.calendar_sync import get_calendar_service

User = get_user_model()


class Command(BaseCommand):
    help = 'Check calendar token status for all users and suggest fixes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Auto-disable calendar sync for users without refresh tokens',
        )

    def handle(self, *args, **options):
        users_with_calendar = User.objects.filter(calendar_sync_enabled=True)
        
        if not users_with_calendar.exists():
            self.stdout.write(
                self.style.WARNING('No users have calendar sync enabled')
            )
            return

        self.stdout.write(f'Checking {users_with_calendar.count()} users with calendar sync enabled...\n')
        
        users_without_refresh = []
        users_with_issues = []
        users_ok = []
        
        for user in users_with_calendar:
            self.stdout.write(f'Checking user: {user.username}')
            
            # Check if user has Google account
            google_account = user.socialaccount_set.filter(provider='google').first()
            if not google_account:
                self.stdout.write(
                    self.style.ERROR(f'  ❌ No Google account linked')
                )
                users_with_issues.append(user)
                continue
            
            # Check if user has token
            token = SocialToken.objects.filter(
                account=google_account,
                app__provider='google'
            ).first()
            
            if not token:
                self.stdout.write(
                    self.style.ERROR(f'  ❌ No OAuth token found')
                )
                users_with_issues.append(user)
                continue
            
            # Check if user has refresh token
            if not token.token_secret:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠️  Missing refresh token (needs to reconnect)')
                )
                users_without_refresh.append(user)
                continue
            
            # Test calendar service
            try:
                service = get_calendar_service(user)
                if service and service.test_connection():
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✅ Calendar connection working')
                    )
                    users_ok.append(user)
                else:
                    self.stdout.write(
                        self.style.ERROR(f'  ❌ Calendar connection failed')
                    )
                    users_with_issues.append(user)
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  ❌ Error testing connection: {e}')
                )
                users_with_issues.append(user)
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write('SUMMARY:')
        self.stdout.write(f'✅ Users with working calendar sync: {len(users_ok)}')
        self.stdout.write(f'⚠️  Users missing refresh token: {len(users_without_refresh)}')
        self.stdout.write(f'❌ Users with other issues: {len(users_with_issues)}')
        
        if users_without_refresh:
            self.stdout.write('\nUsers that need to reconnect their Google account:')
            for user in users_without_refresh:
                self.stdout.write(f'  - {user.username} ({user.email})')
            
            if options['fix']:
                self.stdout.write('\nAuto-disabling calendar sync for users without refresh tokens...')
                for user in users_without_refresh:
                    user.calendar_sync_enabled = False
                    user.save()
                    self.stdout.write(f'  Disabled for {user.username}')
        
        if users_with_issues:
            self.stdout.write('\nUsers with other issues:')
            for user in users_with_issues:
                self.stdout.write(f'  - {user.username} ({user.email})')
        
        self.stdout.write('\n' + '='*50)
        self.stdout.write('INSTRUCTIONS FOR USERS:')
        self.stdout.write('1. Go to /accounts/social/connections/')
        self.stdout.write('2. Disconnect Google account')
        self.stdout.write('3. Reconnect Google account (will ask for Calendar permissions)')
        self.stdout.write('4. Re-enable calendar sync in profile settings')