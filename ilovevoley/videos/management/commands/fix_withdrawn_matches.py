from django.core.management.base import BaseCommand
from django.db import transaction, models
from django.db.models import Q
from ilovevoley.videos.models import Team, Match, Category
from ilovevoley.videos.utils import find_similar_team_by_name

class Command(BaseCommand):
    help = 'Fixes matches erroneously marked as withdrawn due to duplicate teams'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # 0. Fix incorrect category for CV SANT JOSEP GROC
        self.stdout.write("Checking for category correction (Cadete -> Infantil for CV SANT JOSEP GROC)...")
        # Find Cadete and Infantil categories
        try:
            cadete = Category.objects.filter(name__icontains='Cadete').first()
            infantil = Category.objects.filter(name__icontains='Infantil').first()
            
            if cadete and infantil:
                teams_to_fix = Team.objects.filter(name__icontains='CV SANT JOSEP GROC', category=cadete)
                if teams_to_fix.exists():
                    self.stdout.write(f"Found {teams_to_fix.count()} teams of 'CV SANT JOSEP GROC' incorrectly in '{cadete.name}'. Moving to '{infantil.name}'")
                    if not dry_run:
                        for team in teams_to_fix:
                             team.category = infantil
                             team.save()
                             self.stdout.write(f"  - Moved team {team.name} (ID {team.id}) to {infantil.name}")
                else:
                    self.stdout.write("No teams found needing category correction.")
            else:
                 self.stdout.write("Categories Cadete/Infantil not found, skipping specific correction.")
                 
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error correcting categories: {e}"))

        # 1. Find inactive teams that might be duplicates of active teams
        inactive_teams = Team.objects.filter(is_active=False)
        self.stdout.write(f"checking {inactive_teams.count()} inactive teams...")
        
        teams_merged = 0
        matches_moved = 0
        matches_deleted = 0
        
        for inactive_team in inactive_teams:
            # Skip if name is empty
            if not inactive_team.name:
                continue
                
            # Find similar active team without category restriction first
            # We explicitly exclude the inactive team itself from the search
            active_match, score = find_similar_team_by_name(
                inactive_team.name, 
                category=None, 
                threshold=0.9,
                exclude_id=inactive_team.id
            )
            
            # Ensure we found a DIFFERENT team which is ACTIVE
            if active_match and active_match.id != inactive_team.id and active_match.is_active:
                self.stdout.write(f"Found duplicate: Inactive '{inactive_team.name}' (ID {inactive_team.id}) -> Active '{active_match.name}' (ID {active_match.id}) Score: {score:.2f}")
                
                # Get matches for inactive team
                matches = Match.all_objects.filter(
                    Q(home_team=inactive_team) | Q(away_team=inactive_team)
                )
                
                if matches.exists():
                    self.stdout.write(f"  - Processing {matches.count()} matches...")
                    
                    if not dry_run:
                        with transaction.atomic():
                            for match in matches:
                                # Determine role
                                is_home = (match.home_team_id == inactive_team.id)
                                
                                # Check for collision with active team
                                query = Q(match_date__date=match.match_date.date()) 
                                # Match against the active team in the SAME role (or opposite? usually same role)
                                if is_home:
                                    query &= Q(home_team=active_match, away_team=match.away_team)
                                else:
                                    query &= Q(home_team=match.home_team, away_team=active_match)
                                    
                                existing_match = Match.objects.filter(query).first()
                                
                                if existing_match:
                                    # Collision! The active team already has a match here.
                                    # We assume the 'existing_match' is the correct one (from recent scrape).
                                    # We delete the duplicate (which is likely marked withdrawn)
                                    self.stdout.write(f"    - Deleting duplicate match (ID {match.id}, Status: {match.status}) in favor of (ID {existing_match.id}, Status: {existing_match.status})")
                                    match.delete()
                                    matches_deleted += 1
                                else:
                                    # No collision. Move match to active team.
                                    # And fix status if it was withdrawn
                                    old_status = match.status
                                    new_status = old_status
                                    
                                    if match.status == 'withdrawn':
                                        new_status = 'finished' if (match.home_score is not None and match.away_score is not None) else 'scheduled'
                                    
                                    if is_home:
                                        match.home_team = active_match
                                    else:
                                        match.away_team = active_match
                                        
                                    match.status = new_status
                                    match.save()
                                    self.stdout.write(f"    - Moved match (ID {match.id}): Status '{old_status}' -> '{new_status}'")
                                    matches_moved += 1
                            
                            # Delete inactive team
                            self.stdout.write(f"  - Deleting inactive team: {inactive_team.name}")
                            inactive_team.delete()
                            teams_merged += 1
                else:
                     if not dry_run:
                        self.stdout.write(f"  - Deleting inactive team (no matches): {inactive_team.name}")
                        inactive_team.delete()
                        teams_merged += 1
            else:
                # No similar active team found
                pass

        self.stdout.write(self.style.SUCCESS(f"\nDone. Merged {teams_merged} teams. Moved {matches_moved} matches. Deleted {matches_deleted} duplicates."))
