"""One durable five-yuan authorization across every pilot output directory."""
import os
from contextlib import contextmanager
from pathlib import Path

from app.services.organization.providers import cost, price_snapshot
from scripts.summary_quality.storage import load, save

CAP = 5_000_000
MAX_CALLS = 10


@contextmanager
def budget_lock(root):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    path = root/'budget.lock'
    with path.open('x', encoding='ascii') as stream: stream.write(str(os.getpid()))
    try: yield
    finally: path.unlink()


class Budget:
    def __init__(self, root, client, resolved):
        self.root,self.client,self.resolved = Path(root),client,resolved
        self.path = self.root/'budget.json'
        self.ledger = load(self.path) if self.path.exists() else {'schema_version':1,'cap_micros':CAP,'max_calls':MAX_CALLS,'calls':[]}
        if self.ledger['cap_micros'] != CAP or self.ledger['max_calls'] != MAX_CALLS: raise RuntimeError('pilot_budget_mismatch')
        self.prices = price_snapshot(resolved)

    @property
    def spent(self): return sum(row['accounted_micros'] for row in self.ledger['calls'])

    def cached(self, identity):
        return next((row for row in self.ledger['calls'] if row['fingerprint'] == identity), None)

    async def generate(self, identity, system, user):
        previous = self.cached(identity)
        if previous:
            if previous['status'] in {'received','succeeded','invalid'}:
                return load(self.root/previous['response'])['text'],previous
            raise RuntimeError('pilot_explicit_retry_required')
        if len(self.ledger['calls']) >= MAX_CALLS: raise RuntimeError('pilot_call_limit')
        incoming = await self.client.count_input_tokens(self.resolved,system,user)
        if type(incoming) is not int or not 0 <= incoming <= 272000: raise RuntimeError('pilot_input_capacity_exceeded')
        reserve = cost(self.prices,incoming+256,self.resolved.profile.max_output_tokens)
        if self.spent+reserve > CAP: raise RuntimeError('pilot_budget_exhausted')
        number = len(self.ledger['calls'])+1
        row = {'fingerprint':identity,'number':number,'status':'reserved','reserved_micros':reserve,
               'accounted_micros':reserve,'estimated_input_tokens':incoming,'price_snapshot':self.prices,
               'model':self.resolved.profile.model,'profile_fingerprint':self.resolved.fingerprint,
               'response':f'responses/{number:02d}.json'}
        self.ledger['calls'].append(row);save(self.path,self.ledger)
        try:
            reply = await self.client.generate(self.resolved,system,user)
        except Exception as error:
            row.update(status='uncertain',error=getattr(error,'code','model_call_failed'));save(self.path,self.ledger)
            raise RuntimeError(row['error']) from None
        # Persist the complete reply before releasing its reservation. If a write
        # is interrupted, the reserved intent prevents another paid attempt.
        save(self.root/row['response'],{'text':reply.text,'usage':reply.usage})
        row.update(status='received',usage=reply.usage)
        incoming,outgoing = reply.usage.get('input_tokens'),reply.usage.get('output_tokens')
        if type(incoming) is int and type(outgoing) is int and incoming >= 0 and outgoing >= 0:
            row['accounted_micros'] = cost(self.prices,incoming,outgoing)
        save(self.path,self.ledger)
        return reply.text,row

    def validated(self,row,valid):
        row['status'] = 'succeeded' if valid else 'invalid'
        save(self.path,self.ledger)
