"""Demo run / request models and validation status enum."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class ValidationStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NA = "N/A"

    @classmethod
    def coerce(cls, value: str | ValidationStatus | None) -> ValidationStatus:
        if value is None:
            return cls.NA
        if isinstance(value, cls):
            return value
        raw = str(value).strip().upper().replace("NA", "N/A")
        if raw in ("N/A", "NA", "NONE"):
            return cls.NA
        return cls(raw)


VALIDATION_DIMENSIONS = (
    "classification",
    "policy",
    "capability",
    "lifecycle",
    "route",
    "endpoint",
    "telemetry",
)


def new_id() -> str:
    return str(uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DemoRequest:
    demo_run_id: str
    scenario_id: str
    request_id: str
    prompt: str
    expected: dict[str, Any] = field(default_factory=dict)
    actual: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, str] = field(default_factory=dict)
    telemetry: dict[str, Any] = field(default_factory=dict)
    display_name: str | None = None
    index: int = 0
    status: str = "pending"  # pending|running|completed|error
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    def overall(self) -> ValidationStatus:
        statuses = [ValidationStatus.coerce(v) for v in self.validation.values()]
        if any(s == ValidationStatus.FAIL for s in statuses):
            return ValidationStatus.FAIL
        if any(s == ValidationStatus.WARN for s in statuses):
            return ValidationStatus.WARN
        if statuses and all(s in (ValidationStatus.PASS, ValidationStatus.NA) for s in statuses):
            if any(s == ValidationStatus.PASS for s in statuses):
                return ValidationStatus.PASS
        return ValidationStatus.NA

    def presentation(self):
        """Executive-facing status (ADVISORY vs WARN); does not alter validation."""
        from token_factory.demo.presentation import classify_presentation_status

        return classify_presentation_status(self.validation, self.actual, self.expected)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        overall = self.overall()
        pres = self.presentation()
        data["validation_status"] = overall.value
        data["presentation_status"] = pres.status
        data["advisory_reason"] = pres.advisory_reason
        return data


@dataclass
class DemoRun:
    id: str
    scenario_pack: str
    lifecycle_mode: str = "production"
    traffic_profile: str = "sequential"
    started_at: str | None = None
    completed_at: str | None = None
    requests: list[DemoRequest] = field(default_factory=list)
    validation_summary: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    injections: list[str] = field(default_factory=list)
    seed: int | None = None
    concurrency: int = 1
    mock: bool = False
    ci: bool = False
    distributions: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        scenario_pack: str,
        *,
        lifecycle_mode: str = "production",
        traffic_profile: str = "sequential",
        seed: int | None = None,
        concurrency: int = 1,
        injections: list[str] | None = None,
        mock: bool = False,
        ci: bool = False,
    ) -> DemoRun:
        return cls(
            id=new_id(),
            scenario_pack=scenario_pack,
            lifecycle_mode=lifecycle_mode,
            traffic_profile=traffic_profile,
            seed=seed,
            concurrency=concurrency,
            injections=list(injections or []),
            mock=mock,
            ci=ci,
            started_at=utc_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.id,
            "scenario_pack": self.scenario_pack,
            "lifecycle_mode": self.lifecycle_mode,
            "traffic_profile": self.traffic_profile,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "seed": self.seed,
            "concurrency": self.concurrency,
            "injections": self.injections,
            "mock": self.mock,
            "ci": self.ci,
            "validation_summary": self.validation_summary,
            "coverage": self.coverage,
            "distributions": self.distributions,
            "meta": self.meta,
            "requests": [r.to_dict() for r in self.requests],
        }

    def policy_ok(self) -> bool:
        """True when no FAIL on policy-critical dimensions (CI exit criterion)."""
        critical = ("classification", "policy", "capability", "lifecycle", "route", "endpoint")
        for req in self.requests:
            for dim in critical:
                if ValidationStatus.coerce(req.validation.get(dim)) == ValidationStatus.FAIL:
                    return False
        return True
