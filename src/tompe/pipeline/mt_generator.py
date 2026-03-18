"""Multi-system MT generation pipeline stage.

Generates translations from configured MT backends (Google, DeepL, NLLB, GPT-4, Claude, DeepSeek)
for each selected corpus segment.
"""

from tompe.schemas.corpus import CorpusSegment, MTOutput


async def translate_segment(
    segment: CorpusSegment,
    mt_system: str,
    config: dict,
) -> MTOutput:
    """Translate a single segment using the specified MT system."""
    raise NotImplementedError


async def generate_all_translations(
    segment: CorpusSegment,
    mt_systems: list[str],
    config: dict,
) -> list[MTOutput]:
    """Generate translations from all configured MT systems for a segment."""
    raise NotImplementedError
