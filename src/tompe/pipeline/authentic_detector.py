"""Authentic error detection pipeline stage.

For the authentic pathway: detects real errors in MT output by comparing
against human reference using xCOMET-XL and GEMBA-MQM cross-validation.
"""

from tompe.schemas.corpus import CorpusSegment, MTOutput
from tompe.schemas.error import AuthenticErrorDetection


async def detect_authentic_errors(
    segment: CorpusSegment,
    mt_output: MTOutput,
    confidence_threshold: float = 0.8,
) -> AuthenticErrorDetection:
    """Detect and categorize errors in authentic MT output.

    Pipeline:
    1. Compare MT output against human reference
    2. Run xCOMET-XL → word-level error spans with severity
    3. Run GEMBA-MQM → MQM-categorized error annotations
    4. Cross-validate: keep errors detected by both systems
    5. Assign ToM level based on MQM category mapping
    6. Generate Layer 1 + Layer 2 explanations
    7. Flag for human expert validation
    """
    raise NotImplementedError
