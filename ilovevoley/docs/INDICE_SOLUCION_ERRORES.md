# 📚 Índice - Solución de Errores 500 en Producción

## 🎯 Inicio Rápido

**¿Tienes errores 500 en producción?** → Empieza aquí:

1. **[README_ERRORES_PRODUCCION.md](README_ERRORES_PRODUCCION.md)** ⭐ **EMPIEZA AQUÍ**
   - Guía visual con flujo de resolución
   - Comandos específicos para cada problema
   - Checklist de verificación

2. **[SOLUCION_RAPIDA.md](SOLUCION_RAPIDA.md)** ⚡ **5-10 minutos**
   - Pasos inmediatos para solucionar
   - Soluciones temporales y permanentes
   - Comandos copy-paste listos para usar

---

## 📖 Documentación Completa

### Para Usuarios

| Archivo | Propósito | Tiempo |
|---------|-----------|--------|
| **[README_ERRORES_PRODUCCION.md](README_ERRORES_PRODUCCION.md)** | Punto de entrada principal | 5 min |
| **[SOLUCION_RAPIDA.md](SOLUCION_RAPIDA.md)** | Guía paso a paso | 10 min |
| **check_config.sh** | Script de diagnóstico automático | 2 min |

### Para Desarrolladores

| Archivo | Propósito |
|---------|-----------|
| **[DIAGNOSTICO_ERRORES_PRODUCCION.md](DIAGNOSTICO_ERRORES_PRODUCCION.md)** | Análisis técnico completo |
| **[RESUMEN_MEJORAS.md](RESUMEN_MEJORAS.md)** | Cambios implementados en el código |
| **config/logging_production.py** | Configuración de logging |
| **env.production.example** | Ejemplo de configuración de producción |

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

**Archivo**: [SOLUCION_RAPIDA.md#para-google-oauth](SOLUCION_RAPIDA.md#para-google-oauth)

**Causa más probable**: Site.domain incorrecto

**Solución rápida**:
```bash
python manage.py shell -c "from django.contrib.sites.models import Site; s=Site.objects.get(id=1); s.domain='tu-dominio.com'; s.save()"
```

---

### Error 500: Subida de Imágenes

**Archivo**: [SOLUCION_RAPIDA.md#para-google-vision-api](SOLUCION_RAPIDA.md#para-google-vision-api)

**Causa más probable**: Credenciales de Vision API no configuradas

**Solución rápida** (deshabilitar):
```bash
# En .env:
GOOGLE_VISION_ENABLED=False
AUTO_MODERATION_ENABLED=False
```

---

## 📋 Flujo de Trabajo Recomendado

```
1. Leer README_ERRORES_PRODUCCION.md (5 min)
   ↓
2. Ejecutar: bash check_config.sh (2 min)
   ↓
3. Seguir instrucciones específicas del diagnóstico
   ↓
4. Aplicar soluciones de SOLUCION_RAPIDA.md (5-10 min)
   ↓
5. Verificar en navegador (1 min)
   ↓
6. ✅ Problema resuelto
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