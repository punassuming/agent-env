"""Compatibility entry point; implementation is bundled with the bootstrap skill."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_source = Path(__file__).resolve().parents[1] / ".agents/skills/bootstrap-agent-env/scripts/bootstrap.py"
_spec = spec_from_file_location("agent_env_skill_bootstrap", _source)
_module = module_from_spec(_spec)
_spec.loader.exec_module(_module)
discover = _module.discover
install = _module.install
finalize = _module.finalize
main = _module.main
