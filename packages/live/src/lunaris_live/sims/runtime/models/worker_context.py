from dataclasses import dataclass

from lunaris_runtime.credentials import CredentialResolver
from lunaris_runtime.persistence import ICostEventStore, ISubjectCostStore

from ....session import ISessionStore


@dataclass(frozen=True)
class SimWorkerContext:
    sessions: ISessionStore
    credential_resolver: CredentialResolver | None = None
    cost_events: ICostEventStore | None = None
    subject_costs: ISubjectCostStore | None = None
    session_budget_s: float = 1800
    session_budget_usd: float = 0
