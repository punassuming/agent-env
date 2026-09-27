"""Compatibility entry point; canonical runtime is a bootstrap-skill asset."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_source = Path(__file__).resolve().parents[1] / ".agents/skills/bootstrap-agent-env/assets/runtime.py"
_spec = spec_from_file_location("agent_env_skill_runtime", _source)
_module = module_from_spec(_spec)
_spec.loader.exec_module(_module)
load_registry = _module.load_registry
run_command = _module.run_command
main = _module.main
