# Evaluación de proveedores de login social (#255)

Fecha: 2026-10-02. Estado actual: solo Google (`allauth==65.19.4`).

## Resumen y decisión propuesta

| Proveedor | Viabilidad técnica | Trámite en el tercero | Decisión |
|---|---|---|---|
| Facebook | Sí, provider nativo | Alto (app Meta + revisión + política de privacidad) | Aplazar; implementar solo si hay demanda real |
| Instagram | **No** | — | **Descartar** |
| X / Twitter | Sí (`twitter_oauth2`) | Cuenta developer de pago por uso | **Descartar** |
| Apple | Sí | Apple Developer Program (de pago) | Implementar **solo si** se publica app iOS |
| Microsoft | Sí | Bajo (Entra ID, gratis) | No aporta al público objetivo |
| Discord | Sí | Bajo (gratis) | No aporta al público objetivo |

Recomendación: no añadir proveedores ahora. Google cubre el caso de uso. Revisar Apple
cuando se decida la publicación en App Store (ver
`2026-09-30-mobile-packaging-pwa-capacitor-twa.md`).

## Qué dice allauth

- Tiene provider para todos los candidatos (`facebook`, `instagram`, `twitter_oauth2`,
  `apple`, `microsoft`, `discord`). Cada uno exige una `SocialApp` (admin o
  `SOCIALACCOUNT_PROVIDERS['x']['APPS']`) asociada al `Site`, y el callback
  `https://<dominio>/accounts/<provider>/login/callback/`.
- Facebook: `email` y `public_profile` no requieren revisión; cualquier otro permiso sí.
  allauth trata el email de Facebook como **no verificado** por defecto
  (`VERIFIED_EMAIL: True` lo cambia, con riesgo de seguridad).
- Apple: requiere membresía del Apple Developer Program, App ID, Service ID y clave
  privada (`client_id`, `secret` = Key ID, `key` = Team ID).
- X OAuth2: se registra la app en el portal de developers; la doc de allauth no cubre
  scopes de email ni precios.

## Por proveedor

### Facebook
- Trámites: crear app en Meta for Developers, configurar dominios y callback,
  política de privacidad pública y pasar a modo "Live" (revisión de Meta). Con solo
  `email` + `public_profile` el acceso estándar es automático, pero pueden pedir
  verificación de negocio.
- Riesgo: el email puede no concederse o llegar sin verificar; con el adapter actual no
  se vincularía a cuentas locales existentes (comportamiento correcto), pero un usuario
  que ya entra con Google crearía una cuenta duplicada.
- Estimación: 0,5 d de código + 1-2 semanas de calendario de trámite.

### Instagram
- Meta cerró la Basic Display API el 4-dic-2024. La sustituta (Instagram API with
  Instagram Login) no soporta cuentas personales y no devuelve email. El provider de
  allauth no es utilizable para login de usuarios finales.
- Estimación: no aplica.

### X / Twitter
- Desde feb-2026 el plan gratuito está descontinuado; el acceso es de pago por uso
  (salvo apps "Public Utility"). No está confirmado que el login OAuth2 entregue email,
  que este proyecto exige (`SOCIALACCOUNT_EMAIL_REQUIRED = True`).
- Estimación: no aplica.

### Apple
- Trámites: Apple Developer Program (99 USD/año), App ID, Service ID, clave `.p8`,
  dominio verificado.
- Riesgo: el email puede ser un relay privado (`@privaterelay.appleid.com`) que no
  coincide con ninguna cuenta local: cuentas duplicadas y emails de la app que no
  llegan si no se registra el dominio de envío en Apple.
- Estimación: 1 d de código + 0,5 d de trámite (si ya hay cuenta de developer).

### Microsoft / Discord
- Sin revisión. Entra ID (Microsoft) y el portal de Discord son gratuitos. Sin demanda
  identificada entre clubes y familias de voleibol.
- Estimación: 0,5 d cada uno.

## Trabajo común a cualquier proveedor nuevo (0,5-1 d)

1. Botones hardcodeados con `google_login` en `account/login.html:78` y
   `account/signup.html:107`: pasar a bucle con `{% provider_login_url %}`.
2. `CustomSocialAccountAdapter.populate_user` solo contempla `google`.
3. `check_socialauth_config` (`ilovevoley/core/checks.py`) y
   `check_production_config` solo validan `SocialApp` de Google.
4. `SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'` y `EMAIL_AUTHENTICATION_AUTO_CONNECT`
   confían en el email del proveedor: cualquier provider nuevo debe marcar el email
   como verificado **solo** si el tercero lo garantiza (Google sí; Facebook y Apple no
   de forma fiable). Es la protección contra el pre-secuestro que ya implementa el
   adapter.
5. `signup.html` de socialaccount pide `parent_info`: confirmar que el flujo con email
   ausente o relay no lo rompe.

## Pendiente de contrastar antes de cerrar

- Precio y scopes exactos de X para login (no verificado en fuente oficial).
- Si Meta exige verificación de negocio para Facebook Login con solo `email` y
  `public_profile` en una app de un club.
- Si la guía 4.8 de App Store obliga a ofrecer Sign in with Apple junto a Google en la
  app iOS.

## Fuentes

- [Proveedores de django-allauth](https://docs.allauth.org/en/latest/socialaccount/providers/index.html)
- [allauth: Facebook](https://docs.allauth.org/en/latest/socialaccount/providers/facebook.html)
- [allauth: Apple](https://docs.allauth.org/en/latest/socialaccount/providers/apple.html)
- [allauth: X OAuth 2](https://docs.allauth.org/en/latest/socialaccount/providers/twitter_oauth2.html)
- [Cierre de la Instagram Basic Display API](https://dev.to/nick_johnson/instagram-basic-display-api-is-dead-build-what-works-instead-4ifm)
- [Precios de la API de X 2026](https://postproxy.dev/blog/x-api-pricing-2026/)
