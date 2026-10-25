"""Study execution, contract validation, and research wing framework for God's Ears."""
from .admission import (
    admit_model,
    load_models_lock,
)
from .amalgamation import (
    balance_cross_cell_luminance_and_gaze,
    compose_diptych_triptych_grid,
    export_amalgamated_study_timeline,
    route_polyphonic_cell_audio,
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
from .counterfactuals import (
    audit_counterfactual_seam_integrity,
    insert_diegetic_object,
    register_counterfactual_branch,
    remove_transient_distractor,
)
from .depth_world import (
    estimate_metric_depth_consistency,
    project_relighting_pass,
    reconstruct_room_proxy_geometry,
    validate_parallax_camera_move,
)
from .dispatch import (
    STUDY_BINDING_FAMILY,
    resolve_study_output_dir,
    run_study,
)
from .generative_texture import (
    blend_temporal_texture_cadence,
    enforce_identity_preservation_gate,
    package_generative_material_layer,
    synthesize_bounded_texture_pass,
)
from .motion import (
    couple_gesture_to_sound_events,
    decompose_motion_field,
    extract_gesture_phrasing,
    retarget_motion_envelope,
)
from .provenance_archive import (
    build_provenance_lineage_graph,
    export_counter_archive_packet,
    seal_archival_study_ledger,
    verify_documentary_ethics_disclosure,
)
from .residual_study import (
    classify_residual_regime,
    compute_study_residual_envelope,
    sonify_or_visualize_residual_layer,
    verify_residual_conservation,
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
from .synthesis import (
    ALL_WINGS,
    assemble_comp001_master_synthesis,
    collect_accepted_wing_materials,
    resolve_cross_wing_conflicts,
)
from .temporal_architecture import (
    build_piecewise_retime_curve,
    compile_macro_section_arc,
    detect_phase_lock_conjunctions,
    enforce_long_take_continuity_budget,
)
from .voice_acoustics import (
    align_score_cues_to_breath_cadence,
    convolve_acoustic_space_match,
    estimate_room_impulse_profile,
    extract_vocal_prosody_and_breath,
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
    # Motion & Gesture Decomposition (W03)
    "decompose_motion_field",
    "extract_gesture_phrasing",
    "retarget_motion_envelope",
    "couple_gesture_to_sound_events",
    # Depth, Geometry & World Reconstruction (W04)
    "estimate_metric_depth_consistency",
    "reconstruct_room_proxy_geometry",
    "project_relighting_pass",
    "validate_parallax_camera_move",
    # Counterfactuals & Inpainting (W05)
    "remove_transient_distractor",
    "insert_diegetic_object",
    "audit_counterfactual_seam_integrity",
    "register_counterfactual_branch",
    # Generative Texture (W06)
    "synthesize_bounded_texture_pass",
    "enforce_identity_preservation_gate",
    "blend_temporal_texture_cadence",
    "package_generative_material_layer",
    # Residual Core Studies (W07)
    "compute_study_residual_envelope",
    "classify_residual_regime",
    "sonify_or_visualize_residual_layer",
    "verify_residual_conservation",
    # Voice, Breath & Room Acoustics (W08)
    "extract_vocal_prosody_and_breath",
    "estimate_room_impulse_profile",
    "convolve_acoustic_space_match",
    "align_score_cues_to_breath_cadence",
    # Multi-Frame Amalgamation (W09)
    "compose_diptych_triptych_grid",
    "balance_cross_cell_luminance_and_gaze",
    "route_polyphonic_cell_audio",
    "export_amalgamated_study_timeline",
    # Long-Take Temporal Architecture (W10)
    "build_piecewise_retime_curve",
    "detect_phase_lock_conjunctions",
    "enforce_long_take_continuity_budget",
    "compile_macro_section_arc",
    # Archival Provenance & Counter-Archive (W11)
    "build_provenance_lineage_graph",
    "verify_documentary_ethics_disclosure",
    "seal_archival_study_ledger",
    "export_counter_archive_packet",
    # Cross-Wing Composition Synthesis & Assembly (#114-116)
    "ALL_WINGS",
    "collect_accepted_wing_materials",
    "resolve_cross_wing_conflicts",
    "assemble_comp001_master_synthesis",
]
