import requests
from bs4 import BeautifulSoup
import json
import logging
from typing import Dict, List, Optional
from django.utils import timezone
from .models import League, Match, Standing, ScrapingEndpoint

logger = logging.getLogger(__name__)


def scrape_league_data(league: League, endpoint_type: str = 'standings') -> Dict:
    """
    Scrapes data for a specific league and endpoint type
    
    Args:
        league: League object to scrape
        endpoint_type: Type of data to scrape ('standings', 'results', 'calendar')
    
    Returns:
        Dict with scraped data or error information
    """
    try:
        # Get the appropriate endpoint
        endpoint = league.endpoints.filter(
            endpoint_type=endpoint_type,
            is_active=True
        ).first()
        
        if not endpoint:
            return {'error': f'No active endpoint found for {endpoint_type}'}
        
        # Build the full URL
        url = endpoint.get_full_url()
        
        # Make the request
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Parse based on parser type
        if endpoint.parser_type == 'table_standings':
            return parse_table_standings(response.text, league)
        elif endpoint.parser_type == 'match_results':
            return parse_match_results(response.text, league)
        elif endpoint.parser_type == 'match_calendar':
            return parse_match_calendar(response.text, league)
        elif endpoint.parser_type.startswith('json_'):
            return parse_json_data(response.json(), league, endpoint.parser_type)
        else:
            return {'error': f'Unknown parser type: {endpoint.parser_type}'}
            
    except requests.RequestException as e:
        logger.error(f'Request error scraping {league.name}: {e}')
        return {'error': f'Request failed: {str(e)}'}
    except Exception as e:
        logger.error(f'Unexpected error scraping {league.name}: {e}')
        return {'error': f'Unexpected error: {str(e)}'}


def parse_table_standings(html_content: str, league: League) -> Dict:
    """Parse HTML table standings"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        tables = soup.find_all('table')
        
        if not tables:
            return {'error': 'No tables found in HTML'}
        
        # Find the standings table (usually the first or largest table)
        standings_table = tables[0]
        rows = standings_table.find_all('tr')[1:]  # Skip header row
        
        standings_data = []
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 3:  # Minimum columns for standings
                standings_data.append({
                    'position': cells[0].get_text(strip=True),
                    'team_name': cells[1].get_text(strip=True),
                    'points': cells[-1].get_text(strip=True) if cells else '0',
                    # Add more fields as needed
                })
        
        return {
            'success': True,
            'data': standings_data,
            'league_id': league.id,
            'scraped_at': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f'Error parsing standings table: {e}')
        return {'error': f'Failed to parse standings: {str(e)}'}


def parse_match_results(html_content: str, league: League) -> Dict:
    """Parse HTML match results"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        matches = []
        
        # Look for match result patterns
        # This is a simplified example - adjust based on actual HTML structure
        match_elements = soup.find_all(['div', 'tr'], class_=lambda x: x and 'match' in x.lower())
        
        for element in match_elements:
            match_data = extract_match_data(element)
            if match_data:
                matches.append(match_data)
        
        return {
            'success': True,
            'data': matches,
            'league_id': league.id,
            'scraped_at': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f'Error parsing match results: {e}')
        return {'error': f'Failed to parse match results: {str(e)}'}


def parse_match_calendar(html_content: str, league: League) -> Dict:
    """Parse HTML match calendar"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        matches = []
        
        # Look for calendar/match elements
        # This is a simplified example - adjust based on actual HTML structure
        match_elements = soup.find_all(['div', 'tr'], class_=lambda x: x and 'calendar' in x.lower())
        
        for element in match_elements:
            match_data = extract_match_data(element)
            if match_data:
                matches.append(match_data)
        
        return {
            'success': True,
            'data': matches,
            'league_id': league.id,
            'scraped_at': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f'Error parsing match calendar: {e}')
        return {'error': f'Failed to parse match calendar: {str(e)}'}


def parse_json_data(json_data: Dict, league: League, parser_type: str) -> Dict:
    """Parse JSON data from API endpoints"""
    try:
        matches = []
        
        if parser_type == 'json_matches':
            # Parse upcoming matches
            for match_item in json_data.get('matches', []):
                match_data = {
                    'home_team': match_item.get('home_team', ''),
                    'away_team': match_item.get('away_team', ''),
                    'match_date': match_item.get('date', ''),
                    'venue': match_item.get('venue', ''),
                    'status': 'scheduled'
                }
                matches.append(match_data)
        
        elif parser_type == 'json_results':
            # Parse finished matches
            for match_item in json_data.get('results', []):
                match_data = {
                    'home_team': match_item.get('home_team', ''),
                    'away_team': match_item.get('away_team', ''),
                    'home_score': match_item.get('home_score'),
                    'away_score': match_item.get('away_score'),
                    'match_date': match_item.get('date', ''),
                    'status': 'finished'
                }
                matches.append(match_data)
        
        return {
            'success': True,
            'data': matches,
            'league_id': league.id,
            'scraped_at': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f'Error parsing JSON data: {e}')
        return {'error': f'Failed to parse JSON data: {str(e)}'}


def extract_match_data(element) -> Optional[Dict]:
    """Extract match data from HTML element"""
    try:
        # This is a simplified example - adjust based on actual HTML structure
        text = element.get_text(strip=True)
        
        # Look for patterns like "Team A vs Team B" or "Team A - Team B"
        if ' vs ' in text or ' - ' in text:
            separator = ' vs ' if ' vs ' in text else ' - '
            teams = text.split(separator)
            
            if len(teams) >= 2:
                return {
                    'home_team': teams[0].strip(),
                    'away_team': teams[1].strip(),
                    'raw_text': text
                }
        
        return None
        
    except Exception as e:
        logger.error(f'Error extracting match data: {e}')
        return None


def create_standings_from_data(league: League, standings_data: List[Dict]) -> int:
    """
    Create Standing objects from scraped data
    
    Args:
        league: League object
        standings_data: List of standings dictionaries
    
    Returns:
        Number of standings created/updated
    """
    created_count = 0
    
    try:
        for item in standings_data:
            # Try to find existing team by name
            # This will be updated when teams app is created
            team_name = item.get('team_name', '')
            if not team_name:
                continue
            
            # For now, create a placeholder team or skip
            # This will be properly implemented when teams app is ready
            logger.warning(f'Standings creation skipped - teams app not ready: {team_name}')
            continue
            
            # When teams app is ready, uncomment this:
            # team, created = Team.objects.get_or_create(
            #     name=team_name,
            #     defaults={'federation_id': f'team_{team_name.lower().replace(" ", "_")}'}
            # )
            # 
            # standing, created = Standing.objects.get_or_create(
            #     league=league,
            #     team=team,
            #     defaults={
            #         'position': int(item.get('position', 0)),
            #         'total_points': int(item.get('points', 0))
            #     }
            # )
            # 
            # if created:
            #     created_count += 1
    
    except Exception as e:
        logger.error(f'Error creating standings: {e}')
    
    return created_count


def create_matches_from_data(league: League, matches_data: List[Dict]) -> int:
    """
    Create Match objects from scraped data
    
    Args:
        league: League object
        matches_data: List of match dictionaries
    
    Returns:
        Number of matches created/updated
    """
    created_count = 0
    
    try:
        for item in matches_data:
            # Extract match information
            home_team_text = item.get('home_team', '')
            away_team_text = item.get('away_team', '')
            match_date_str = item.get('match_date', '')
            
            if not all([home_team_text, away_team_text, match_date_str]):
                continue
            
            # Parse date
            try:
                # This is a simplified date parsing - adjust based on actual format
                match_date = timezone.datetime.fromisoformat(match_date_str.replace('Z', '+00:00'))
            except ValueError:
                logger.warning(f'Could not parse date: {match_date_str}')
                continue
            
            # Create or update match
            match, created = Match.objects.get_or_create(
                league=league,
                home_team_text=home_team_text,
                away_team_text=away_team_text,
                match_date=match_date,
                defaults={
                    'status': item.get('status', 'scheduled'),
                    'venue': item.get('venue', ''),
                    'home_score': item.get('home_score'),
                    'away_score': item.get('away_score'),
                    'is_friendly': False
                }
            )
            
            if created:
                created_count += 1
    
    except Exception as e:
        logger.error(f'Error creating matches: {e}')
    
    return created_count


def get_league_statistics(league: League) -> Dict:
    """Get statistics for a league"""
    try:
        matches = league.matches.all()
        standings = league.standings.all()
        
        return {
            'total_matches': matches.count(),
            'finished_matches': matches.filter(status='finished').count(),
            'scheduled_matches': matches.filter(status='scheduled').count(),
            'total_teams': standings.count(),
            'last_updated': league.updated_at.isoformat() if hasattr(league, 'updated_at') else None
        }
        
    except Exception as e:
        logger.error(f'Error getting league statistics: {e}')
        return {'error': str(e)}