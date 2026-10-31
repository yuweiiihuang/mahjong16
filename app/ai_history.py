"""Public, per-seat controller summaries without actions or player identifiers."""


def public_ai_failure(reason: str | None) -> str | None:
    """Expose a user-facing category, never native diagnostic details."""
    if not reason:
        return None
    return {'unavailable': 'unavailable', 'capacity': 'busy',
            'TimeoutError': 'timeout'}.get(reason, 'error')


def seat_ai_history(hand: dict) -> list[dict]:
    """Summarize actual accepted decisions; never infer old strategies from preferences."""
    summaries = []
    for pid in range(4):
        configured = (hand['ai_levels'] or [None] * 4)[pid]
        segments = []
        for decision in hand['decisions'] or []:
            if decision.get('pid') != pid or decision['seq'] > hand['step_count']:
                continue
            source = decision.get('source', 'unknown')
            controller = source if source in ('human', 'bot') else 'auto'
            level = ({'greedy': 'standard', 'meowcats_2000': 'advanced'}
                     .get(decision.get('strategy'), 'unknown') if controller == 'bot' else None)
            if segments and (segments[-1]['controller'], segments[-1]['level']) == (
                    controller, level):
                segments[-1]['end'] = decision['seq']
            else:
                segments.append({'start': decision['seq'], 'end': decision['seq'],
                                 'controller': controller, 'level': level})
        failures = [failure for failure in hand['ai_failures'] or []
                    if failure['pid'] == pid and failure['after_seq'] <= hand['step_count']]
        bots = [segment for segment in segments if segment['controller'] == 'bot']
        known = configured is not None or bool(segments)
        used = bool(bots or failures) if known else None
        summaries.append({
            'used': used, 'configured': configured,
            'level': bots[-1]['level'] if bots else 'standard' if failures else 'unknown',
            'degraded': bool(failures),
            'fallback_after': failures[0]['after_seq']
                if failures and hand.get('status') == 'completed' else None,
            'fallback_reason': public_ai_failure(failures[0]['reason']) if failures else None,
            'mixed': bool(bots) and any(s['controller'] != 'bot' for s in segments),
            'segments': segments if hand.get('status') == 'completed' else [],
        })
    return summaries
