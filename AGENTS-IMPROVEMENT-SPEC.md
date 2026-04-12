# AGENTS Improvement Spec

Audit of the MEXC Rebalancer Bot codebase against the newly created `AGENTS.md`.
Each finding is classified as **Good**, **Missing**, or **Wrong/Risk**.

---

## What's Good

| Area | Detail |
|------|--------|
| Module separation | `mexc_client`, `smart_portfolio`, `telegram_bot`, `main` have clear, non-overlapping responsibilities. |
| Auth implementation | HMAC-SHA256 signing is correct; key never logged or sent in body. |
| Sell-before-buy ordering | `execute_rebalance` sells overweight assets first to free USDT before buying, avoiding balance shortfalls. |
| Per-order error isolation | Each order is wrapped in `try/except`; one failure doesn't abort the whole rebalance. |
| Telegram whitelist | `TELEGRAM_CHAT_ID` guard prevents unauthorized access. |
| Config-driven design | All tunable parameters live in `config.json`; no magic numbers in logic. |
| Docstrings on public functions | All public functions have docstrings explaining parameters and return shape. |

---

## What's Missing

### M1 — No automated tests
**Impact:** High. Any refactor or new feature risks silent regressions in order logic or config parsing.  
**Spec:** Add `pytest` with at least:
- Unit tests for `validate_allocations` (edge cases: 1 asset, 11 assets, sum ≠ 100).
- Unit tests for `needs_rebalance_proportional` using a mock `MEXCClient`.
- Unit tests for `execute_rebalance` asserting sell-before-buy order and correct quantities (mock client).
- Unit tests for `next_run_time` for all three frequencies.

### M2 — No `.env.example` / secret documentation
**Impact:** Medium. New contributors or deployments have no reference for required env vars beyond reading source.  
**Spec:** Create `.env.example`:
```
MEXC_API_KEY=
MEXC_SECRET_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```
Reference it in `AGENTS.md` under "Environment Variables".

### M3 — No `.gitignore`
**Impact:** Medium. A `.env` file or `__pycache__/` could be accidentally committed.  
**Spec:** Create `.gitignore` with at minimum:
```
__pycache__/
*.pyc
.env
.env.*
*.log
```

### M4 — `config.json` committed with real-looking defaults
**Impact:** Medium. `config.json` is tracked in git. If a user puts real asset values or API keys in it, they may commit sensitive data.  
**Spec:** Add `config.json` to `.gitignore` and provide `config.example.json` as the tracked template. Update `load_config` to fall back to `config.example.json` with a warning if `config.json` is absent.

### M5 — No `--dry-run` flag
**Impact:** Medium. There is no way to preview what orders would be placed without executing them. This makes testing and onboarding risky.  
**Spec:** Add `--dry-run` to `main.py` and thread a `dry_run: bool` parameter through `execute_rebalance`. When `True`, log intended orders but skip `place_market_buy` / `place_market_sell` calls. Expose as `/dryrun` toggle in Telegram bot.

### M6 — No minimum order size guard
**Impact:** Medium. MEXC enforces minimum notional order sizes (typically 1–5 USDT). Orders below the minimum will be rejected by the API, logged as errors, and silently skipped, leaving the portfolio partially rebalanced.  
**Spec:** In `execute_rebalance`, skip any order where `diff_usdt < MIN_ORDER_USDT` (configurable, default `5.0`) and log a warning. Add `min_order_usdt` to `config.json` schema.

### M7 — `smart_portfolio.py` docstring says "Bitget"
**Impact:** Low. Module-level docstring still reads "Bitget Spot Auto-Rebalancing Bot" — leftover from the Bitget migration.  
**Spec:** Update the module docstring to reference MEXC.

### M8 — No `requirements.txt` version pins for security-sensitive deps
**Impact:** Low-Medium. `python-telegram-bot>=20.0` and `requests>=2.31.0` are unpinned upper bounds. A breaking upstream release could silently break the bot.  
**Spec:** Pin to exact versions after testing (e.g. `python-telegram-bot==21.x.x`, `requests==2.31.x`). Add a comment noting the last-verified versions.

---

## What's Wrong / Risk

### W1 — `hmac.new` should be `hmac.new` → actually `hmac.new` is correct, but `_sign` ignores param ordering
**File:** `mexc_client.py`, `_sign`  
**Detail:** `urlencode(params)` on a plain `dict` does not guarantee insertion order in all Python versions before 3.7. While CPython 3.7+ preserves insertion order, `_signed_params` adds `timestamp` and `signature` via dict mutation, which means `signature` is computed over a dict that already contains `timestamp` but the order of other keys depends on call-site construction. This is currently safe but fragile.  
**Spec:** Use `sorted(params.items())` or an `OrderedDict` in `_sign` to make signing order explicit and deterministic.

### W2 — `_sign` computes signature over params that include `signature` key if called twice
**File:** `mexc_client.py`, `_signed_params`  
**Detail:** `_signed_params` mutates the passed-in dict by adding `timestamp` and `signature`. If the same dict is reused across retries, the second call will sign a dict that already contains a stale `signature` key, producing an invalid signature.  
**Spec:** Always work on a copy: `p = dict(params or {})` (already done) — but also ensure `signature` is not present in `p` before signing. Add an assertion or `p.pop("signature", None)` before `_sign`.

### W3 — `execute_rebalance` uses stale price for sell quantity
**File:** `smart_portfolio.py`, `execute_rebalance`  
**Detail:** `base_qty = s["diff_usdt"] / s["price"]` uses the price fetched at the start of `get_portfolio_value`. By the time the sell order is placed (especially after prior sells), the price may have moved. For volatile assets this can result in over- or under-selling.  
**Spec:** Re-fetch price immediately before computing `base_qty`, or use `quoteOrderQty` for sells as well (if MEXC supports it), so the exchange handles the quantity conversion at execution time.

### W4 — `run` loop in `telegram_bot.py` uses `datetime.utcnow()` (deprecated in Python 3.12)
**File:** `smart_portfolio.py`, `next_run_time` and `run`; `telegram_bot.py`, `_run_loop`  
**Detail:** `datetime.utcnow()` is deprecated since Python 3.12 and will be removed in a future version. It also returns a naive datetime, making timezone handling error-prone.  
**Spec:** Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)` and update comparisons accordingly.

### W5 — Background thread in `telegram_bot.py` has no exception propagation
**File:** `telegram_bot.py`, `_run_loop`  
**Detail:** The rebalancer loop runs in a `threading.Thread`. If an unhandled exception occurs inside the thread (e.g. network failure not caught by per-order try/except), the thread dies silently. The Telegram bot continues responding but the rebalancer is no longer running.  
**Spec:** Wrap the entire `_run_loop` body in a `try/except Exception` that sets a flag and sends a Telegram message to the owner notifying them the loop has crashed.

### W6 — `TELEGRAM_CHAT_ID` whitelist only checks `effective_chat.id`, not `effective_user.id`
**File:** `telegram_bot.py`, `_allowed`  
**Detail:** `effective_chat.id` is the chat ID, which for group chats differs from the user ID. If the bot is added to a group, any group member can issue commands. The intent is to whitelist a specific user.  
**Spec:** Check `update.effective_user.id` instead of (or in addition to) `update.effective_chat.id`.

---

## Concrete Implementation Order

Priority order based on impact and effort:

1. **W5** — Silent thread crash (high risk, low effort: add one try/except + notify call)
2. **W6** — Chat ID whitelist bypass (security, low effort)
3. **M3 + M4** — `.gitignore` + untrack `config.json` (prevents accidental secret commit)
4. **M2** — `.env.example` (onboarding, trivial)
5. **M6** — Minimum order size guard (prevents silent partial rebalances)
6. **W4** — `datetime.utcnow()` deprecation (correctness, low effort)
7. **W3** — Stale price in sell quantity (trading accuracy)
8. **W2** — Signature mutation safety (correctness, low effort)
9. **M5** — `--dry-run` flag (usability, medium effort)
10. **M7** — Stale "Bitget" docstring (trivial)
11. **M1** — Automated tests (high value, highest effort — do last once logic is stable)
12. **M8** — Pin dependency versions (maintenance)
13. **W1** — Deterministic param ordering in `_sign` (defensive, low effort)
