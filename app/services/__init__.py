from importlib import import_module

__all__ = [
    "AsrMergeService",
    "AsrOcrReconciliationService",
    "AsrVocalizationFilterService",
    "ChunkingService",
    "EngineRuntime",
    "GUIProjectBridge",
    "GPUStageScheduler",
    "ProjectService",
    "ResourceDownloadService",
    "SegmentRegroupService",
    "SegmentService",
    "SpeakerDiarizationService",
    "SubtitleExchangeService",
    "VoiceCatalogService",
    "WorkflowRuntime",
]

_MODULE_MAP = {
    "AsrMergeService": ".asr_merge_service",
    "AsrOcrReconciliationService": ".asr_ocr_reconciliation_service",
    "AsrVocalizationFilterService": ".asr_vocalization_filter_service",
    "ChunkingService": ".chunking_service",
    "EngineRuntime": ".engine_runtime",
    "GUIProjectBridge": ".gui_project_bridge",
    "GPUStageScheduler": ".gpu_stage_scheduler",
    "ProjectService": ".project_service",
    "ResourceDownloadService": ".resource_download_service",
    "SegmentRegroupService": ".segment_regroup_service",
    "SegmentService": ".segment_service",
    "SpeakerDiarizationService": ".speaker_diarization_service",
    "SubtitleExchangeService": ".subtitle_exchange_service",
    "VoiceCatalogService": ".voice_catalog_service",
    "WorkflowRuntime": ".workflow_runtime",
}


def __getattr__(name):
    module_name = _MODULE_MAP.get(name)
    if not module_name:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
