"""
Query Router - Clasifica consultas y decide la estrategia más eficiente
"""
import re
import unicodedata
from datetime import datetime, date, timedelta
from videosvoley.videos.models import Match, Standing, League, Team, Club
from django.db.models import Q
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class QueryRouter:
    """Router inteligente para consultas de voleibol"""
    
    def __init__(self, user=None):
        self.user = user
        # Categorías preferidas del usuario (si tiene perfil configurado)
        self.user_categories = self._get_user_categories()
    
    def _get_user_categories(self):
        """Obtener categorías de interés del usuario"""
        if self.user and hasattr(self.user, 'category_preferences'):
            return self.user.category_preferences.all()
        # Fallback: todas las categorías por ahora
        return []
    
    def route_query(self, query: str):
        """
        Clasifica la consulta y decide qué estrategia usar
        Returns: dict con 'strategy', 'response', 'confidence'
        """
        query_lower = query.lower().strip()
        
        # 1. Detectar consultas sobre próximos partidos
        if self._is_next_match_query(query_lower):
            return self._handle_next_match_query(query_lower)
        
        # 1.5. Detectar consultas específicas de enfrentamiento
        if self._is_versus_query(query_lower):
            return self._handle_versus_query(query_lower)
        
        # 2. Detectar consultas específicas sobre puntos del equipo (ANTES de clasificación)
        if self._is_team_points_query(query_lower):
            return self._handle_team_points_query(query_lower)
        
        # 3. Detectar consultas sobre estadísticas (tantos/goles) (ANTES de clasificación)
        if self._is_team_stats_query(query_lower):
            return self._handle_team_stats_query(query_lower)
        
        # 4. Detectar consultas sobre clasificación (DESPUÉS de consultas específicas)
        if self._is_standings_query(query_lower):
            return self._handle_standings_query(query_lower)
        
        # 5. Detectar consultas sobre resultados pasados
        if self._is_past_match_query(query_lower):
            return self._handle_past_match_query(query_lower)
        
        # 5.5. Detectar consultas sobre resultados de periodo (semana/mes)
        if self._is_period_results_query(query_lower):
            return self._handle_period_results_query(query_lower)
        
        # 5.6. Detectar consultas de análisis/tendencias (racha, mejor equipo, etc.)
        if self._is_analysis_query(query_lower):
            return self._handle_analysis_query(query_lower)
        
        # 6. Detectar consultas del reglamento
        if self._is_rules_query(query_lower):
            return {
                'strategy': 'rag_rules',
                'response': None,
                'confidence': 0.8,
                'reason': 'Consulta sobre reglamento - usar RAG'
            }
        
        # 5. Todo lo demás -> RAG completo
        return {
            'strategy': 'rag_full',
            'response': None,
            'confidence': 0.5,
            'reason': 'Consulta general - usar RAG completo'
        }
    
    def _is_next_match_query(self, query_lower: str) -> bool:
        """Detecta si pregunta por próximos partidos"""
        next_indicators = ['próximo', 'siguiente', 'cuándo', 'cuando', 'qué día', 'que dia']
        match_indicators = ['partido', 'partidos', 'jugamos', 'juega', 'jugará', 'jugar', 'encuentro', 'enfrentar', 'enfrentará', 'enfrentara']
        
        # También detectar patrones específicos de "del equipo"
        team_patterns = ['del ', 'de ', 'del equipo', 'de equipo']
        
        has_next = any(word in query_lower for word in next_indicators)
        has_match = any(word in query_lower for word in match_indicators)
        has_team_pattern = any(pattern in query_lower for pattern in team_patterns)
        
        return (has_next and has_match) or (has_team_pattern and has_match and ('próximo' in query_lower or 'cuándo' in query_lower or 'cuando' in query_lower))
    
    def _is_standings_query(self, query_lower: str) -> bool:
        """Detecta si pregunta por clasificaciones"""
        standings_indicators = [
            'clasificación', 'clasificacion', 'tabla', 'posición', 'posicion',
            'puntos', 'ranking', 'como va', 'cómo va', 'puesto'
        ]
        return any(word in query_lower for word in standings_indicators)
    
    def _is_past_match_query(self, query_lower: str) -> bool:
        """Detecta si pregunta por partidos pasados/resultados"""
        past_indicators = ['último', 'ultimo', 'anterior', 'resultado', 'cómo fue', 'como fue']
        match_indicators = ['partido', 'partidos', 'encuentro']
        
        has_past = any(word in query_lower for word in past_indicators)
        has_match = any(word in query_lower for word in match_indicators)
        
        return has_past and has_match
    
    def _is_rules_query(self, query_lower: str) -> bool:
        """Detecta si pregunta sobre reglamento"""
        rules_indicators = [
            'reglamento', 'reglas', 'norma', 'según el reglamento', 
            'altura', 'red', 'rotación', 'rotacion', 'saque', 'toque',
            'falta', 'doble', 'medidas', 'campo', 'cancha'
        ]
        return any(word in query_lower for word in rules_indicators)
    
    def _is_versus_query(self, query_lower: str) -> bool:
        """Detecta si es una consulta específica de enfrentamiento"""
        versus_indicators = [
            'contra', 'enfrentar', 'enfrentará', 'enfrentara', 'enfrenta', 'enfrentamos', 
            'se enfrenta', 'se enfrentan', 'vs', 'versus'
        ]
        team_indicators = ['equipo', 'sant joan', 'artà', 'arta', 'pórtol', 'portol', 'alaró', 'alaro']
        
        has_versus = any(word in query_lower for word in versus_indicators)
        has_team = any(team in query_lower for team in team_indicators)
        
        # También detectar patrones como "cuándo se volverá a enfrentar"
        specific_patterns = [
            'volverá a enfrentar', 'volvera a enfrentar', 
            'próximo enfrentamiento', 'proximo enfrentamiento',
            'cuándo jugará', 'cuando jugara', 'se enfrenta al', 'enfrenta al'
        ]
        has_specific_pattern = any(pattern in query_lower for pattern in specific_patterns)
        
        return has_versus and has_team or has_specific_pattern
    
    def _is_team_points_query(self, query_lower: str) -> bool:
        """Detecta si pregunta específicamente por los puntos del equipo"""
        points_indicators = ['puntos', 'puntaje', 'puntuación', 'puntuacion']
        our_team_indicators = ['nuestro', 'nuestros', 'nosotros', 'sant josep', 'equipo']
        quantity_indicators = ['cuántos', 'cuantos', 'qué', 'que', 'cómo', 'como']
        
        has_points = any(word in query_lower for word in points_indicators)
        has_our_team = any(word in query_lower for word in our_team_indicators)
        has_quantity = any(word in query_lower for word in quantity_indicators)
        
        return has_points and (has_our_team or has_quantity) and 'lleva' in query_lower
    
    def _is_team_stats_query(self, query_lower: str) -> bool:
        """Detecta si pregunta por estadísticas del equipo (tantos, goles, puntos a favor)"""
        stats_indicators = ['tantos', 'goles', 'puntos a favor', 'puntos en contra', 'sets', 'marcado', 'anotado']
        quantity_indicators = ['cuántos', 'cuantos', 'qué', 'que', 'cómo', 'como']
        
        has_stats = any(indicator in query_lower for indicator in stats_indicators)
        has_quantity = any(word in query_lower for word in quantity_indicators)
        
        return has_stats and has_quantity
    
    def _is_period_results_query(self, query_lower: str) -> bool:
        """Detecta si pregunta por resultados de un periodo específico"""
        results_indicators = ['resultados', 'resultado', 'partidos', 'jugaron', 'encuentros', 'jornada', 'se jugaron']
        period_indicators = ['semana', 'mes', 'esta semana', 'este mes', 'último mes', 'ultima semana', 'esta', 'este']
        
        has_results = any(indicator in query_lower for indicator in results_indicators)
        has_period = any(indicator in query_lower for indicator in period_indicators)
        
        # También detectar preguntas directas sobre partidos jugados
        direct_patterns = ['qué partidos', 'que partidos', 'partidos jugados', 'partidos se jugaron']
        has_direct_pattern = any(pattern in query_lower for pattern in direct_patterns)
        
        return (has_results and has_period) or has_direct_pattern
    
    def _is_analysis_query(self, query_lower: str) -> bool:
        """Detecta si es una consulta de análisis/tendencias"""
        analysis_indicators = [
            'racha', 'mejor', 'peor', 'líder', 'lider', 'primero', 'último', 'ultimo',
            'más victorias', 'mas victorias', 'menos derrotas', 'invicto', 'ganando',
            'perdiendo', 'tendencia', 'evolución', 'evolucion', 'progreso'
        ]
        
        team_context = ['equipo', 'equipos', 'quien']
        
        has_analysis = any(indicator in query_lower for indicator in analysis_indicators)
        has_team_context = any(context in query_lower for context in team_context)
        
        # Patrones específicos
        specific_patterns = [
            'qué equipo', 'que equipo', 'cuál equipo', 'cual equipo',
            'mejor racha', 'peor racha', 'quién va', 'quien va',
            'más ganados', 'mas ganados', 'menos perdidos'
        ]
        has_specific_pattern = any(pattern in query_lower for pattern in specific_patterns)
        
        return (has_analysis and has_team_context) or has_specific_pattern
    
    def _extract_category(self, query_lower: str) -> str:
        """Extrae la categoría mencionada en la consulta"""
        categories = {
            'alevín': ['alevin', 'alevín'],
            'infantil': ['infantil'],
            'cadete': ['cadete'],
            'juvenil': ['juvenil'],
            'senior': ['senior']
        }
        
        for category, keywords in categories.items():
            if any(keyword in query_lower for keyword in keywords):
                return category
        
        return None
    
    def _normalize_text(self, text: str) -> str:
        """Normalizar texto quitando acentos, puntuación y convirtiendo a minúsculas"""
        # Quitar acentos
        normalized = unicodedata.normalize('NFD', text)
        without_accents = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
        # Quitar puntuación (solo letras y espacios)
        clean_text = re.sub(r'[^\w\s]', '', without_accents)
        return clean_text.lower().strip()

    def _search_team_by_keyword(self, keyword: str) -> bool:
        """Busca si existe un equipo con la keyword dada"""
        try:
            logger.info(f"Buscando keyword: '{keyword}'")
            # Buscar en nombres de equipos
            team_exists = Team.objects.filter(name__icontains=keyword).exists()
            logger.info(f"Team.name icontains '{keyword}': {team_exists}")
            if team_exists:
                return True
            # Buscar en nombres oficiales de clubes
            club_exists = Team.objects.filter(club__isnull=False, club__official_name__icontains=keyword).exists()
            logger.info(f"Club.official_name icontains '{keyword}': {club_exists}")
            if club_exists:
                return True
            return False
        except Exception as e:
            logger.error(f"Error buscando keyword '{keyword}': {e}")
            return False

    def _extract_team_name(self, query_lower: str) -> str:
        """Extrae el nombre del equipo específico mencionado en la consulta usando la BD dinámicamente"""
        words = query_lower.split()
        logger.info(f"Analizando palabras: {words}")
        
        # 1. Buscar patrones específicos "del EQUIPO" o "de EQUIPO"
        team_from_pattern = self._extract_team_from_pattern(query_lower)
        if team_from_pattern:
            logger.info(f"Equipo extraído de patrón del/de: '{team_from_pattern}'")
            return team_from_pattern
        
        # 2. Buscar cada palabra individual (mínimo 3 caracteres para evitar ruido)
        # Excluir palabras comunes que no son equipos
        excluded_words = ['del', 'de', 'la', 'el', 'en', 'con', 'para', 'por', 'contra', 'ante', 'bajo', 'sobre']
        
        for word in words:
            normalized_word = self._normalize_text(word)
            logger.info(f"Palabra normalizada: '{word}' -> '{normalized_word}' (len: {len(normalized_word)})")
            if len(normalized_word) >= 3 and normalized_word not in excluded_words and self._search_team_by_keyword(normalized_word):
                logger.info(f"Equipo encontrado con palabra individual: '{normalized_word}'")
                return normalized_word
        
        # 3. Buscar combinaciones de 2 palabras consecutivas
        for i in range(len(words) - 1):
            word1 = self._normalize_text(words[i])
            word2 = self._normalize_text(words[i + 1])
            combined = f"{word1} {word2}"
            if self._search_team_by_keyword(combined):
                logger.info(f"Equipo encontrado con combinación: '{combined}'")
                return combined
        
        # 4. Buscar combinaciones de 3 palabras (para casos como "club deportivo xyz")
        for i in range(len(words) - 2):
            word1 = self._normalize_text(words[i])
            word2 = self._normalize_text(words[i + 1])
            word3 = self._normalize_text(words[i + 2])
            combined = f"{word1} {word2} {word3}"
            if self._search_team_by_keyword(combined):
                logger.info(f"Equipo encontrado con triple combinación: '{combined}'")
                return combined
        
        # Si no encuentra equipos específicos, usar el del club por defecto
        default_team = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
        logger.info(f"No se detectó equipo específico en: '{query_lower}', usando por defecto: '{default_team}'")
        return default_team
    
    def _extract_team_from_pattern(self, query_lower: str) -> str:
        """Extrae equipos usando patrones específicos como 'del Alaró', 'de Pórtol'"""
        import re
        
        # Patrones: "del EQUIPO", "de EQUIPO", "del equipo EQUIPO", etc.
        patterns = [
            r'del\s+([a-záéíóúñü]+)',           # del Alaró
            r'de\s+([a-záéíóúñü]+)',            # de Pórtol  
            r'del\s+equipo\s+([a-záéíóúñü\s]+)',  # del equipo Sant Joan
            r'de\s+equipo\s+([a-záéíóúñü\s]+)',   # de equipo X
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                candidate_team = match.group(1).strip()
                logger.info(f"Candidato a equipo del patrón '{pattern}': '{candidate_team}'")
                # Verificar si existe en la BD
                if self._search_team_by_keyword(candidate_team):
                    return candidate_team
        
        return None
    
    def _handle_next_match_query(self, query_lower: str):
        """Maneja consultas sobre próximos partidos"""
        try:
            category = self._extract_category(query_lower)
            team_name = self._extract_team_name(query_lower)
            
            # Buscar próximo partido
            from django.utils import timezone
            today = timezone.now().date()
            
            # Detectar si es una consulta de enfrentamiento específico
            is_versus_query = any(word in query_lower for word in ['contra', 'enfrentar', 'enfrentará', 'enfrentara'])
            club_team = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
            
            if is_versus_query and team_name != club_team.lower():
                # Buscar partidos específicos entre el club y el equipo mencionado
                future_matches = Match.objects.filter(
                    match_date__date__gt=today
                ).filter(
                    (Q(home_team__name__icontains=club_team) | Q(home_team_text__icontains=club_team)) &
                    (Q(away_team__name__icontains=team_name) | Q(away_team_text__icontains=team_name))
                    |
                    (Q(home_team__name__icontains=team_name) | Q(home_team_text__icontains=team_name)) &
                    (Q(away_team__name__icontains=club_team) | Q(away_team_text__icontains=club_team))
                ).order_by('match_date')
            else:
                # Filtrar partidos del equipo especificado (comportamiento original)
                future_matches = Match.objects.filter(
                    match_date__date__gt=today
                ).filter(
                    Q(home_team__name__icontains=team_name) | 
                    Q(away_team__name__icontains=team_name) |
                    Q(home_team_text__icontains=team_name) |
                    Q(away_team_text__icontains=team_name)
                ).order_by('match_date')
            
            # Filtrar por categoría si se especifica
            if category:
                future_matches = future_matches.filter(
                    league__name__icontains=category
                )
            
            match = future_matches.first()
            
            if match:
                response = self._format_next_match_response(match, category, team_name)
                return {
                    'strategy': 'direct_query',
                    'response': response,
                    'confidence': 0.9,
                    'reason': f'Consulta sobre próximo partido{" de " + category if category else ""}{" del " + team_name if team_name else ""}'
                }
            else:
                return {
                    'strategy': 'direct_query', 
                    'response': f"No hay próximos partidos programados{' de ' + category if category else ''}.",
                    'confidence': 0.8,
                    'reason': 'No se encontraron partidos futuros'
                }
                
        except Exception as e:
            logger.error(f"Error en consulta de próximo partido: {e}")
            return {
                'strategy': 'rag_fallback',
                'response': None,
                'confidence': 0.3,
                'reason': f'Error en consulta directa: {e}'
            }
    
    def _handle_versus_query(self, query_lower: str):
        """Maneja consultas específicas de enfrentamiento"""
        try:
            category = self._extract_category(query_lower)
            
            # Extraer los dos equipos de la consulta
            club_team = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
            opponent_team = self._extract_team_name(query_lower)
            
            from django.utils import timezone
            today = timezone.now().date()
            
            # Buscar próximos enfrentamientos entre ambos equipos
            future_matches = Match.objects.filter(
                match_date__date__gt=today
            ).filter(
                (Q(home_team__name__icontains=club_team) | Q(home_team_text__icontains=club_team)) &
                (Q(away_team__name__icontains=opponent_team) | Q(away_team_text__icontains=opponent_team))
                |
                (Q(home_team__name__icontains=opponent_team) | Q(home_team_text__icontains=opponent_team)) &
                (Q(away_team__name__icontains=club_team) | Q(away_team_text__icontains=club_team))
            ).order_by('match_date')
            
            # Filtrar por categoría si se especifica
            if category:
                future_matches = future_matches.filter(
                    league__name__icontains=category
                )
            
            match = future_matches.first()
            
            if match:
                response = self._format_versus_match_response(match, category, opponent_team)
                return {
                    'strategy': 'direct_query',
                    'response': response,
                    'confidence': 0.9,
                    'reason': f'Consulta sobre enfrentamiento{" de " + category if category else ""} contra {opponent_team}'
                }
            else:
                return {
                    'strategy': 'direct_query',
                    'response': f"No hay enfrentamientos programados{' de ' + category if category else ''} contra {opponent_team}.",
                    'confidence': 0.8,
                    'reason': 'No se encontraron enfrentamientos futuros'
                }
                
        except Exception as e:
            logger.error(f"Error en consulta de enfrentamiento: {e}")
            return {
                'strategy': 'rag_fallback',
                'response': None,
                'confidence': 0.3,
                'reason': f'Error en consulta directa: {e}'
            }
    
    def _handle_team_points_query(self, query_lower: str):
        """Maneja consultas específicas sobre puntos del equipo"""
        try:
            category = self._extract_category(query_lower)
            club_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
            
            # Buscar clasificación del equipo
            standings = Standing.objects.select_related('team', 'league').filter(
                team__name__icontains=club_name
            )
            
            # Filtrar por categoría si se especifica
            if category:
                standings = standings.filter(league__name__icontains=category)
            
            standing = standings.first()
            
            if standing:
                response = f"📊 <strong>Puntos del equipo{' ' + category if category else ''}:</strong>\n\n"
                response += f"🏆 <strong>{standing.team.name}</strong>\n"
                response += f"📈 <strong>{standing.total_points} puntos</strong> (posición {standing.position})\n"
                response += f"🏅 Liga: {standing.league.name}\n"
                
                return {
                    'strategy': 'direct_query',
                    'response': response,
                    'confidence': 0.9,
                    'reason': f'Consulta sobre puntos del equipo{" de " + category if category else ""}'
                }
            else:
                return {
                    'strategy': 'direct_query',
                    'response': f"No se encontró información de puntos{' de ' + category if category else ''}.",
                    'confidence': 0.8,
                    'reason': 'No se encontró equipo en clasificaciones'
                }
                
        except Exception as e:
            logger.error(f"Error en consulta de puntos: {e}")
            return {
                'strategy': 'rag_fallback',
                'response': None,
                'confidence': 0.3,
                'reason': f'Error en consulta directa: {e}'
            }
    
    def _handle_team_stats_query(self, query_lower: str):
        """Maneja consultas sobre estadísticas del equipo"""
        try:
            category = self._extract_category(query_lower)
            team_name = self._extract_team_name(query_lower)
            
            # Buscar clasificación del equipo para obtener estadísticas
            standings = Standing.objects.select_related('team', 'league')
            
            if team_name and team_name.upper() != getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP'):
                standings = standings.filter(team__name__icontains=team_name)
            else:
                # Si no especifica equipo o es el nuestro
                club_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
                standings = standings.filter(team__name__icontains=club_name)
            
            # Filtrar por categoría si se especifica
            if category:
                standings = standings.filter(league__name__icontains=category)
            
            standing = standings.first()
            
            if standing:
                response = f"📊 <strong>Estadísticas de {standing.team.name}{' (' + category + ')' if category else ''}:</strong>\n\n"
                response += f"⚽ <strong>Puntos a favor:</strong> {standing.points_for}\n"
                response += f"🛡️ <strong>Puntos en contra:</strong> {standing.points_against}\n"
                response += f"📈 <strong>Sets ganados:</strong> {standing.sets_for}\n"
                response += f"📉 <strong>Sets perdidos:</strong> {standing.sets_against}\n"
                response += f"🎯 <strong>Partidos ganados:</strong> {standing.won} / {standing.played}\n"
                
                return {
                    'strategy': 'direct_query',
                    'response': response,
                    'confidence': 0.9,
                    'reason': f'Consulta sobre estadísticas del equipo{" de " + category if category else ""}'
                }
            else:
                return {
                    'strategy': 'direct_query',
                    'response': f"No se encontraron estadísticas{' de ' + category if category else ''}.",
                    'confidence': 0.8,
                    'reason': 'No se encontró equipo en clasificaciones'
                }
                
        except Exception as e:
            logger.error(f"Error en consulta de estadísticas: {e}")
            return {
                'strategy': 'rag_fallback',
                'response': None,
                'confidence': 0.3,
                'reason': f'Error en consulta directa: {e}'
            }
    
    def _handle_period_results_query(self, query_lower: str):
        """Maneja consultas sobre resultados de periodos específicos"""
        try:
            category = self._extract_category(query_lower)
            
            # Determinar el periodo
            from django.utils import timezone
            import datetime
            today = timezone.now().date()
            
            # Por defecto, esta semana (lunes a domingo)
            if 'esta semana' in query_lower or 'semana' in query_lower:
                # Obtener lunes de esta semana
                days_since_monday = today.weekday()
                start_date = today - datetime.timedelta(days=days_since_monday)
                end_date = start_date + datetime.timedelta(days=6)
                period_name = "esta semana"
            elif 'este mes' in query_lower or 'mes' in query_lower:
                start_date = today.replace(day=1)
                # Último día del mes
                if today.month == 12:
                    end_date = today.replace(year=today.year+1, month=1, day=1) - datetime.timedelta(days=1)
                else:
                    end_date = today.replace(month=today.month+1, day=1) - datetime.timedelta(days=1)
                period_name = "este mes"
            else:
                # Por defecto, últimos 7 días
                start_date = today - datetime.timedelta(days=7)
                end_date = today
                period_name = "últimos 7 días"
            
            # Buscar partidos del periodo con resultados
            matches = Match.objects.filter(
                match_date__date__gte=start_date,
                match_date__date__lte=end_date
            ).filter(
                home_score__isnull=False,
                away_score__isnull=False
            ).order_by('-match_date')
            
            # Filtrar por categoría si se especifica
            if category:
                matches = matches.filter(league__name__icontains=category)
            
            if matches:
                response = self._format_period_results_response(matches, category, period_name, start_date, end_date)
                return {
                    'strategy': 'direct_query',
                    'response': response,
                    'confidence': 0.9,
                    'reason': f'Consulta sobre resultados de {period_name}{" de " + category if category else ""}'
                }
            else:
                return {
                    'strategy': 'direct_query',
                    'response': f"No hay resultados de {period_name}{' de ' + category if category else ''}.",
                    'confidence': 0.8,
                    'reason': f'No se encontraron partidos en {period_name}'
                }
                
        except Exception as e:
            logger.error(f"Error en consulta de resultados de periodo: {e}")
            return {
                'strategy': 'rag_fallback',
                'response': None,
                'confidence': 0.3,
                'reason': f'Error en consulta directa: {e}'
            }
    
    def _handle_analysis_query(self, query_lower: str):
        """Maneja consultas de análisis/tendencias"""
        try:
            category = self._extract_category(query_lower)
            
            # Por ahora, implementamos solo racha de victorias
            if 'racha' in query_lower or 'mejor' in query_lower:
                return self._calculate_winning_streaks(category, query_lower)
            else:
                # Para otras consultas de análisis, usar el sistema de clasificaciones
                return self._handle_standings_query(query_lower)
                
        except Exception as e:
            logger.error(f"Error en consulta de análisis: {e}")
            return {
                'strategy': 'rag_fallback',
                'response': None,
                'confidence': 0.3,
                'reason': f'Error en consulta directa: {e}'
            }
    
    def _calculate_winning_streaks(self, category=None, query_lower=""):
        """Calcula las rachas de victoria actuales de los equipos (solo temporada actual)"""
        try:
            # Determinar si pregunta por mejor o peor racha
            is_worst = 'peor' in query_lower or 'peores' in query_lower or 'último' in query_lower or 'ultimo' in query_lower
            
            # Calcular temporada actual dinámicamente
            from django.utils import timezone
            now = timezone.now()
            year = now.year
            
            # Lógica simple: si estamos antes de septiembre, usar temporada anterior
            if now.month < 9:
                current_season = f"{year-1}-{str(year)[2:]}"
            else:
                current_season = f"{year}-{str(year+1)[2:]}"
            
            # Para simplificar, usaremos los datos de Standing que ya tenemos
            # Filtrar solo por temporada actual
            standings = Standing.objects.select_related('team', 'league').filter(
                league__season=current_season
            )
            if category:
                standings = standings.filter(league__name__icontains=category)
            
            # Ordenar según si pregunta por mejor o peor
            if is_worst:
                # Ordenar por peores estadísticas: más derrotas, menos puntos
                worst_teams = standings.order_by('won', 'total_points', '-lost')[:5]
                selected_teams = worst_teams
                racha_type = "peor racha"
            else:
                # Ordenar por mejores estadísticas
                best_teams = standings.order_by('-won', '-total_points', 'lost')[:5]
                selected_teams = best_teams
                racha_type = "mejor racha"
            
            if selected_teams:
                # Emoji diferente según si es mejor o peor
                main_emoji = "💀" if is_worst else "🏆"
                response = f"{main_emoji} <strong>Equipos con {racha_type}{' de ' + category if category else ''}:</strong>\n\n"
                
                for i, standing in enumerate(selected_teams, 1):
                    # Para mejor racha, saltar equipos sin victorias
                    # Para peor racha, incluir todos los equipos
                    if not is_worst and standing.won == 0:
                        continue
                        
                    emoji = "💀" if is_worst and i == 1 else "😵" if is_worst and i == 2 else "😔" if is_worst and i == 3 else "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                    win_rate = (standing.won / standing.played * 100) if standing.played > 0 else 0
                    loss_rate = (standing.lost / standing.played * 100) if standing.played > 0 else 0
                    
                    response += f"{emoji} <strong>{standing.team.name}</strong>\n"
                    
                    if is_worst:
                        # Para peor racha, enfocarse en derrotas y mala posición
                        response += f"   📉 <strong>{standing.lost} derrotas</strong> de {standing.played} partidos ({loss_rate:.0f}% derrotas)\n"
                        response += f"   💔 Solo {standing.won} victorias - {standing.total_points} puntos\n"
                        response += f"   📍 Posición: {standing.position}º en la clasificación\n"
                    else:
                        # Para mejor racha, enfocarse en victorias
                        response += f"   📈 <strong>{standing.won} victorias</strong> de {standing.played} partidos ({win_rate:.0f}%)\n"
                        response += f"   🏅 {standing.total_points} puntos - Posición {standing.position}\n"
                    
                    if standing.league:
                        response += f"   🏆 {standing.league.name}\n"
                    response += "\n"
                
                return {
                    'strategy': 'direct_query',
                    'response': response,
                    'confidence': 0.9,
                    'reason': f'Consulta sobre {racha_type}{" de " + category if category else ""}'
                }
            else:
                return {
                    'strategy': 'direct_query',
                    'response': f"No hay datos de racha disponibles{' de ' + category if category else ''}.",
                    'confidence': 0.8,
                    'reason': 'No se encontraron equipos'
                }
                
        except Exception as e:
            logger.error(f"Error calculando rachas: {e}")
            return {
                'strategy': 'rag_fallback',
                'response': None,
                'confidence': 0.3,
                'reason': f'Error en cálculo de rachas: {e}'
            }
    
    def _handle_standings_query(self, query_lower: str):
        """Maneja consultas sobre clasificaciones"""
        try:
            category = self._extract_category(query_lower)
            
            # Buscar clasificaciones recientes
            standings = Standing.objects.select_related('team', 'league')
            
            # Filtrar por categoría si se especifica  
            if category:
                standings = standings.filter(league__name__icontains=category)
            
            standings = standings.order_by('league_id', 'position')
            
            if standings:
                response = self._format_standings_response(standings, category)
                return {
                    'strategy': 'direct_query',
                    'response': response, 
                    'confidence': 0.9,
                    'reason': f'Consulta sobre clasificación{" de " + category if category else ""}'
                }
            else:
                return {
                    'strategy': 'direct_query',
                    'response': f"No hay clasificaciones disponibles{' de ' + category if category else ''}.",
                    'confidence': 0.8,
                    'reason': 'No se encontraron clasificaciones'
                }
                
        except Exception as e:
            logger.error(f"Error en consulta de clasificación: {e}")
            return {
                'strategy': 'rag_fallback',
                'response': None,
                'confidence': 0.3,
                'reason': f'Error en consulta directa: {e}'
            }
    
    def _handle_past_match_query(self, query_lower: str):
        """Maneja consultas sobre partidos pasados"""
        try:
            category = self._extract_category(query_lower)
            
            # Buscar último partido
            from django.utils import timezone
            today = timezone.now().date()
            club_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
            
            # Filtrar solo partidos del club
            past_matches = Match.objects.filter(
                match_date__date__lt=today
            ).filter(
                Q(home_team__name__icontains=club_name) | 
                Q(away_team__name__icontains=club_name) |
                Q(home_team_text__icontains=club_name) |
                Q(away_team_text__icontains=club_name)
            ).order_by('-match_date')
            
            # Filtrar por categoría si se especifica
            if category:
                past_matches = past_matches.filter(
                    league__name__icontains=category
                )
            
            match = past_matches.first()
            
            if match:
                response = self._format_past_match_response(match, category)
                return {
                    'strategy': 'direct_query',
                    'response': response,
                    'confidence': 0.9,
                    'reason': f'Consulta sobre último partido{" de " + category if category else ""}'
                }
            else:
                return {
                    'strategy': 'direct_query',
                    'response': f"No hay partidos pasados{' de ' + category if category else ''}.",
                    'confidence': 0.8,
                    'reason': 'No se encontraron partidos pasados'
                }
                
        except Exception as e:
            logger.error(f"Error en consulta de partido pasado: {e}")
            return {
                'strategy': 'rag_fallback',
                'response': None,
                'confidence': 0.3,
                'reason': f'Error en consulta directa: {e}'
            }
    
    def _format_next_match_response(self, match, category=None, team_name=None):
        """Formatea respuesta sobre próximo partido"""
        date_str = match.match_date.strftime('%d/%m/%Y')
        day_name = match.match_date.strftime('%A')
        
        # Traducir día de la semana
        days = {
            'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
            'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 
            'Sunday': 'Domingo'
        }
        day_spanish = days.get(day_name, day_name)
        
        response = f"🏐 <strong>Próximo partido{' de ' + category if category else ''}:</strong>\n\n"
        response += f"📅 <strong>{day_spanish}, {date_str}</strong>\n"
        response += f"⚡ <strong>{match.home_team} vs {match.away_team}</strong>\n"
        
        if match.venue:
            response += f"📍 <strong>Lugar</strong>: {match.venue}\n"
        
        if match.league:
            response += f"🏆 <strong>Liga</strong>: {match.league.name}\n"
        
        # Calcular días hasta el partido
        if hasattr(match.match_date, 'date'):
            match_date = match.match_date.date()  # Si es datetime, extraer la fecha
        else:
            match_date = match.match_date  # Si ya es date
        days_until = (match_date - date.today()).days
        if days_until == 0:
            response += "\n🔥 <strong>¡Es hoy!</strong>"
        elif days_until == 1:
            response += "\n⏰ <strong>¡Es mañana!</strong>"
        else:
            response += f"\n⏰ <strong>Faltan {days_until} días</strong>"
        
        return response
    
    def _format_standings_response(self, standings, category=None):
        """Formatea respuesta sobre clasificaciones"""
        response = f"📊 <strong>Clasificación{' de ' + category if category else ''}:</strong>\n\n"
        
        # Agrupar por ligas
        leagues = {}
        for standing in standings:
            league_name = standing.league.name
            if league_name not in leagues:
                leagues[league_name] = []
            leagues[league_name].append(standing)
        
        # Formatear cada liga
        for league_name, league_standings in leagues.items():
            if len(leagues) > 1:  # Solo mostrar nombre si hay múltiples ligas
                response += f"<strong>{league_name}</strong>\n"
            
            for standing in league_standings:
                # Emoji según posición
                if standing.position == 1:
                    emoji = "🥇"
                elif standing.position == 2:
                    emoji = "🥈" 
                elif standing.position == 3:
                    emoji = "🥉"
                else:
                    emoji = f"{standing.position}."
                
                response += f"{emoji} <strong>{standing.team.name}</strong> - {standing.total_points} puntos\n"
            
            # Añadir separación entre ligas (excepto la última)
            if len(leagues) > 1 and league_name != list(leagues.keys())[-1]:
                response += "\n"
        
        return response
    
    def _format_versus_match_response(self, match, category=None, opponent_team=None):
        """Formatea respuesta sobre enfrentamiento específico"""
        date_str = match.match_date.strftime('%d/%m/%Y')
        day_name = match.match_date.strftime('%A')
        
        # Traducir día de la semana
        days = {
            'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
            'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 
            'Sunday': 'Domingo'
        }
        day_spanish = days.get(day_name, day_name)
        
        response = f"🏐 <strong>Próximo enfrentamiento{' de ' + category if category else ''}{' contra ' + opponent_team if opponent_team else ''}:</strong>\n\n"
        response += f"📅 <strong>{day_spanish}, {date_str}</strong>\n"
        response += f"⚡ <strong>{match.home_team} vs {match.away_team}</strong>\n"
        
        if match.venue:
            response += f"📍 <strong>Lugar</strong>: {match.venue}\n"
        
        if match.league:
            response += f"🏆 <strong>Liga</strong>: {match.league.name}\n"
        
        # Calcular días hasta el partido
        if hasattr(match.match_date, 'date'):
            match_date = match.match_date.date()  # Si es datetime, extraer la fecha
        else:
            match_date = match.match_date  # Si ya es date
        days_until = (match_date - date.today()).days
        if days_until == 0:
            response += "\n🔥 <strong>¡Es hoy!</strong>"
        elif days_until == 1:
            response += "\n⏰ <strong>¡Es mañana!</strong>"
        else:
            response += f"\n⏰ <strong>Faltan {days_until} días</strong>"
        
        return response
    
    def _format_period_results_response(self, matches, category=None, period_name="periodo", start_date=None, end_date=None):
        """Formatea respuesta sobre resultados de un periodo"""
        response = f"🏐 <strong>Resultados de {period_name}{' de ' + category if category else ''}:</strong>\n"
        if start_date and end_date:
            response += f"📅 <strong>{start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m/%Y')}</strong>\n\n"
        else:
            response += "\n"
        
        for match in matches:
            date_str = match.match_date.strftime('%d/%m')
            day_name = match.match_date.strftime('%A')
            
            # Traducir día de la semana
            days = {
                'Monday': 'Lun', 'Tuesday': 'Mar', 'Wednesday': 'Mié',
                'Thursday': 'Jue', 'Friday': 'Vie', 'Saturday': 'Sáb', 
                'Sunday': 'Dom'
            }
            day_spanish = days.get(day_name, day_name)
            
            response += f"📅 <strong>{day_spanish} {date_str}</strong> | "
            response += f"<strong>{match.home_team} {match.home_score} - {match.away_score} {match.away_team}</strong>\n"
            
            if match.league:
                response += f"   🏆 {match.league.name}\n"
            if match.venue:
                response += f"   📍 {match.venue}\n"
            response += "\n"
        
        response += f"📊 <strong>Total: {len(matches)} partidos jugados</strong>"
        return response
    
    def _format_past_match_response(self, match, category=None):
        """Formatea respuesta sobre partido pasado"""
        date_str = match.match_date.strftime('%d/%m/%Y')
        
        response = f"🏐 <strong>Último partido{' de ' + category if category else ''}:</strong>\n\n"
        response += f"📅 <strong>{date_str}</strong>\n"
        response += f"⚡ <strong>{match.home_team} vs {match.away_team}</strong>\n"
        
        if match.home_score is not None and match.away_score is not None:
            response += f"🏆 <strong>Resultado</strong>: {match.home_score} - {match.away_score}\n"
        
        if match.venue:
            response += f"📍 <strong>Lugar</strong>: {match.venue}\n"
        
        if match.league:
            response += f"🏆 <strong>Liga</strong>: {match.league.name}\n"
        
        return response