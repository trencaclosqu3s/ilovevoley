from ilovevoley.videos.models import Match, Team
from django.db.models import Count, Q

def check_duplicates():
    # Teams that were targets of the merge
    target_team_names = ["CV SANT JOSEP", "CV SANT JOSEP GROC", "LUCI'S WORK SL ESPORLES VC", "LUCI'S WORD SL ESPORLES VC"]
    
    print(f"Checking for duplicates involving names like: {target_team_names}")
    
    # Get active teams matching these names
    teams = Team.objects.filter(
        Q(name__icontains="SANT JOSEP") | Q(name__icontains="LUCI'S")
    ).filter(is_active=True)
    
    print(f"Analyzing {teams.count()} active teams found.")
    
    total_duplicates = 0
    
    for team in teams:
        # Check for matches where this team plays home or away
        matches = Match.objects.filter(Q(home_team=team) | Q(away_team=team))
        
        # Group by opponent and date
        seen = {}
        duplicates = []
        
        for match in matches:
            opponent = match.away_team if match.home_team == team else match.home_team
            opponent_id = opponent.id if opponent else "None"
            date_str = match.match_date.strftime("%Y-%m-%d")
            
            key = f"{opponent_id}_{date_str}"
            
            if key in seen:
                duplicates.append((seen[key], match))
            else:
                seen[key] = match

        if duplicates:
            print(f"\nPotential duplicates for team {team.name} (ID {team.id}):")
            for m1, m2 in duplicates:
                print(f"  Conflict found on {m1.match_date.date()}:")
                print(f"    1. ID {m1.id} [{m1.status}]: {m1} (Created: {m1.created_at.date()})")
                print(f"    2. ID {m2.id} [{m2.status}]: {m2} (Created: {m2.created_at.date()})")
                total_duplicates += 1
                
    if total_duplicates == 0:
        print("\nSUCCESS: No duplicate matches found (same opponent, same date) for these teams.")
    else:
        print(f"\nWARNING: Found {total_duplicates} potential duplicate pairs.")

if __name__ == "__main__":
    check_duplicates()
