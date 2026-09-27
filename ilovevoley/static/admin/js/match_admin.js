document.addEventListener('DOMContentLoaded', function() {
    const leagueSelect = document.getElementById('id_league');
    const homeTeamSelect = document.getElementById('id_home_team');
    const awayTeamSelect = document.getElementById('id_away_team');
    const filterCheckbox = document.getElementById('id_filter_by_category');
    
    if (!leagueSelect || !homeTeamSelect || !awayTeamSelect || !filterCheckbox) {
        return; // No están todos los elementos necesarios
    }
    
    function updateTeamOptions() {
        const leagueId = leagueSelect.value;
        const filterByCategory = filterCheckbox.checked;
        
        if (!leagueId) {
            return; // No hay liga seleccionada
        }
        
        // Deshabilitar los selects mientras carga
        homeTeamSelect.disabled = true;
        awayTeamSelect.disabled = true;
        
        // Guardar selecciones actuales
        const currentHomeTeam = homeTeamSelect.value;
        const currentAwayTeam = awayTeamSelect.value;
        
        // Hacer petición AJAX
        const url = `/competitions/ajax/teams-by-league-category/?league_id=${leagueId}&filter_by_category=${filterByCategory}`;
        
        fetch(url)
            .then(response => response.json())
            .then(data => {
                // Limpiar opciones actuales
                homeTeamSelect.innerHTML = '<option value="">---------</option>';
                awayTeamSelect.innerHTML = '<option value="">---------</option>';
                
                // Agregar nuevas opciones
                data.teams.forEach(team => {
                    const homeOption = new Option(team.text, team.id);
                    const awayOption = new Option(team.text, team.id);
                    
                    homeTeamSelect.add(homeOption);
                    awayTeamSelect.add(awayOption);
                });
                
                // Restaurar selecciones si siguen siendo válidas
                if (currentHomeTeam) {
                    homeTeamSelect.value = currentHomeTeam;
                }
                if (currentAwayTeam) {
                    awayTeamSelect.value = currentAwayTeam;
                }
                
                // Reactivar los selects
                homeTeamSelect.disabled = false;
                awayTeamSelect.disabled = false;
                
                // Mostrar información sobre el filtrado
                updateFilterInfo(data.teams.length, filterByCategory);
            })
            .catch(error => {
                console.error('Error loading teams:', error);
                homeTeamSelect.disabled = false;
                awayTeamSelect.disabled = false;
            });
    }
    
    function updateFilterInfo(teamCount, filtered) {
        // Buscar o crear elemento de información
        let infoElement = document.getElementById('team-filter-info');
        if (!infoElement) {
            infoElement = document.createElement('div');
            infoElement.id = 'team-filter-info';
            infoElement.style.cssText = 'margin-top: 5px; font-size: 12px; color: #666; font-style: italic;';
            
            // Insertar después del checkbox de filtrado
            const filterRow = filterCheckbox.closest('.form-row');
            if (filterRow) {
                filterRow.appendChild(infoElement);
            }
        }
        
        if (filtered) {
            infoElement.textContent = `Mostrando ${teamCount} equipos de la misma categoría que la liga.`;
            infoElement.style.color = '#00a86b';
        } else {
            infoElement.textContent = `Mostrando todos los ${teamCount} equipos disponibles.`;
            infoElement.style.color = '#666';
        }
    }
    
    // Event listeners
    leagueSelect.addEventListener('change', updateTeamOptions);
    filterCheckbox.addEventListener('change', updateTeamOptions);
    
    // Ejecutar filtrado inicial si hay liga seleccionada
    if (leagueSelect.value) {
        updateTeamOptions();
    }
});