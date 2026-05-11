"""Two-step prompt architecture for MQM error injection.

From spec v1.1 §2: Reasoning first (Step 1), then structured output (Step 2).
This separation avoids the 10-15% reasoning degradation from format restrictions
(Tam et al. 2024) while ensuring reliable XML-tagged output.

Also includes prompts for Layer 1 and Layer 2 explanation generation.
"""

from __future__ import annotations

from tompe.pipeline.codebook import CodebookExample
from tompe.pipeline.mqm_taxonomy import TOM_LEVEL_DESCRIPTIONS
from tompe.schemas.enums import PrimaryTag, Severity, TOMLevel


# ============================================================================
# Step 1: Error Planning (Reasoning)
# ============================================================================

SYSTEM_PROMPT_STEP1 = """\
You are a translation quality expert specializing in French-English \
translation errors. You understand MQM error taxonomy and Theory of Mind \
in translation. Your task is to plan a specific translation error \
injection — think carefully about where and how to inject the error.\
"""


def build_step1_prompt(
    source_text: str,
    reference: str,
    primary_tag: PrimaryTag,
    error_type: str,
    severity: Severity,
    tom_level: TOMLevel,
    domain: str,
    definition: str = "",
    boundary_not: str = "",
    mt_system: str = "neural MT",
) -> str:
    """Build the Step 1 (planning) prompt. From spec v1.1 §2.2."""
    tom_desc = TOM_LEVEL_DESCRIPTIONS.get(tom_level, str(tom_level))

    definition_block = ""
    if definition:
        definition_block = f"\nError definition: {definition}"
    if boundary_not:
        definition_block += f"\nBoundary (NOT this type if): {boundary_not}"

    return f"""\
Given the following source text and its correct translation, \
identify ONE location where a {primary_tag.value} ({error_type}) error \
of {severity.value} severity could be naturally introduced — the kind of \
error a {mt_system} would plausibly produce.

Source: {source_text}
Correct translation: {reference}
Domain: {domain}
Error to inject: {primary_tag.value} > {error_type}
Severity: {severity.value}
ToM level: {tom_desc}{definition_block}

Think through:
1. Which word(s) or phrase(s) in the translation are vulnerable to this \
error type?
2. What would the MT system likely "misunderstand" about the source to \
produce this error?
3. What would a target reader infer from the erroneous translation?
4. Is the planned error distinguishable from other error types?

Respond in JSON:
{{
  "target_span": "the word(s) to modify",
  "planned_error": "what the span will become",
  "mt_reasoning": "what the MT system likely misinterpreted",
  "reader_impact": "what a reader would understand",
  "boundary_check": "why this is {error_type} and not something else"
}}\
"""


# ============================================================================
# Step 2: Error Execution (Structured Output with XML Tags)
# ============================================================================

SYSTEM_PROMPT_STEP2 = """\
You are a translation quality expert. Your task is to produce a modified \
translation with exactly one error injected and marked with XML annotation.

The XML tag format is:
<TAG_NAME type="subtype" severity="minor|major|critical" \
tom="1st_machine|1st_author|2nd_reader|recursive" \
desc="5-15 word explanation">error span text</TAG_NAME>

CRITICAL RULES:
1. Modify ONLY the identified span from the planning step.
2. Keep ALL other text EXACTLY identical to the original (character-for-character).
3. The error must be plausible — something a real MT system would produce.
4. The desc attribute must be 5-15 words explaining WHY this is an error.
5. The surrounding text must remain grammatical.

Respond with valid JSON only.\
"""


def build_step2_system_prompt(tag_format: "TagFormat | None" = None) -> str:
    """Return the Step 2 system prompt for the given tag format.

    The C4 production prompt is verbatim ``SYSTEM_PROMPT_STEP2``; the
    C1–C3 ablation variants describe the simpler tag schema and drop
    rules that don't apply (e.g. C1 has no ``desc`` rule).
    """
    from tompe.pipeline.tag_formats import TagFormat

    if tag_format is None or tag_format == TagFormat.C4_FULL:
        return SYSTEM_PROMPT_STEP2

    if tag_format == TagFormat.C1_BARE:
        return """\
You are a translation quality expert. Your task is to produce a modified \
translation with exactly one error injected and marked with XML annotation.

The XML tag format is:
<error>error span text</error>

CRITICAL RULES:
1. Modify ONLY the identified span from the planning step.
2. Keep ALL other text EXACTLY identical to the original (character-for-character).
3. The error must be plausible — something a real MT system would produce.
4. The surrounding text must remain grammatical.

Respond with valid JSON only.\
"""

    if tag_format == TagFormat.C2_CATEGORICAL:
        return """\
You are a translation quality expert. Your task is to produce a modified \
translation with exactly one error injected and marked with XML annotation.

The XML tag format uses the MQM primary tag as the tag name:
<TAG_NAME>error span text</TAG_NAME>
where TAG_NAME is one of: MISTRANSLATION, OMISSION, ADDITION, GRAMMAR, \
TERMINOLOGY, STYLE, LOCALE, UNTRANSLATED, SPELLING, PUNCTUATION.

CRITICAL RULES:
1. Modify ONLY the identified span from the planning step.
2. Keep ALL other text EXACTLY identical to the original (character-for-character).
3. The error must be plausible — something a real MT system would produce.
4. The surrounding text must remain grammatical.

Respond with valid JSON only.\
"""

    # TagFormat.C3_ATTRIBUTED
    return """\
You are a translation quality expert. Your task is to produce a modified \
translation with exactly one error injected and marked with XML annotation.

The XML tag format is:
<TAG_NAME type="subtype" severity="minor|major|critical">error span text</TAG_NAME>

CRITICAL RULES:
1. Modify ONLY the identified span from the planning step.
2. Keep ALL other text EXACTLY identical to the original (character-for-character).
3. The error must be plausible — something a real MT system would produce.
4. The surrounding text must remain grammatical.

Respond with valid JSON only.\
"""


def build_step2_prompt(
    reference: str,
    primary_tag: PrimaryTag,
    error_type: str,
    severity: Severity,
    tom_level: TOMLevel,
    step1_output: dict,
    few_shot_examples: list[CodebookExample] | None = None,
    tag_format: "TagFormat | None" = None,
) -> str:
    """Build the Step 2 (execution) prompt. From spec v1.1 §2.3.

    The ``tag_format`` argument selects one of the C1–C4 tagging
    strategies (spec §5.5); defaults to C4 (the production format).
    For the C1–C3 ablation conditions the prompt's tag template and
    the few-shot examples are re-rendered in the matching format so
    the LLM doesn't see a format mismatch.
    """
    import json as _json
    from tompe.pipeline.tag_formats import (
        TagFormat,
        reformat_codebook_xml,
        tag_template_string,
    )

    if tag_format is None:
        tag_format = TagFormat.C4_FULL

    # Build few-shot section from codebook examples
    examples_text = ""
    if few_shot_examples:
        example_blocks = []
        for i, ex in enumerate(few_shot_examples, 1):
            injected = reformat_codebook_xml(ex.injected, tag_format)
            example_blocks.append(
                f"--- Example {i} ({ex.direction}) ---\n"
                f"Original: {ex.reference}\n"
                f"Injected: {injected}"
            )
        examples_text = (
            "Here are examples of correctly tagged injections:\n\n"
            + "\n\n".join(example_blocks)
            + "\n\n--- Now your task ---\n\n"
        )

    plan_json = _json.dumps(step1_output, ensure_ascii=False, indent=2)

    tag_template = tag_template_string(
        primary_tag=primary_tag,
        error_type=error_type,
        severity=severity,
        tom_level=tom_level,
        fmt=tag_format,
    )

    if tag_format == TagFormat.C1_BARE:
        annotation_descriptor = "an <error> tag"
    else:
        annotation_descriptor = f"a <{primary_tag.value}> tag"

    return f"""\
{examples_text}\
Now produce the modified translation with the error injected using XML \
annotation.

Tag to use: {tag_template}

Original translation: {reference}
Planned modification: {plan_json}

Respond in JSON:
{{
  "injected_translation": "full text with {annotation_descriptor} inline",
  "error_span_text": "just the error span content (inside the tags)",
  "original_span_text": "what was there before",
  "explanation": {{
    "mt_interpretation": "The MT system likely interpreted ... as ...",
    "actual_meaning": "The source actually means ...",
    "reader_impact": "A target reader would understand this as ...",
    "correction_rationale": "The correct translation is ... because ..."
  }}
}}\
"""


# ============================================================================
# Explanation prompts — Layer 1 (Contrastive)
# ============================================================================

SYSTEM_PROMPT_CONTRASTIVE = """\
You are an expert in translation pedagogy and Theory of Mind applied to \
machine translation post-editing training. Your task is to generate a \
contrastive explanation for a specific translation error, helping students \
understand the error from multiple perspectives (MT system, author, reader).

Respond with valid JSON only.\
"""


def build_contrastive_user_prompt(
    source_text: str,
    reference: str,
    original_text: str,
    injected_text: str,
    primary_tag: str,
    error_type: str,
    severity: str,
    brief_explanation: str,
) -> str:
    """Build the user prompt for Layer 1 contrastive explanation."""
    return f"""\
Source text: {source_text}
Reference translation: {reference}

Error details:
- Original (correct): "{original_text}"
- Error (injected): "{injected_text}"
- Type: {primary_tag} > {error_type}
- Severity: {severity}
- Context: {brief_explanation}

Generate a contrastive explanation with these fields:
- mt_interpretation: What the MT system likely "thought" (1-2 sentences)
- actual_meaning: What the source actually means (1-2 sentences)
- reader_impact: How a reader would misinterpret this (1-2 sentences)
- correction_rationale: Why the correct translation is correct (1-2 sentences)\
"""


# ============================================================================
# Explanation prompts — Layer 2a (Popular Science)
# ============================================================================

SYSTEM_PROMPT_LAYER2A = """\
You are an expert in NLP and neural machine translation, specializing in \
explaining MT system behavior to translation students WITHOUT deep technical \
knowledge. Write at "popular science" level — no jargon, use concrete \
analogies and relatable comparisons.

Respond with valid JSON only.\
"""


def build_layer2a_user_prompt(
    primary_tag: str,
    error_type: str,
    mt_system: str,
    brief_explanation: str,
) -> str:
    """Build the user prompt for Layer 2a popular science explanation."""
    system_type = "a general-purpose LLM" if mt_system in (
        "gpt4", "claude", "ollama", "deepseek", "together"
    ) else "a dedicated neural MT system"

    return f"""\
Error type: {primary_tag} > {error_type}
MT system: {mt_system} ({system_type})
Error context: {brief_explanation}

Generate an accessible explanation (for translation students, no NLP jargon):
- error_mechanism: Why MT systems commonly make this type of error \
(2-3 sentences, use analogies)
- architectural_cause: How this relates to how the system works internally \
(2-3 sentences, simplified but accurate)
- pattern_generalization: When students can expect to see similar errors \
(1-2 sentences, actionable cues)
- mt_system_specific: (null if not applicable) How dedicated MT vs LLM \
differs for this error (1-2 sentences)\
"""


# ============================================================================
# Explanation prompts — Layer 2b (Technical)
# ============================================================================

SYSTEM_PROMPT_LAYER2B = """\
You are an NLP researcher explaining MT error mechanisms to advanced students \
who want technical depth. Use proper NLP terminology, cite relevant concepts, \
and be technically precise.

Respond with valid JSON only.\
"""


def build_layer2b_user_prompt(
    primary_tag: str,
    error_type: str,
    mt_system: str,
    brief_explanation: str,
) -> str:
    """Build the user prompt for Layer 2b technical explanation."""
    return f"""\
Error type: {primary_tag} > {error_type}
MT system: {mt_system}
Error context: {brief_explanation}

Generate a technical NLP explanation:
- technical_description: Precise explanation using NLP terminology \
(3-4 sentences)
- key_concepts: List of 3-5 technical concepts involved \
(e.g., "BPE tokenization", "attention coverage gap")
- references: List of 2-3 relevant paper references \
(e.g., "Koehn & Knowles 2017")\
"""


# ============================================================================
# JSON response schemas for structured output
# ============================================================================

STEP1_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "target_span": {"type": "string"},
        "planned_error": {"type": "string"},
        "mt_reasoning": {"type": "string"},
        "reader_impact": {"type": "string"},
        "boundary_check": {"type": "string"},
    },
    "required": ["target_span", "planned_error", "mt_reasoning",
                  "reader_impact", "boundary_check"],
    "additionalProperties": False,
}

STEP2_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "injected_translation": {"type": "string"},
        "error_span_text": {"type": "string"},
        "original_span_text": {"type": "string"},
        "explanation": {
            "type": "object",
            "properties": {
                "mt_interpretation": {"type": "string"},
                "actual_meaning": {"type": "string"},
                "reader_impact": {"type": "string"},
                "correction_rationale": {"type": "string"},
            },
            "required": ["mt_interpretation", "actual_meaning",
                         "reader_impact", "correction_rationale"],
            "additionalProperties": False,
        },
    },
    "required": ["injected_translation", "error_span_text",
                  "original_span_text", "explanation"],
    "additionalProperties": False,
}

CONTRASTIVE_EXPLANATION_SCHEMA = {
    "type": "object",
    "properties": {
        "mt_interpretation": {"type": "string"},
        "actual_meaning": {"type": "string"},
        "reader_impact": {"type": "string"},
        "correction_rationale": {"type": "string"},
    },
    "required": ["mt_interpretation", "actual_meaning",
                  "reader_impact", "correction_rationale"],
    "additionalProperties": False,
}

LAYER2A_SCHEMA = {
    "type": "object",
    "properties": {
        "error_mechanism": {"type": "string"},
        "architectural_cause": {"type": "string"},
        "pattern_generalization": {"type": "string"},
        "mt_system_specific": {"type": ["string", "null"]},
    },
    "required": ["error_mechanism", "architectural_cause",
                  "pattern_generalization", "mt_system_specific"],
    "additionalProperties": False,
}

LAYER2B_SCHEMA = {
    "type": "object",
    "properties": {
        "technical_description": {"type": "string"},
        "key_concepts": {"type": "array", "items": {"type": "string"}},
        "references": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["technical_description", "key_concepts", "references"],
    "additionalProperties": False,
}
