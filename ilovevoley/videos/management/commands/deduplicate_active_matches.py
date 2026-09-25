from django.core.management.base import BaseCommand
from django.db import transaction, models
from django.db.models import Count, Q
from ilovevoley.videos.models import Match, Team

class Command(BaseCommand):
    help = 'Deduplicates matches for active teams that have multiple entries for same opponent/date'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Teams to check
        target_team_names = ["CV SANT JOSEP", "CV SANT JOSEP GROC", "LUCI'S WORK SL ESPORLES VC"]
        
        self.stdout.write(f"Checking for duplicates for teams: {target_team_names}")
        
        teams = Team.objects.filter(
            Q(name__icontains="SANT JOSEP") | Q(name__icontains="LUCI'S")
        ).filter(is_active=True)
        
        total_deleted = 0
        
        for team in teams:
            matches = Match.objects.filter(Q(home_team=team) | Q(away_team=team))
            
            # Using a dictionary to find duplicates
            # Key: (opponent_id, date) -> list of matches
            seen = {}
            
            for match in matches:
                opponent = match.away_team if match.home_team == team else match.home_team
                opponent_id = opponent.id if opponent else "None"
                date_str = match.match_date.strftime("%Y-%m-%d")
                
                key = (opponent_id, date_str)
                
                if key not in seen:
                    seen[key] = []
                seen[key].append(match)
            
            # Process duplicates
            for key, duplicate_group in seen.items():
                if len(duplicate_group) > 1:
                    # Sort by id (keep the one with federation_id if possible, or the one with results)
                    # Priority: Has results > Has federation_id > Newest ID (or Oldest? usually newest is from recent scrape)
                    # Let's say keep the one with results.
                    
                    def sort_key(m):
                        has_results = 1 if (m.home_score is not None and m.away_score is not None) else 0
                        has_fed_id = 1 if m.federation_id else 0
                        # Prefer 'finished' over 'withdrawn' over 'scheduled'
                        status_score = 3 if m.status == 'finished' else (1 if m.status == 'withdrawn' else 2) 
                        return (has_results, status_score, has_fed_id, m.id)
                    
                    duplicate_group.sort(key=sort_key, reverse=True)
                    
                    keeper = duplicate_group[0]
                    tossers = duplicate_group[1:]
                    
                    self.stdout.write(f"\nDuplicate group found for {team.name} vs Opponent {key[0]} on {key[1]}:")
                    self.stdout.write(f"  Keeping: ID {keeper.id} [{keeper.status}] {keeper.home_score}-{keeper.away_score} (FedID: {keeper.federation_id})")
                    
                    if not dry_run:
                        with transaction.atomic():
                            for tosser in tossers:
                                self.stdout.write(f"  Deleting: ID {tosser.id} [{tosser.status}] {tosser.home_score}-{tosser.away_score}")
                                tosser.delete()
                                total_deleted += 1
                    else:
                        for tosser in tossers:
                             self.stdout.write(f"  [DRY RUN] Would delete: ID {tosser.id} [{tosser.status}]")
                             total_deleted += 1

        self.stdout.write(self.style.SUCCESS(f"\nDone. Deleted {total_deleted} duplicate matches."))
