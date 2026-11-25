"""One approved release connection test, isolated from stock delivery receipts."""
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RELEASE_TITLE = 'C3 approved final release 20261124 (#202)'
RESERVATION = 'release_checks/c3_telegram_connection_20261124.json'
TEST_TEXT = '[강현AI PRO · C3 TOP5]\n최종 운영 연결 시험\nTEST — 실제 매수 신호 아님'
PROTECTED = {
    'reports/c3_paper/paper_ledger.json': 'c6f7cae01241f50e21443b66957115aed4ae711409e7ee67bf8a621a66ee9270',
    'receipts/c3_top5_daily/20261119.json': '9fb797c04cb374d9e3c76607daffc5e7b1df20a94c73f5bdf3fdc9e54f972792',
    'scripts/c3_top5_session_policy.py': '5b90931ef2767af4f1be0105e4b6c4ac9735943859bcec110bcd1cad76f54fc6',
    'scripts/c3_entry_geometry.py': 'bd527819f2958faa1d59f08f79c384712a0f2bc981e34802600c5934fc066ea2',
}


def production_checks(root):
    root = Path(root)
    for name, expected in PROTECTED.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError('PROTECTED_FILE_CHANGED')
    workflow = (root / '.github/workflows/c3_top5_daily_telegram.yml').read_text()
    for required in ('default: balanced', "inputs.financial_model || 'balanced'",
                     "cron: '0 23 * * 1-5'", 'timeout-minutes: 35',
                     'group: c3-top5-daily-classic-per-stock', 'cancel-in-progress: false',
                     "on_main=os.environ.get('GITHUB_REF_NAME')=='main'",
                     "is_production=(event=='schedule' and on_main)"):
        if required not in workflow:
            raise ValueError('PRODUCTION_BOUNDARY_CHANGED')
    from c3_top5_financial_selection import APPROVAL_POLICY, INDEPENDENT_POLICY
    if APPROVAL_POLICY != 'EXECUTABLE_FINANCIAL_APPROVAL_V1':
        raise ValueError('APPROVAL_POLICY_CHANGED')
    policy=INDEPENDENT_POLICY if 'C3_APPROVAL_POLICY: '+INDEPENDENT_POLICY in workflow else APPROVAL_POLICY
    return dict(model='balanced', approval_policy=policy,legacy_approval_policy=APPROVAL_POLICY,
                protected_files_verified=list(PROTECTED), cron='0 23 * * 1-5')


def request_json(url, payload, headers, opener):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     method='PUT' if 'api.github.com/' in url else 'POST',
                                     headers={**headers, 'Content-Type': 'application/json'})
    with opener(request, timeout=30) as response:
        return response.status, json.load(response)


def check_connection(env, event, opener=urllib.request.urlopen):
    result = dict(schema='C3_RELEASE_CONNECTION_TEST_V1', status='BLOCKED',
                  purpose='CONNECTION_TEST_NOT_BUY_SIGNAL', stock_signals_sent=0,
                  test_messages_sent=0, run_id=env.get('GITHUB_RUN_ID'),
                  checked_at=datetime.now(timezone.utc).isoformat())
    if (env.get('GITHUB_EVENT_NAME') != 'push' or env.get('GITHUB_REF') != 'refs/heads/main'
            or env.get('GITHUB_REPOSITORY') != 'shdmfpsj-beep/krx-auto-scanner'
            or env.get('GITHUB_RUN_ATTEMPT') != '1'
            or event.get('head_commit', {}).get('message', '').split('\n')[0] != RELEASE_TITLE):
        return {**result, 'reason': 'APPROVED_RELEASE_CONTEXT_REQUIRED'}
    token, chat, gh_token = (env.get(k, '') for k in
                            ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'GH_TOKEN'))
    if not token or not gh_token or not chat.lstrip('-').isdigit():
        return {**result, 'reason': 'REQUIRED_SECRET_OR_NUMERIC_DESTINATION_MISSING'}
    marker = dict(purpose=result['purpose'], state='ATTEMPT_RESERVED_NO_AUTOMATIC_RETRY',
                  run_id=result['run_id'], commit=env.get('GITHUB_SHA'),
                  reserved_at=result['checked_at'], stock_signals_sent=0)
    payload = dict(message='Reserve approved C3 connection test (not a stock receipt)',
                   branch='main', content=base64.b64encode(json.dumps(marker).encode()).decode())
    result['stage'] = 'CREATE_ONLY_TEST_RESERVATION'
    try:
        status, _ = request_json('https://api.github.com/repos/' + env['GITHUB_REPOSITORY']
                                 + '/contents/' + RESERVATION, payload,
                                 {'Authorization': 'Bearer ' + gh_token,
                                  'Accept': 'application/vnd.github+json',
                                  'X-GitHub-Api-Version': '2022-11-28'}, opener)
        if status != 201:
            return {**result, 'reason': 'TEST_RESERVATION_NOT_CREATED', 'http_status': status}
        result.update(stage='TELEGRAM_SEND_ONCE', reservation=RESERVATION)
        status, answer = request_json('https://api.telegram.org/bot' + token + '/sendMessage',
                                      dict(chat_id=chat, text=TEST_TEXT,
                                           disable_notification=True), {}, opener)
        result.update(http_status=status, telegram_ok=answer.get('ok') is True)
        message = answer.get('result', {})
        message_id = message.get('message_id')
        result['destination_matches'] = str(message.get('chat', {}).get('id')) == str(int(chat))
        if status != 200 or answer.get('ok') is not True:
            raise ValueError('TELEGRAM_RESPONSE_NOT_OK')
        if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
            raise ValueError('TELEGRAM_MESSAGE_ID_MISSING')
        # Preserve confirmed send evidence even if a destination check fails.
        result.update(message_id=message_id, test_messages_sent=1,
                      sent_at=datetime.now(timezone.utc).isoformat())
        if not result['destination_matches']:
            raise ValueError('TELEGRAM_DESTINATION_MISMATCH')
        return {**result, 'status': 'SENT', 'stage': 'COMPLETE'}
    except urllib.error.HTTPError as exc:
        return {**result, 'status': 'BLOCKED' if result['stage'].startswith('CREATE') else 'ERROR',
                'reason': 'HTTP_FAILURE_NO_AUTOMATIC_RETRY', 'http_status': exc.code}
    except Exception as exc:
        # Exception text can include the bot token in a request URL. Never log it.
        return {**result, 'status': 'ERROR', 'reason': 'FAILURE_NO_AUTOMATIC_RETRY',
                'exception_type': type(exc).__name__}


def main():
    output = Path('output/c3_final_release'); output.mkdir(parents=True, exist_ok=True)
    try:
        checks = production_checks(Path.cwd())
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        result = {**check_connection(os.environ, event), 'production_checks': checks}
    except Exception as exc:
        result = dict(status='ERROR', stage='PRODUCTION_PREFLIGHT',
                      exception_type=type(exc).__name__, test_messages_sent=0)
    (output / 'telegram_connection_result.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    release = dict(schema='C3_FINAL_RELEASE_V1', main_sha=os.environ.get('GITHUB_SHA'),
                   run_id=os.environ.get('GITHUB_RUN_ID'), event=os.environ.get('GITHUB_EVENT_NAME'),
                   connection_test=result, production_model='balanced',
                   requested_market_asof='20261124',
                   market_20261124_status='PENDING_EXISTING_SCHEDULE_NOT_EXECUTED_BY_THIS_TEST',
                   next_scheduled_run_kst='2026-11-25T08:00:00+09:00',
                   next_morning_check_kst='2026-11-25T08:45:00+09:00',
                   automatic_retry=False, stock_delivery_receipts_modified=False)
    (output / 'release_status.json').write_text(json.dumps(release, ensure_ascii=False, indent=2) + '\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write('### C3 final release\n\n' + json.dumps(release, ensure_ascii=False) + '\n')
    print('C3_RELEASE_CONNECTION', json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'SENT' else 1)


if __name__ == '__main__':
    main()
