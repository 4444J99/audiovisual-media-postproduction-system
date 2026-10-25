"""Study execution, contract validation, and research wing framework for God's Ears."""
from .admission import (
    admit_model,
    load_models_lock,
)
from .contracts import (
    REQUIRED_PROVENANCE_FIELDS,
    STATUS_AXIS,
    validate_binding,
    validate_dependency_dag,
    validate_mask_to_body_span,
    validate_material,
    validate_performance,
)
from .dispatch import (
    STUDY_BINDING_FAMILY,
    resolve_study_output_dir,
    run_study,
)
from .review import (
    build_review,
    compute_loudness_matching_gain,
    map_retimed_moments,
    verify_finite_samples,
)
from .sound_separation import (
    build_source_event_palette,
    compare_voice_and_object_separation,
    compose_separated_instrument_study,
    run_sound_separation,
)
from .surface_atlas import (
    apply_persistent_surface_edit,
    promote_accepted_surface,
    run_material_transfers,
    validate_canonical_surface,
)

__all__ = [
    # Dispatch
    "STUDY_BINDING_FAMILY",
    "run_study",
    "resolve_study_output_dir",
    # Review
    "build_review",
    "compute_loudness_matching_gain",
    "map_retimed_moments",
    "verify_finite_samples",
    # Contracts (F03)
    "STATUS_AXIS",
    "REQUIRED_PROVENANCE_FIELDS",
    "validate_binding",
    "validate_material",
    "validate_performance",
    "validate_dependency_dag",
    "validate_mask_to_body_span",
    # Admission (F04)
    "admit_model",
    "load_models_lock",
    # Sound Separation (W01)
    "run_sound_separation",
    "compare_voice_and_object_separation",
    "build_source_event_palette",
    "compose_separated_instrument_study",
    # Surface & Atlas (W02)
    "validate_canonical_surface",
    "apply_persistent_surface_edit",
    "run_material_transfers",
    "promote_accepted_surface",
]
