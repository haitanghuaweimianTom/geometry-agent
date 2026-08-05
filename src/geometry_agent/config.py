"""Configuration management (see design/11-Engineering.md §8).

All thresholds, model paths, and LLM parameters live in configs/*.yaml and are
validated by Pydantic Settings.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ParserConfig(BaseModel):
    deskew_threshold_deg: float = 1.0
    skeleton_method: str = "zhang_suen"
    ocr_enabled: bool = True
    sam_enabled: bool = True
    sam_checkpoint: str = ""
    yolo_weights: str = ""


class GraphConfig(BaseModel):
    spatial_bucket_px: float = 40.0
    relation_parallel_workers: int = 4


class VerifierConfig(BaseModel):
    # adaptive tolerance: tol = max(abs_tol, rel_tol * scale)
    on_line_abs_tol: float = 2.0
    on_line_rel_tol: float = 0.005
    on_circle_abs_tol: float = 2.0
    on_circle_rel_tol: float = 0.015
    perp_angle_tol_deg: float = 3.0
    parallel_angle_tol_deg: float = 3.0
    tangent_abs_tol: float = 2.0
    tangent_rel_tol: float = 0.015
    equal_rel_tol: float = 0.02
    equal_angle_tol_deg: float = 2.0
    ellipse_sum_rel_tol: float = 0.015
    collinear_abs_tol: float = 2.0
    collinear_rel_tol: float = 0.005
    concentric_abs_tol: float = 2.0
    concentric_rel_tol: float = 0.01
    uncertain_band_mult: float = 3.0  # uncertain if tol < e <= mult*tol


class DSLConfig(BaseModel):
    include_uncertain: bool = False  # emit uncertain relations as comments
    compact: bool = False  # omit coordinates to save tokens


class VerificationConfig(BaseModel):
    enabled: bool = True
    max_retries: int = 3
    symbolic_timeout_ms: int = 200
    lean_endpoint: str = "http://10.42.0.124:9407"
    lean_timeout_s: int = 10
    llm_judge_enabled: bool = True


class LLMConfig(BaseModel):
    model: str = "GLM-5.2"
    api_key: str = ""
    base_url: str = "http://118.196.164.179:8001/ai-gateway/v1"
    temperature: float = 0.3
    max_tokens: int = 4096
    max_tool_calls: int = 30
    max_reflections: int = 3
    voting_n: int = 1  # 1 = single path; >1 = self-consistency
    fewshot_dir: str = "prompts/fewshot"
    verification: VerificationConfig = VerificationConfig()


class SolverConfig(BaseModel):
    sympy_enabled: bool = True
    z3_enabled: bool = True
    rule_engine_enabled: bool = True
    lean_enabled: bool = False
    equation_selfcheck_enabled: bool = True  # 自动数值核验步骤中形如 lhs = rhs 的等式
    theorem_db_path: str = "theorems/theorems.json"


class HumanLoopConfig(BaseModel):
    enabled: bool = True
    interactive: bool = False  # CLI 交互模式
    out_dir: str = "outputs"
    max_rounds: int = 5
    open_pdf: bool = False  # 是否自动打开 PDF


class KnowledgeConfig(BaseModel):
    enabled: bool = True
    db_path: str = "knowledge/curated.json"  # 持久化路径(可选)
    web_enabled: bool = True
    web_timeout: float = 15.0
    min_local_entries: int = 3  # 本地不足此数才联网


class CodeExecConfig(BaseModel):
    """Sandboxed code execution tool config (design/08 §code tools)."""

    enabled: bool = True
    timeout_sec: float = 10.0
    max_output_chars: int = 2000
    allow_imports: list[str] = ["math", "numpy", "sympy", "fractions", "decimal", "statistics"]


class Settings(BaseSettings):
    """Top-level settings, loaded from configs/*.yaml or env."""

    model_config = SettingsConfigDict(env_prefix="GA_", env_nested_delimiter="__")

    parser: ParserConfig = ParserConfig()
    graph: GraphConfig = GraphConfig()
    verifier: VerifierConfig = VerifierConfig()
    dsl: DSLConfig = DSLConfig()
    llm: LLMConfig = LLMConfig()
    solver: SolverConfig = SolverConfig()
    human_loop: HumanLoopConfig = HumanLoopConfig()
    knowledge: KnowledgeConfig = KnowledgeConfig()
    code_exec: CodeExecConfig = CodeExecConfig()
    verification: VerificationConfig = VerificationConfig()

    debug: bool = False
    log_level: str = "INFO"


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from a YAML file if given, else defaults/env.

    Precedence (highest first):
      1. Environment variables: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
      2. .env file in project root
      3. YAML config file (configs/default.yaml)
      4. Built-in defaults
    """
    import os

    import yaml

    # Load .env file if present (before YAML so YAML can override)
    _env_path = Path(__file__).resolve().parents[2] / ".env"
    if _env_path.exists():
        try:
            with open(_env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass

    settings = Settings()
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        # nested update
        for key, val in data.items():
            if key == "verification" and isinstance(val, dict):
                # Propagate top-level verification block into llm.verification
                sub = settings.llm.verification
                for k, v in val.items():
                    if hasattr(sub, k):
                        setattr(sub, k, v)
                if hasattr(settings, key):
                    sub_top = getattr(settings, key)
                    for k, v in val.items():
                        if hasattr(sub_top, k):
                            setattr(sub_top, k, v)
            elif hasattr(settings, key) and isinstance(val, dict):
                sub = getattr(settings, key)
                for k, v in val.items():
                    if hasattr(sub, k):
                        setattr(sub, k, v)
            elif hasattr(settings, key):
                setattr(settings, key, val)

    # Environment variables override the YAML (so users don't need to edit
    # the config file to inject secrets).
    if os.getenv("LLM_API_KEY"):
        settings.llm.api_key = os.environ["LLM_API_KEY"]
    if os.getenv("LLM_BASE_URL"):
        settings.llm.base_url = os.environ["LLM_BASE_URL"]
    if os.getenv("LLM_MODEL"):
        settings.llm.model = os.environ["LLM_MODEL"]
    return settings
