from dataclasses import dataclass


@dataclass(frozen=True)
class SimVersions:
    factory: str = "sim-factory-v11"
    verifier: str = "chromium-contract-v2"
    contract: int = 1
