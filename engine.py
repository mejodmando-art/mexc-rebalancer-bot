"""
Portfolio loop engine — manages per-portfolio rebalance threads.

Extracted from api/main.py so it can be used by both the Telegram-only
entry point (main.py) and any future API layer.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Optional

log = logging.getLogger("engine")

# pid -> {"thread": Thread, "stop": Event, "error": str|None, "started_at": str|None}
_portfolio_loops: dict[int, dict] = {}
_loops_lock = threading.Lock()


# ── Telegram notification (fire-and-forget) ────────────────────────────────────

def notify_telegram(message: str) -> None:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    try:
        import requests as _req
        _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=5,
        )
    except Exception as e:
        log.warning("Telegram notification failed: %s", e)


# ── Loop worker ────────────────────────────────────────────────────────────────

def _make_loop(portfolio_id: int, stop_event: threading.Event) -> None:
    from smart_portfolio import (
        execute_rebalance, needs_rebalance_proportional,
        next_run_time, get_portfolio_value, check_sl_tp,
        TIMED_FREQUENCY_MINUTES,
    )
    from database import get_portfolio as db_get_portfolio
    from mexc_client import MEXCClient

    with _loops_lock:
        if portfolio_id in _portfolio_loops:
            _portfolio_loops[portfolio_id]["error"] = None
            _portfolio_loops[portfolio_id]["started_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    try:
        cfg = db_get_portfolio(portfolio_id)
        if cfg is None:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        client = MEXCClient()
        mode = cfg["rebalance"]["mode"]
        log.info("Portfolio %d loop started | mode: %s", portfolio_id, mode)
        timed_next_run = None

        while not stop_event.is_set():
            try:
                cfg = db_get_portfolio(portfolio_id)
                if cfg is None:
                    break
                current_mode = cfg["rebalance"]["mode"]

                sl_tp_triggered = check_sl_tp(client, cfg)
                sl_tp_symbols = {t["symbol"] for t in sl_tp_triggered}
                if sl_tp_symbols:
                    for t in sl_tp_triggered:
                        msg = (
                            f"⚠️ *{t['action']}* — `{t['symbol']}`\n"
                            f"دخول: `{t['entry_price']:.4f}` | حالي: `{t['current_price']:.4f}`\n"
                            f"تغيير: `{t['change_pct']:+.2f}%`"
                        )
                        notify_telegram(msg)

                if current_mode == "proportional":
                    interval = cfg["rebalance"]["proportional"]["check_interval_minutes"] * 60
                    buy_enabled = cfg.get("buy_enabled", False)
                    if needs_rebalance_proportional(client, cfg, exclude_symbols=sl_tp_symbols):
                        result = execute_rebalance(
                            client, cfg,
                            exclude_symbols=sl_tp_symbols,
                            portfolio_id=portfolio_id,
                            buy_enabled=buy_enabled,
                        )
                        trades = [r for r in result if r.get("action") in ("BUY", "SELL")]
                        if trades:
                            summary = "\n".join(
                                f"{'🟢' if r['action']=='BUY' else '🔴'} `{r['symbol']}` {r['diff_usdt']:+.2f}$"
                                for r in trades
                            )
                            notify_telegram(f"🔄 *إعادة توازن تلقائية*\n\n{summary}")
                    stop_event.wait(interval)

                elif current_mode == "timed":
                    timed_cfg = cfg["rebalance"]["timed"]
                    frequency = timed_cfg["frequency"]
                    target_hour = timed_cfg.get("hour", 0)
                    buy_enabled = cfg.get("buy_enabled", False)
                    if timed_next_run is None:
                        timed_next_run = next_run_time(frequency, target_hour=target_hour)
                    if datetime.utcnow() >= timed_next_run:
                        result = execute_rebalance(
                            client, cfg,
                            exclude_symbols=sl_tp_symbols,
                            portfolio_id=portfolio_id,
                            buy_enabled=buy_enabled,
                        )
                        trades = [r for r in result if r.get("action") in ("BUY", "SELL")]
                        if trades:
                            summary = "\n".join(
                                f"{'🟢' if r['action']=='BUY' else '🔴'} `{r['symbol']}` {r['diff_usdt']:+.2f}$"
                                for r in trades
                            )
                            notify_telegram(f"🔄 *إعادة توازن ({frequency})*\n\n{summary}")
                        timed_next_run = next_run_time(frequency, target_hour=target_hour)
                    short_freq = (
                        frequency in TIMED_FREQUENCY_MINUTES
                        and frequency not in ("daily", "weekly", "monthly")
                    )
                    stop_event.wait(30 if short_freq else 60)

                else:
                    timed_next_run = None
                    stop_event.wait(60)

            except Exception as e:
                log.error("Portfolio %d loop error: %s", portfolio_id, e)
                stop_event.wait(30)

    except Exception as e:
        with _loops_lock:
            if portfolio_id in _portfolio_loops:
                _portfolio_loops[portfolio_id]["error"] = str(e)
        log.error("Portfolio %d loop crashed: %s", portfolio_id, e)

    log.info("Portfolio %d loop stopped", portfolio_id)


# ── Public API ─────────────────────────────────────────────────────────────────

def is_portfolio_running(portfolio_id: int) -> bool:
    with _loops_lock:
        entry = _portfolio_loops.get(portfolio_id)
    return entry is not None and entry["thread"].is_alive()


def start_portfolio_loop(portfolio_id: int) -> None:
    from database import set_bot_running
    with _loops_lock:
        existing = _portfolio_loops.get(portfolio_id)
        if existing is not None and existing["thread"].is_alive():
            return
        stop_ev = threading.Event()
        t = threading.Thread(
            target=_make_loop, args=(portfolio_id, stop_ev),
            daemon=True, name=f"portfolio-{portfolio_id}",
        )
        _portfolio_loops[portfolio_id] = {
            "thread": t, "stop": stop_ev,
            "error": None, "started_at": None,
        }
    t.start()
    set_bot_running(portfolio_id, True)
    log.info("Portfolio %d loop started", portfolio_id)


def stop_portfolio_loop(portfolio_id: int) -> None:
    from database import set_bot_running
    with _loops_lock:
        entry = _portfolio_loops.get(portfolio_id)
    if entry:
        entry["stop"].set()
        entry["thread"].join(timeout=5)
        with _loops_lock:
            if portfolio_id in _portfolio_loops and not _portfolio_loops[portfolio_id]["thread"].is_alive():
                del _portfolio_loops[portfolio_id]
    set_bot_running(portfolio_id, False)
    log.info("Portfolio %d loop stopped", portfolio_id)


def get_loop_info(portfolio_id: int) -> Optional[dict]:
    with _loops_lock:
        entry = _portfolio_loops.get(portfolio_id)
    if entry is None:
        return None
    return {
        "running": entry["thread"].is_alive(),
        "error": entry.get("error"),
        "started_at": entry.get("started_at"),
    }
