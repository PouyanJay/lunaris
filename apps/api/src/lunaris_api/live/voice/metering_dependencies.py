from dataclasses import dataclass

from lunaris_runtime.credentials import CredentialResolver
from lunaris_runtime.persistence import ICostEventStore, ISubjectCostStore


@dataclass(frozen=True)
class VoiceMeteringDependencies:
    credential_resolver: CredentialResolver | None = None
    cost_event_store: ICostEventStore | None = None
    subject_cost_store: ISubjectCostStore | None = None
