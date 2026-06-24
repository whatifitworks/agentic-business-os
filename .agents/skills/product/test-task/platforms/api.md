# test-task - API sidecar (no UI)

Platform mechanics for verifying a **backend / API** change with no rendered surface. The shared spine is in
[../SKILL.md](../SKILL.md). Verification here is **test- and endpoint-based, not visual**.

## Safe always (no datastore writes)
- **Lint / syntax check** the changed files.
- **Static analysis** (types, undefined symbols, etc.).

## Endpoint / flow smoke as a test account
Authenticate as a **designated test user** and exercise the changed endpoint(s); writes are OK *only on that
test account's own data*. **Never** mutate real users/payments/data, run migrations, or truncate.

## 🛑 Integration tests - isolated datastore only, with a guardrail
The backend is often the highest-risk surface (payments, webhooks, auth) and otherwise has the weakest
automated verification, so the real test suite IS worth running - but **only against an isolated, non-prod
datastore**, never the production one. Many setups point the test config at the *same server* as production
(only suffixing the database name), so a naive test run hits prod. Gate it:

1. **Require an explicit isolated test datastore** via a dedicated env var (e.g. `TEST_DATABASE_URL`)
   pointing at a non-prod host. If it is **unset, do NOT run the suite** - fall back to lint + static
   analysis + the test-account endpoint smoke (the safe default).
2. **Guardrail before running:** parse the host from the test URL and from the production URL; if they match
   (or the test host resolves to the prod endpoint), **STOP and ask** - do not run. Proceed only when the
   test host is provably distinct from prod.
3. **Run scoped against the isolated datastore**, preferring the narrowest filter that covers the change over
   the full suite.

**Infra prerequisite (the owner owns):** standing up the isolated test datastore and exporting its URL is a
one-time setup. Until it exists, the skill stays on the safe default (no suite run) - this adds the
capability for when the datastore is there; it reverses no safety decision.
