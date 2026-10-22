# Codebase Concerns

**Analysis Date:** 2026-10-22

## Tech Debt

**Legacy `videos` package still holds real logic:**
- Issue: `ilovevoley/videos/` is documented as a compatibility layer (URLs, Celery periodic tasks), but still contains the largest module in the repo and core services: `ilovevoley/videos/scraping/federation.py` (1953 lines), `ilovevoley/videos/tasks/scraping.py` (1169), `ilovevoley/videos/scraping/parsers.py` (693), `ilovevoley/videos/utils.py` (678), `ilovevoley/videos/rfevb_service.py`, `ilovevoley/videos/calendar_feed.py`. The `models/` and `views/` subpackages are thin re-export shims (3-67 lines each).
- Files: `ilovevoley/videos/`
- Impact: Contradicts the "new code goes to its domain app" rule. Scraping logic lives apart from `ilovevoley/competitions`, which owns the models it writes.
- Fix approach: Move scraping/parsers/services into `ilovevoley/competitions/` incrementally, keeping Celery task `name=` values unchanged (`PeriodicTask` rows depend on them).

**Oversized view and model modules:**
- Files: `ilovevoley/competitions/views.py` (1841), `ilovevoley/content/views.py` (1822), `ilovevoley/rosters/views.py` (1123), `ilovevoley/core/views.py` (1113), `ilovevoley/competitions/models/competitions.py` (1154), `ilovevoley/competitions/result_card.py` (860), `ilovevoley/competitions/admin/competitions.py` (852)
- Impact: Hard to review and a merge-conflict hotspot.
- Fix approach: Split into packages by feature (as `competitions/models/` and `competitions/admin/` already do) when touching them; do not grow them.

**Unimplemented Live Photo frame extraction:**
- Issue: `ilovevoley/videos/utils.py` (~line 391) writes the whole video to a temp file, then returns `None` with `# TODO: Implementar con opencv-python o moviepy`. The function is effectively a stub that does I/O for nothing.
- Impact: Live Photos never get a frame; wasted disk and memory (`video_file.read()` loads the whole file).
- Fix approach: Implement with ffmpeg or remove the temp-file step and return `None` early.

**Stray `print()` in production code:**
- Files: `ilovevoley/core/email_utils.py` (lines ~152, 204, 207), `ilovevoley/videos/utils.py` (~line 400), and others (29 occurrences outside tests/management/migrations).
- Impact: Violates the pre-commit rule (no `print(`); errors go to stdout and are not captured by Sentry or the logging config (`config/logging_production.py`, `config/sentry.py`). Email failures are swallowed with only a print.
- Fix approach: Use `logger.warning` / `logger.error` for failures; remove success prints.

**Broad exception handling:**
- Files: 143 `except Exception` occurrences in non-test code, concentrated in scraping and tasks (`ilovevoley/videos/scraping/federation.py`, `ilovevoley/videos/tasks/`).
- Impact: Parser regressions against the federation site can fail silently.
- Fix approach: Catch specific exceptions (`requests.RequestException`, `ValueError`), and call `logger.exception` / re-raise in tasks so Celery and Sentry see them.

**One-off script in repo root:**
- Files: `check_duplicates.py`
- Issue: Ad-hoc script with hardcoded club names (SANT JOSEP, LUCI'S) and `print` output, outside any package or management command.
- Fix approach: Delete it, or turn it into a management command if it is still needed.

**Dependency pin:**
- Django pinned to 6.0.8 until `django-celery-beat` supports 6.1+ (`pyproject.toml`). Security patches beyond 6.0.x are blocked until then.

## Known Bugs

**Not detected as tracked bugs.** The only code TODO is the Live Photo stub above. `XXXX` matches in `ilovevoley/videos/scraping/rfevb.py` are URL placeholders in docstrings.

## Security Considerations

**`csrf_exempt` on PWA share target:**
- Risk: `image_share_target` in `ilovevoley/content/views.py` (~line 675) accepts a cross-origin multipart POST without a CSRF token and creates `SharedUpload` rows.
- Current mitigation: Requires authenticated session plus an approved tenant membership (or superuser); type and size checks (`SHARE_TARGET_ACCEPTED_TYPES`, `SHARE_TARGET_MAX_BYTES`, `SHARE_TARGET_MAX_FILES`); rows expire after 24 h; no side effects until consumed.
- Recommendations: Keep the gate intact. Content type comes from the client header, so validate image content server-side (e.g. Pillow open) before consuming. Do not add other `csrf_exempt` views.

**`mark_safe` usage:**
- Files: `ilovevoley/core/templatetags/icons.py` (static SVG dict, `nosec` annotated), `ilovevoley/users/admin.py` (static HTML strings).
- Risk: Low today since all inputs are constants. Anything interpolating user data into these must use `format_html`.

**Outbound fetches of external URLs:**
- Files: `ilovevoley/competitions/services/acta_photo.py` (~line 201), `ilovevoley/videos/rfevb_service.py`, `ilovevoley/videos/scraping/federation.py`, `ilovevoley/videos/tasks/enrichment.py`.
- Current mitigation: `ACTA_ALLOWED_HOSTS` allow-list in `config/settings.py`; `timeout=` set on all inspected `requests.get` calls.
- Recommendations: Keep the allow-list check on every new fetch of DB-stored or user-supplied URLs (SSRF).

**Production hardening present:** `SECURE_SSL_REDIRECT`, HSTS, secure session cookies, and CSP (`SECURE_CSP`) are configured in `config/settings.py`; `SECURE_CSP_REPORT_ONLY = None` means CSP is enforced. Env files are not committed.

## Performance Bottlenecks

**N+1 queries recur in portal views:**
- Evidence: recent fixes #586 (profile team filter) and #588 (`public_matches` club fetch) were both query-count regressions.
- Files: `ilovevoley/competitions/views.py`, `ilovevoley/users/views.py`, `ilovevoley/rosters/views.py`
- Improvement path: Use `select_related`/`prefetch_related` in list views; add `assertNumQueries`-style tests only on hot pages that already regressed.

**Sequential scraping with sleeps:**
- Files: `ilovevoley/videos/scraping/federation.py` (`time.sleep` at ~80, 156, 1337), `ilovevoley/videos/tasks/enrichment.py` (~95), `ilovevoley/videos/rfevb_service.py` (~99)
- Cause: Rate-limit and retry back-off inside Celery tasks occupy workers for long periods.
- Improvement path: Use `self.retry(countdown=...)` and fan out per-endpoint tasks.

**In-process LLM throttle:**
- Files: `ilovevoley/core/narrative.py` (`_throttle`, module-global `_last_call`)
- Cause: Counter is per process, so concurrent workers can exceed the Gemini free-tier limit (15/min); the docstring acknowledges it.
- Improvement path: Share the limiter through Redis/cache, or keep narrative batches on a single-concurrency queue.

**Live Photo temp file read fully into memory:** `ilovevoley/videos/utils.py` (see Tech Debt).

## Fragile Areas

**Federation scraping and parsers:**
- Files: `ilovevoley/videos/scraping/federation.py`, `ilovevoley/videos/scraping/parsers.py`, `ilovevoley/videos/scraping/rfevb.py`, `ilovevoley/videos/rfevb_service.py`
- Why fragile: Depends on third-party HTML/JSON formats (voleibolib, RFEVB) with no contract; acta URLs appear in both full and `acta_XXXX.html` forms (handled in `ilovevoley/videos/tests/test_scraping.py`).
- Safe modification: Add a fixture-based test for each new format quirk; always run `ilovevoley/videos/tests/test_scraping.py` and `test_acta.py`.

**Celery task names and PeriodicTask rows:**
- Files: `config/celery_schedule.py`, `ilovevoley/videos/tasks/`
- Why fragile: Names are stored in the DB. Renaming or moving a task without `name=` silently breaks schedules.
- Safe modification: Never remove or change `name=`; check DB `PeriodicTask` rows before deleting a task.

**Match managers:**
- Files: `ilovevoley/competitions/models/competitions.py`
- Why fragile: `Match.objects` hides `withdrawn` matches; code expecting all matches (merges, duplicate checks) must use `Match.all_objects`. Easy to miss in new queries.

**Multi-tenant resolution:**
- Files: `ilovevoley/core/middleware.py` (`TenantMiddleware`)
- Why fragile: Tenant is derived from the last two host labels; local dev requires `lvh.me`. New querysets must be tenant-scoped (`Person.objects.for_tenant`, `PersonRoleTenantQuerySet`) or data leaks between clubs.

**Person identity and linking:**
- Files: `ilovevoley/rosters/models/rosters.py`, `ilovevoley/rosters/views.py`, `ilovevoley/users/onboarding.py`
- Why fragile: Global `Person` with unique (`first_name`, `last_name`, `birth_year`), provisional records (#569), and moderator-approved linking (#531). Only approval may write `Person.user` / `User.children`.

**Deploy sequence is manual-sensitive:**
- Files: `deploy.sh`, `entrypoint.sh`
- Why fragile: `entrypoint.sh` no longer runs migrations or `collectstatic`; skipping steps in a manual deploy gives 404 static files or missing Catalan translations (`.mo` is gitignored). `docker-compose.dev.yml` must never run on the production host (shares the project name and DB/Redis containers).

## Scaling Limits

**Not measured.** Single compose host (`docker-compose.yml`, `nginx.conf`); no horizontal scaling configuration detected. The per-process LLM throttle (above) is the one known scale-out limit.

## Dependencies at Risk

**`django-celery-beat`:** gates the Django upgrade (see Tech Debt).
**Gemini free tier:** `ilovevoley/core/narrative.py` relies on a rate-limited provider for `SeasonWrapped` narratives.
**Google Vision API:** moderation/auto-tagging in `ilovevoley/content/` depends on an external paid service.
**Lockfile policy:** `uv.lock` is committed; `pyproject.toml` changes without relock fail the build by design.

## Missing Critical Features

**Live Photo thumbnails:** not implemented (see Tech Debt).
**Cross-worker rate limiting for LLM calls:** not implemented.

## Test Coverage Gaps

**Large view modules:** `ilovevoley/competitions/views.py`, `ilovevoley/content/views.py`, `ilovevoley/core/views.py` are big, and the project policy (`docs/ai-guidelines/testing-guidelines.md`) deliberately avoids status-code-only tests. Branches with business rules there can go untested.
- Priority: Medium
**Email utility failure paths:** `ilovevoley/core/email_utils.py` swallows exceptions and prints; no log-based verification.
- Priority: Low
**Share target content validation:** `image_share_target` trusts the client content type.
- Priority: Medium

---

*Concerns audit: 2026-10-22*
