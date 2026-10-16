"""Fail-closed, create-only GitHub reservations. Never releases or takes over a claim."""
import json
import re
import urllib.error
import urllib.request

from deepseek_post_guard import GuardStop


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class GitHubAPI:
    def __init__(self, repository, token):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or not token:
            raise GuardStop('remote_claim_credentials_or_repository_missing')
        self.base = 'https://api.github.com/repos/' + repository + '/'
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def __call__(self, method, path, value=None):
        if (method, path) not in {('POST', 'tags'), ('POST', 'refs')} and not (
            method == 'GET' and re.fullmatch(r'(?:ref/tags/[a-z0-9/-]+|tags/[a-f0-9]{40}|rulesets(?:/[0-9]+)?)', path)
        ):
            raise GuardStop('remote_claim_operation_forbidden')
        request = urllib.request.Request(
            self.base + (path if path.startswith('rulesets') else 'git/' + path), method=method,
            data=None if value is None else json.dumps(value).encode(),
            headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/json', 'User-Agent': 'DSA-MVP-execution-claim'},
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                status = response.status
                raw = response.read()
            if status != (201 if method == 'POST' else 200):
                raise GuardStop('remote_claim_unexpected_status')
            return json.loads(raw)
        except urllib.error.HTTPError as error:
            # Do not log credentials, response bodies, or retry ambiguous writes.
            raise GuardStop('remote_claim_HTTP_' + str(error.code) + '_no_retry') from None
        except Exception:
            raise GuardStop('remote_claim_result_unknown_no_retry') from None


class RemoteExecutionClaim:
    def __init__(self, api, batch_sha, run_id, commit, *, namespace='dsa-mvp-consumed-v1'):
        if not re.fullmatch('[a-f0-9]{64}', batch_sha) or not re.fullmatch('[a-f0-9]{40}', commit):
            raise GuardStop('remote_claim_identity_invalid')
        if not re.fullmatch(r'[0-9]+', str(run_id)) or namespace not in (
            'dsa-mvp-consumed-v1', 'dsa-mvp-claim-test-v1'
        ):
            raise GuardStop('remote_claim_run_or_namespace_invalid')
        self.api, self.batch, self.run, self.commit = api, batch_sha, str(run_id), commit
        self.namespace = namespace
        self.records = {}
        self.sent = set()
        self.ready = False

    def _protection(self):
        rules = self.api('GET', 'rulesets')
        ids = [r['id'] for r in rules if r.get('name') == 'dsa-mvp-execution-claims']
        if len(ids) != 1:
            raise GuardStop('remote_claim_protection_unknown')
        rule = self.api('GET', 'rulesets/' + str(ids[0]))
        condition = rule.get('conditions', {}).get('ref_name', {})
        if (rule.get('enforcement') != 'active' or rule.get('target') != 'tag'
                # GitHub hides bypass_actors from non-admin installation tokens.
                # Require the server's explicit decision for THIS token, never infer it.
                or rule.get('current_user_can_bypass') != 'never'
                or rule.get('bypass_actors', []) != [] or condition.get('exclude') != []
                or not {'refs/tags/' + self.namespace + '/' + kind + '/*' for kind in ('batch', 'request')}.issubset(set(condition.get('include', [])))
                or not {'update', 'deletion'}.issubset({r['type'] for r in rule.get('rules', [])})):
            raise GuardStop('remote_claim_update_delete_protection_missing')

    def _create(self, kind, digest, symbol=None):
        if not re.fullmatch('[a-f0-9]{64}', digest):
            raise GuardStop('remote_claim_digest_invalid')
        ref = 'tags/' + self.namespace + '/' + kind + '/' + digest
        message = {'version': 1, 'state': 'reserved_may_be_consumed_no_reuse',
                   'batch_sha256': self.batch, 'run_id': self.run, 'run_attempt': 1,
                   'workflow_commit': self.commit, 'kind': kind, 'digest': digest, 'symbol': symbol}
        text = json.dumps(message, sort_keys=True, separators=(',', ':'))
        tag = self.api('POST', 'tags', {'tag': ref[5:], 'message': text,
                                      'object': self.commit, 'type': 'commit'})
        tag_sha = tag.get('sha', '')
        if not re.fullmatch('[a-f0-9]{40}', tag_sha):
            raise GuardStop('remote_claim_tag_response_invalid')
        # Atomic create, NOT check-then-update. Existing/inflight/unknown all refuse reuse.
        created = self.api('POST', 'refs', {'ref': 'refs/' + ref, 'sha': tag_sha})
        if created.get('ref') != 'refs/' + ref or created.get('object', {}).get('sha') != tag_sha:
            raise GuardStop('remote_claim_creation_not_proven')
        self.records[digest] = {'ref': ref, 'tag_sha': tag_sha, 'message': message}

    def reserve(self, members):
        if self.records or [m.get('symbol') for m in members] != ['NVDA', 'MU', 'QQQ']:
            raise GuardStop('remote_claim_batch_members_or_repeat_invalid')
        hashes = [m['request_sha256'] for m in members]
        if len(set(hashes)) != 3 or self.batch in hashes:
            raise GuardStop('remote_claim_duplicate_request_hash')
        self._protection()
        self._create('batch', self.batch)
        for member in members:
            self._create('request', member['request_sha256'], member['symbol'])
        # Partial reservation failures permanently block this batch. Never roll back.
        self.ready = True
        return self.records

    def _verify(self, digest):
        record = self.records.get(digest)
        if record is None:
            raise GuardStop('remote_claim_not_reserved')
        ref = self.api('GET', 'ref/' + record['ref'])
        if (ref.get('ref') != 'refs/' + record['ref']
                or ref.get('object', {}).get('sha') != record['tag_sha']
                or ref.get('object', {}).get('type') != 'tag'):
            raise GuardStop('remote_claim_owner_changed_or_unknown')
        tag = self.api('GET', 'tags/' + record['tag_sha'])
        try:
            message = json.loads(tag['message'])
        except (KeyError, ValueError, TypeError):
            raise GuardStop('remote_claim_metadata_unknown') from None
        if (message != record['message'] or tag.get('sha') != record['tag_sha']
                or tag.get('object', {}).get('sha') != self.commit
                or tag.get('object', {}).get('type') != 'commit'):
            raise GuardStop('remote_claim_ownership_mismatch')

    def before_send(self, symbol, request_sha):
        if not self.ready or symbol in self.sent or len(self.sent) >= 3:
            raise GuardStop('remote_claim_local_request_reuse')
        self._protection()
        self._verify(self.batch)
        self._verify(request_sha)
        if self.records[request_sha]['message']['symbol'] != symbol:
            raise GuardStop('remote_claim_symbol_mismatch')
        self.sent.add(symbol)  # Also burned if the following model transport fails.
