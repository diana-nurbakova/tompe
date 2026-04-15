"""Ablation baselines for ToM-PE pipeline validation.

B0 — random_perturbation: word-level corruptions, no LLM
B1 — single_step_inject: single LLM call (no planning step)
B2 — unconstrained_inject: LLM without codebook guidance
"""

from experiments.pipeline_validation.baselines.random_perturbation import inject_random
from experiments.pipeline_validation.baselines.single_step_inject import inject_single_step
from experiments.pipeline_validation.baselines.unconstrained_inject import inject_unconstrained

__all__ = ["inject_random", "inject_single_step", "inject_unconstrained"]
