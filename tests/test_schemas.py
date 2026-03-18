"""Smoke tests for data model imports and basic validation."""

from tompe.schemas import (
    AnnotationLevel,
    AssessmentItem,
    ContrastiveExplanation,
    CorpusSegment,
    InjectedError,
    ItemMetadata,
    ItemPathway,
    MQMCategory,
    Severity,
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
        mqm_category=MQMCategory.ACCURACY,
        mqm_subcategory="mistranslation",
        severity=Severity.MAJOR,
        tom_level=TOMLevel.FIRST_ORDER_MACHINE,
        explanation=ContrastiveExplanation(
            mt_interpretation="The MT interpreted 'adopted' as a false cognate",
            actual_meaning="The source means 'adopted/passed (legislation)'",
            reader_impact="A reader would not understand the legal action taken",
            correction_rationale="'adopté' is the correct translation in legal context",
        ),
    )
    assert error.mqm_category == MQMCategory.ACCURACY
    assert error.tom_level == TOMLevel.FIRST_ORDER_MACHINE


def test_annotation_config_defaults():
    config = AnnotationConfig(level=AnnotationLevel.NAVIGATOR)
    assert config.level == AnnotationLevel.NAVIGATOR
    assert config.show_mqm_labels is False


def test_mqm_enum_values():
    assert MQMCategory.ACCURACY.value == "accuracy"
    assert MQMCategory.FLUENCY.value == "fluency"
    assert len(MQMCategory) == 5


def test_tom_level_enum_values():
    assert TOMLevel.FIRST_ORDER_MACHINE.value == "1st_machine"
    assert TOMLevel.RECURSIVE_MULTI.value == "recursive"
    assert len(TOMLevel) == 4
