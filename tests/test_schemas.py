"""Smoke tests for data model imports and basic validation."""

from tompe.schemas import (
    AnnotationLevel,
    ContrastiveExplanation,
    CorpusSegment,
    InjectedError,
    ItemPathway,
    MQMCategory,
    PrimaryTag,
    Severity,
    SkillID,
    TOMLevel,
)
from tompe.schemas.annotation import AnnotationConfig


def test_corpus_segment_creation():
    segment = CorpusSegment(
        segment_id="test-001",
        source_text="The European Parliament has adopted this regulation.",
        reference_translation="Le Parlement européen a adopté ce règlement.",
        source_lang="en",
        target_lang="fr",
        corpus_origin="europarl",
        domain="parliamentary",
        complexity_score=0.3,
        terminology_density=0.1,
        text_register="formal",
    )
    assert segment.segment_id == "test-001"
    assert segment.source_lang == "en"


def test_injected_error_creation():
    error = InjectedError(
        error_id="err-001",
        span_start=10,
        span_end=20,
        original_text="adopté",
        injected_text="actué",
        primary_tag=PrimaryTag.MISTRANSLATION,
        error_type="false_cognate",
        severity=Severity.MAJOR,
        tom_level=TOMLevel.FIRST_ORDER_MACHINE,
        primary_skill=SkillID.S3,
        explanation=ContrastiveExplanation(
            mt_interpretation="The MT interpreted 'adopted' as a false cognate",
            actual_meaning="The source means 'adopted/passed (legislation)'",
            reader_impact="A reader would not understand the legal action taken",
            correction_rationale="'adopté' is the correct translation in legal context",
        ),
    )
    assert error.primary_tag == PrimaryTag.MISTRANSLATION
    assert error.tom_level == TOMLevel.FIRST_ORDER_MACHINE
    assert error.primary_skill == SkillID.S3


def test_annotation_config_defaults():
    config = AnnotationConfig(level=AnnotationLevel.NAVIGATOR)
    assert config.level == AnnotationLevel.NAVIGATOR
    assert config.show_mqm_labels is False


def test_primary_tag_enum_values():
    assert PrimaryTag.MISTRANSLATION.value == "MISTRANSLATION"
    assert PrimaryTag.GRAMMAR.value == "GRAMMAR"
    assert len(PrimaryTag) == 10


def test_mqm_category_legacy():
    """Legacy MQMCategory should still work."""
    assert MQMCategory.ACCURACY.value == "accuracy"
    assert len(MQMCategory) == 5


def test_tom_level_enum_values():
    assert TOMLevel.FIRST_ORDER_MACHINE.value == "1st_machine"
    assert TOMLevel.RECURSIVE_MULTI.value == "recursive"
    assert len(TOMLevel) == 4


def test_skill_id_enum():
    assert SkillID.S1.value == "S1"
    assert SkillID.S7.value == "S7"
    assert len(SkillID) == 7
