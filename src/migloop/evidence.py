"""Collector-owned file evidence; no field is a model or causal truth verdict."""
from dataclasses import asdict, dataclass
from typing import Any


CONFIRMED_BASES = frozenset({"native_tool", "supported_shell", "supported_python"})


@dataclass(frozen=True)
class FileProof:
    operation_basis: str = "legacy"
    execution: str = "unknown"
    delivery: str = "unknown"
    snapshot: str = "unknown"
    rule: str = ""


def proof_payload(proof: FileProof | None) -> dict[str, str]:
    return asdict(proof or FileProof())


def read_basis(ref: Any) -> str:
    """Same classification for FileRef objects and exported reader payloads."""
    def value(obj: Any, key: str, default: Any = None) -> Any:
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

    if value(ref, "observation_uncertain", False):
        return "overlapping_read"
    if value(ref, "dep", value(value(ref, "ev"), "dep", False)):
        return "dependency_read"
    if not value(ref, "certain", False):
        return "uncertain_version"
    proof = value(ref, "proof")
    if (value(proof, "operation_basis") in CONFIRMED_BASES and value(proof, "execution") == "confirmed"
            and value(proof, "delivery") == "content"):
        return "read"
    return "unverified_read"
