from dataclasses import dataclass


@dataclass
class PreferenceInterpreterOutput:
    priority_weights: dict
    career_stage: str
    risk_tolerance: str


@dataclass
class JobQualityOutput:
    job_id: int
    job_quality_score: float


@dataclass
class FitOutput:
    job_id: int
    fit_score: float
    fit_reasons: list


@dataclass
class SelectionProbabilityOutput:
    job_id: int
    selection_probability: float


@dataclass
class RankerOutput:
    top_jobs: list


def clamp_score(value):
    return max(0.0, min(1.0, float(value)))
