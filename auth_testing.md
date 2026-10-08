# NOVA Authentication and CSRF Test Flow

1. Read `/app/memory/test_credentials.md`; never print environment secrets, OAuth codes, or Google tokens.
2. Create a temporary MongoDB user/session and sign its session ID with the current `SESSION_SECRET`.
3. Send the signed value only as the `nova_session` cookie.
4. Set `Origin` to the exact current frontend origin.
5. Call `GET /api/auth/csrf`; retain the returned token only in test memory.
6. Send `X-CSRF-Token` on every authenticated POST, PUT, PATCH, and DELETE.
7. Negative CSRF tests must use isolated temporary sessions and must not invoke paid provider calls.
8. Delete temporary users, sessions, notes, OAuth state rows, and test messages after each run.
9. Never delete or modify the real user's encrypted Google token record.