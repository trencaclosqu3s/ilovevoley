# 📚 Índice - Solución de Errores 500 en Producción

## 🎯 Inicio Rápido

**¿Tienes errores 500 en producción?** → Empieza aquí:

1. **[DIAGNOSTICO_ERRORES_PRODUCCION.md](DIAGNOSTICO_ERRORES_PRODUCCION.md)** ⭐ **GUÍA TÉCNICA PRINCIPAL**
   - Análisis de causas raíz (Google OAuth, Sites framework, Vision API)
   - Comandos específicos para cada problema
   - Checklist de verificación y prevención

---

## 📖 Documentación

### Para Administradores y Desarrolladores

| Archivo | Propósito |
|---------|-----------|
| **[DIAGNOSTICO_ERRORES_PRODUCCION.md](DIAGNOSTICO_ERRORES_PRODUCCION.md)** | Análisis técnico completo y resolución de errores |
| **[RESUMEN_MEJORAS.md](RESUMEN_MEJORAS.md)** | Resumen de cambios y protecciones aplicadas |
| **config/logging_production.py** | Configuración de logging de producción |

---

## 🛠 Herramientas Creadas

### Scripts de Diagnóstico

```bash
# 1. Script bash (visual, rápido)
bash check_config.sh

# 2. Comando Django (detallado)
python manage.py check_production_config

# 3. System checks de Django
python manage.py check --deploy
```

### Código Nuevo

```
ilovevoley/
├── core/
│   ├── checks.py                              # System checks automáticos
│   ├── management/
│   │   └── commands/
│   │       └── check_production_config.py     # Comando de diagnóstico
│   └── templates/
│       └── emails/
│           └── vision_api_error.html          # Notificación de errores
└── videos/
    └── views.py                               # Logging mejorado (modificado)
```

---

## 🚨 Problemas Comunes

### Error 500: Login con Google

**Documento**: [DIAGNOSTICO_ERRORES_PRODUCCION.md](DIAGNOSTICO_ERRORES_PRODUCCION.md)

**Causa más probable**: `Site.domain` incorrecto o callback OAuth no registrado

**Solución rápida**:
```bash
python manage.py shell -c "from django.contrib.sites.models import Site; s=Site.objects.get(id=1); s.domain='ilovevoley.es'; s.save()"
```

---

### Error 500: Subida de Imágenes

**Documento**: [DIAGNOSTICO_ERRORES_PRODUCCION.md](DIAGNOSTICO_ERRORES_PRODUCCION.md)

**Causa más probable**: Credenciales de Vision API no configuradas

**Solución rápida** (deshabilitar mientras se configuran):
```bash
# En .env:
GOOGLE_VISION_ENABLED=False
AUTO_MODERATION_ENABLED=False
```

---

## 📋 Flujo de Trabajo Recomendado

```
1. Consultar DIAGNOSTICO_ERRORES_PRODUCCION.md
   ↓
2. Ejecutar chequeo de configuración:
   docker compose run --rm web python manage.py check_production_config
   ↓
3. Seguir instrucciones específicas del diagnóstico
   ↓
4. Verificar en navegador
   ↓
5. ✅ Problema resuelto
```

---

## 🎓 Recursos Adicionales

### Configuración

- **env.production.example**: Plantilla de configuración para producción con comentarios detallados
- **config/logging_production.py**: Configuración de logging recomendada

### Documentación Django

- [Django Sites Framework](https://docs.djangoproject.com/en/5.2/ref/contrib/sites/)
- [django-allauth](https://docs.allauth.org/en/latest/)
- [Google Vision API](https://cloud.google.com/vision/docs)

### Monitoreo

- [Sentry](https://sentry.io/) - Tracking de errores
- [Prometheus](https://prometheus.io/) - Métricas
- [Grafana](https://grafana.com/) - Visualización

---

## 📊 Estadísticas de Archivos

| Tipo | Cantidad | Propósito |
|------|----------|-----------|
| Documentación | 5 archivos | Guías y referencias |
| Scripts | 1 archivo | Diagnóstico automático |
| Código Python | 3 archivos | Checks y comandos |
| Configuración | 2 archivos | Templates y logging |
| **Total** | **11 archivos** | **Sistema completo** |

---

## ✅ Checklist de Implementación

### Inmediato (Hoy)
- [ ] Leer README_ERRORES_PRODUCCION.md
- [ ] Ejecutar bash check_config.sh
- [ ] Corregir Site.domain si es necesario
- [ ] Verificar Google OAuth en admin
- [ ] Decidir sobre Vision API (configurar o deshabilitar)
- [ ] Probar login con Google
- [ ] Probar subida de imágenes

### Esta Semana
- [ ] Configurar logging en producción
- [ ] Revisar que los checks funcionan correctamente
- [ ] Documentar configuración específica de tu entorno
- [ ] Añadir check_config.sh al proceso de deploy

### Este Mes
- [ ] Implementar monitoreo (Sentry, etc.)
- [ ] Configurar backups automáticos
- [ ] Crear runbook de incidentes
- [ ] Capacitar al equipo en el uso de las herramientas

---

## 🆘 Soporte

### Si necesitas ayuda:

1. **Primero**: Ejecuta `bash check_config.sh` y revisa el output
2. **Luego**: Consulta [SOLUCION_RAPIDA.md](SOLUCION_RAPIDA.md) para tu problema específico
3. **Si persiste**: Revisa [DIAGNOSTICO_ERRORES_PRODUCCION.md](DIAGNOSTICO_ERRORES_PRODUCCION.md) para análisis profundo
4. **Logs**: Comparte el output de los comandos de diagnóstico

### Información útil para soporte:

```bash
# Recopilar información de diagnóstico
bash check_config.sh > diagnostico.txt 2>&1
python manage.py check_production_config >> diagnostico.txt 2>&1
tail -100 /var/log/nginx/error.log >> diagnostico.txt 2>&1

# Compartir diagnostico.txt
```

---

## 📞 Contacto y Contribuciones

- **Issues**: Reportar problemas en el repositorio
- **Pull Requests**: Mejoras y correcciones bienvenidas
- **Documentación**: Sugerencias para mejorar las guías

---

## 🎉 Resumen

**Problema**: Errores 500 en producción (Google OAuth y subida de imágenes)

**Solución**: 
- ✅ 11 archivos de documentación y herramientas
- ✅ Diagnóstico automático en < 5 minutos
- ✅ Soluciones paso a paso documentadas
- ✅ Logging mejorado implementado
- ✅ System checks automáticos añadidos

**Resultado esperado**: 
- Identificar problemas en < 5 minutos
- Solucionar en < 10 minutos
- Prevenir futuros problemas con monitoreo

---

**¿Listo para empezar?** → [README_ERRORES_PRODUCCION.md](README_ERRORES_PRODUCCION.md) 🚀