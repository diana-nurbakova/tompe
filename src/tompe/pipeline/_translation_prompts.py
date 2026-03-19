"""Prompt templates for LLM-as-translator in the MT generation pipeline.

Five prompt strategies producing different error profiles, from least to most
constrained. The strategy is configurable per MT system in mt_backends.yaml.
"""

from __future__ import annotations


# --- System prompts (shared preamble) ---

_TRANSLATOR_SYSTEM = (
    "You are a professional translator. Translate the source text accurately "
    "and fluently into the target language. Output ONLY the translation, "
    "with no explanations, notes, or commentary."
)


# --- Strategy builders ---

def build_zero_shot(
    source_text: str,
    source_lang: str,
    target_lang: str,
    **kwargs,
) -> tuple[str, str]:
    """Zero-shot: simple translation instruction.

    Expected error profile: baseline natural LLM errors — false cognates,
    occasional omissions, register inconsistencies.
    """
    lang_names = {"en": "English", "fr": "French"}
    src = lang_names.get(source_lang, source_lang)
    tgt = lang_names.get(target_lang, target_lang)

    system = _TRANSLATOR_SYSTEM
    user = (
        f"Translate the following {src} text into {tgt}.\n\n"
        f"{source_text}"
    )
    return system, user


def build_domain_context(
    source_text: str,
    source_lang: str,
    target_lang: str,
    domain: str = "",
    register: str = "",
    **kwargs,
) -> tuple[str, str]:
    """Domain-aware: includes domain and register instructions.

    Expected error profile: fewer register errors, potentially more
    terminology errors where domain-specific terms are unfamiliar.
    """
    lang_names = {"en": "English", "fr": "French"}
    src = lang_names.get(source_lang, source_lang)
    tgt = lang_names.get(target_lang, target_lang)

    domain_desc = {
        "legal": "EU legal and regulatory texts",
        "parliamentary": "European Parliament debates and proceedings",
        "institutional": "EU institutional communications and reports",
    }
    register_desc = {
        "formal": "formal register appropriate for official documents",
        "semi-formal": "semi-formal register appropriate for parliamentary discourse",
        "informal": "accessible, clear language for general audiences",
    }

    domain_str = domain_desc.get(domain, domain) if domain else "institutional texts"
    register_str = register_desc.get(register, register) if register else "formal register"

    system = (
        f"You are a professional translator specializing in {domain_str}. "
        f"Translate accurately and fluently into {tgt}, maintaining "
        f"{register_str}. Output ONLY the translation."
    )
    user = (
        f"Translate the following {src} text into {tgt}.\n"
        f"Domain: {domain_str}\n"
        f"Register: {register_str}\n\n"
        f"{source_text}"
    )
    return system, user


def build_glossary_guided(
    source_text: str,
    source_lang: str,
    target_lang: str,
    glossary_entries: list[dict] | None = None,
    **kwargs,
) -> tuple[str, str]:
    """Glossary-guided: includes IATE terminology for the segment.

    Expected error profile: tests whether LLM follows glossary or ignores it.
    Errors where glossary terms are not used are highly diagnostic.
    """
    lang_names = {"en": "English", "fr": "French"}
    src = lang_names.get(source_lang, source_lang)
    tgt = lang_names.get(target_lang, target_lang)

    glossary_text = ""
    if glossary_entries:
        lines = []
        for entry in glossary_entries:
            src_term = entry.get("source_term", "")
            tgt_term = entry.get("target_term", "")
            if src_term and tgt_term:
                lines.append(f"  {src_term} → {tgt_term}")
        if lines:
            glossary_text = (
                "\n\nTerminology glossary (use these exact translations "
                "for the following terms):\n" + "\n".join(lines)
            )

    system = (
        "You are a professional translator working with official EU/UN documents. "
        "You MUST use the provided terminology glossary for domain-specific terms. "
        f"Translate accurately into {tgt}. Output ONLY the translation."
    )
    user = (
        f"Translate the following {src} text into {tgt}.{glossary_text}\n\n"
        f"Source text:\n{source_text}"
    )
    return system, user


def build_few_shot(
    source_text: str,
    source_lang: str,
    target_lang: str,
    examples: list[dict] | None = None,
    domain: str = "",
    **kwargs,
) -> tuple[str, str]:
    """Few-shot: 2-3 source→reference examples from the same corpus/domain.

    Expected error profile: primes the model with domain style. Errors reveal
    where the model deviates from established patterns despite seeing examples.
    """
    lang_names = {"en": "English", "fr": "French"}
    src = lang_names.get(source_lang, source_lang)
    tgt = lang_names.get(target_lang, target_lang)

    domain_str = f" in the {domain} domain" if domain else ""

    system = (
        f"You are a professional translator{domain_str}. "
        f"Translate {src} texts into {tgt}, following the style and conventions "
        f"shown in the examples. Output ONLY the translation."
    )

    examples_text = ""
    if examples:
        example_blocks = []
        for i, ex in enumerate(examples, 1):
            src_ex = ex.get("source_text", "")
            ref_ex = ex.get("reference_translation", "")
            example_blocks.append(
                f"Example {i}:\n"
                f"{src}: {src_ex}\n"
                f"{tgt}: {ref_ex}"
            )
        examples_text = "\n\n".join(example_blocks) + "\n\n"

    user = (
        f"{examples_text}"
        f"Now translate:\n"
        f"{src}: {source_text}\n"
        f"{tgt}:"
    )
    return system, user


def build_few_shot_glossary(
    source_text: str,
    source_lang: str,
    target_lang: str,
    examples: list[dict] | None = None,
    glossary_entries: list[dict] | None = None,
    domain: str = "",
    **kwargs,
) -> tuple[str, str]:
    """Few-shot + glossary: combines domain priming with terminology guidance.

    Most constrained strategy. Errors are most diagnostic — they indicate
    where the model fails despite having both stylistic examples and
    explicit terminology guidance.
    """
    lang_names = {"en": "English", "fr": "French"}
    src = lang_names.get(source_lang, source_lang)
    tgt = lang_names.get(target_lang, target_lang)

    domain_str = f" in the {domain} domain" if domain else ""

    system = (
        f"You are a professional translator{domain_str}. "
        f"Translate {src} texts into {tgt}, following the style shown in the "
        f"examples and using the provided terminology glossary for domain-specific "
        f"terms. Output ONLY the translation."
    )

    # Build glossary section
    glossary_text = ""
    if glossary_entries:
        lines = []
        for entry in glossary_entries:
            src_term = entry.get("source_term", "")
            tgt_term = entry.get("target_term", "")
            if src_term and tgt_term:
                lines.append(f"  {src_term} → {tgt_term}")
        if lines:
            glossary_text = (
                "Terminology glossary:\n" + "\n".join(lines) + "\n\n"
            )

    # Build examples section
    examples_text = ""
    if examples:
        example_blocks = []
        for i, ex in enumerate(examples, 1):
            src_ex = ex.get("source_text", "")
            ref_ex = ex.get("reference_translation", "")
            example_blocks.append(
                f"Example {i}:\n"
                f"{src}: {src_ex}\n"
                f"{tgt}: {ref_ex}"
            )
        examples_text = "\n\n".join(example_blocks) + "\n\n"

    user = (
        f"{glossary_text}"
        f"{examples_text}"
        f"Now translate:\n"
        f"{src}: {source_text}\n"
        f"{tgt}:"
    )
    return system, user


# --- Strategy registry ---

PROMPT_STRATEGIES: dict[str, callable] = {
    "zero_shot": build_zero_shot,
    "domain_context": build_domain_context,
    "glossary_guided": build_glossary_guided,
    "few_shot": build_few_shot,
    "few_shot_glossary": build_few_shot_glossary,
}


def build_translation_prompt(
    strategy: str,
    source_text: str,
    source_lang: str,
    target_lang: str,
    **kwargs,
) -> tuple[str, str]:
    """Build a (system, user) prompt pair for the given strategy.

    Args:
        strategy: One of the PROMPT_STRATEGIES keys.
        source_text: The text to translate.
        source_lang: Source language code ("en" or "fr").
        target_lang: Target language code ("en" or "fr").
        **kwargs: Strategy-specific arguments (domain, register, examples, glossary_entries).

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    builder = PROMPT_STRATEGIES.get(strategy)
    if builder is None:
        raise ValueError(
            f"Unknown prompt strategy {strategy!r}. "
            f"Available: {list(PROMPT_STRATEGIES.keys())}"
        )
    return builder(source_text, source_lang, target_lang, **kwargs)
