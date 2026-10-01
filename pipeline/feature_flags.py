"""Centralizador de feature flags — ETAPA 6."""
from config import cfg

class FeatureFlags:
    def pipeline_state(self): return cfg.feature_pipeline_state
    def professional_logs(self): return cfg.feature_professional_logs
    def safe_mode(self): return cfg.safe_mode
    def dry_run(self): return cfg.dry_run
    def approval(self): return cfg.require_approval
    def gemini(self): return cfg.gemini_video_enabled
