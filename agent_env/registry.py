"""Compatibility entry point; registry manager is bundled with the bootstrap skill."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_source = Path(__file__).resolve().parents[1] / ".agents/skills/bootstrap-agent-env/scripts/registry.py"
_spec = spec_from_file_location("agent_env_skill_registry", _source)
_module = module_from_spec(_spec)
_spec.loader.exec_module(_module)
safe_path = _module.safe_path
load = _module.load
files = _module.files
deploy = _module.deploy
