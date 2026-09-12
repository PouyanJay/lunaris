from dataclasses import dataclass


@dataclass(frozen=True)
class SimVersions:
    factory: str = "sim-factory-v3"
    verifier: str = "chromium-contract-v1"
    contract: int = 1
