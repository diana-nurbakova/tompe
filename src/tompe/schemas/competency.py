"""Competency/skill model for the ToM-PE platform.

Defines 7 core PE skills (S1-S7) that map to the intersection of MQM error
detection, ToM perspective-taking, and PE action. From spec v1.1 §3.2-3.5.
"""

from pydantic import BaseModel

from tompe.schemas.enums import AnnotationLevel, PrimaryTag, SkillID, TOMLevel


class SkillDefinition(BaseModel):
    """Definition of a single PE competency skill."""

    skill_id: SkillID
    name: str
    description: str
    primary_tags: list[PrimaryTag]
    primary_tom_level: TOMLevel


class MasteryThreshold(BaseModel):
    """Mastery criteria for a single skill. From spec v1.1 §3.5."""

    skill_id: SkillID
    metric: str
    threshold: float
    window_sessions: int


class StageDefinition(BaseModel):
    """Progression stage mapping skills to scaffolding levels. From §3.4."""

    stage: int
    name: str
    active_skills: list[SkillID]
    annotation_level: AnnotationLevel
    exercise_modes: str


# ============================================================================
# The 7 core skills (§3.2)
# ============================================================================

SKILL_DEFINITIONS: list[SkillDefinition] = [
    SkillDefinition(
        skill_id=SkillID.S1,
        name="Surface Error Detection",
        description=(
            "Detect spelling, punctuation, capitalization, and character encoding errors"
        ),
        primary_tags=[PrimaryTag.SPELLING, PrimaryTag.PUNCTUATION],
        primary_tom_level=TOMLevel.FIRST_ORDER_MACHINE,
    ),
    SkillDefinition(
        skill_id=SkillID.S2,
        name="Grammatical Error Detection",
        description=(
            "Detect morphosyntactic errors: agreement, tense, word order, articles"
        ),
        primary_tags=[PrimaryTag.GRAMMAR],
        primary_tom_level=TOMLevel.FIRST_ORDER_MACHINE,
    ),
    SkillDefinition(
        skill_id=SkillID.S3,
        name="Meaning Transfer Verification",
        description=(
            "Detect mistranslation, false cognates, sense errors by comparing "
            "source-target meaning"
        ),
        primary_tags=[PrimaryTag.MISTRANSLATION],
        primary_tom_level=TOMLevel.FIRST_ORDER_MACHINE,
    ),
    SkillDefinition(
        skill_id=SkillID.S4,
        name="Completeness Verification",
        description=(
            "Detect omissions and additions by verifying all source content "
            "is present in target"
        ),
        primary_tags=[PrimaryTag.OMISSION, PrimaryTag.ADDITION, PrimaryTag.UNTRANSLATED],
        primary_tom_level=TOMLevel.FIRST_ORDER_AUTHOR,
    ),
    SkillDefinition(
        skill_id=SkillID.S5,
        name="Terminology Verification",
        description=(
            "Detect domain-specific term errors by checking against "
            "terminological resources"
        ),
        primary_tags=[PrimaryTag.TERMINOLOGY],
        primary_tom_level=TOMLevel.SECOND_ORDER_READER,
    ),
    SkillDefinition(
        skill_id=SkillID.S6,
        name="Pragmatic & Style Evaluation",
        description=(
            "Detect register, idiomaticity, style, and locale convention errors"
        ),
        primary_tags=[PrimaryTag.STYLE, PrimaryTag.LOCALE],
        primary_tom_level=TOMLevel.SECOND_ORDER_READER,
    ),
    SkillDefinition(
        skill_id=SkillID.S7,
        name="Coherence & Discourse Evaluation",
        description=(
            "Detect inter-sentential coherence breaks, anaphoric errors, "
            "discourse flow issues"
        ),
        primary_tags=[],  # Cross-category
        primary_tom_level=TOMLevel.RECURSIVE_MULTI,
    ),
]

# ============================================================================
# Mastery criteria per skill (§3.5)
# ============================================================================

MASTERY_THRESHOLDS: list[MasteryThreshold] = [
    MasteryThreshold(skill_id=SkillID.S1, metric="detection_rate", threshold=0.90, window_sessions=3),
    MasteryThreshold(skill_id=SkillID.S2, metric="detection_rate", threshold=0.80, window_sessions=3),
    MasteryThreshold(skill_id=SkillID.S3, metric="detection_rate", threshold=0.70, window_sessions=3),
    MasteryThreshold(skill_id=SkillID.S4, metric="detection_rate", threshold=0.65, window_sessions=3),
    MasteryThreshold(skill_id=SkillID.S5, metric="detection_rate", threshold=0.70, window_sessions=3),
    MasteryThreshold(skill_id=SkillID.S6, metric="detection_rate", threshold=0.60, window_sessions=3),
    MasteryThreshold(skill_id=SkillID.S7, metric="detection_rate", threshold=0.55, window_sessions=3),
]

# Cross-skill thresholds
OVER_EDITING_THRESHOLD = 0.20  # Max false positive rate
JUSTIFICATION_DEPTH_THRESHOLD = 0.40  # Min % rated "deep"

# ============================================================================
# Skill → Progression Stage Mapping (§3.4)
# ============================================================================

PROGRESSION_STAGES: list[StageDefinition] = [
    StageDefinition(
        stage=1,
        name="Orientation",
        active_skills=[SkillID.S1, SkillID.S2],
        annotation_level=AnnotationLevel.NAVIGATOR,
        exercise_modes="Evaluation only, Critical severity, EN→FR only",
    ),
    StageDefinition(
        stage=2,
        name="Guided Detection",
        active_skills=[SkillID.S3, SkillID.S4],
        annotation_level=AnnotationLevel.GUIDED,
        exercise_modes="Evaluation, Major severity added",
    ),
    StageDefinition(
        stage=3,
        name="Independent Evaluation",
        active_skills=[SkillID.S3, SkillID.S4, SkillID.S5, SkillID.S6],
        annotation_level=AnnotationLevel.INDEPENDENT,
        exercise_modes="Evaluation + PE, mixed severity",
    ),
    StageDefinition(
        stage=4,
        name="Dual Mode",
        active_skills=[SkillID.S1, SkillID.S2, SkillID.S3, SkillID.S4, SkillID.S5, SkillID.S6],
        annotation_level=AnnotationLevel.INDEPENDENT,
        exercise_modes="Evaluation + PE, both directions",
    ),
    StageDefinition(
        stage=5,
        name="Expert",
        active_skills=[SkillID.S1, SkillID.S2, SkillID.S3, SkillID.S4, SkillID.S5, SkillID.S6, SkillID.S7],
        annotation_level=AnnotationLevel.EXPERT,
        exercise_modes="Independent eval + Comparative ranking + PE triage",
    ),
]
