"""Persistent Wealth-internal signing secret; external credentials do not belong here."""
from __future__ import annotations
import json, os, secrets, time
from contextlib import contextmanager
from pathlib import Path
from app.services.ipo.actions import action_state_lock

APPLICATION_SECRET_FILE = Path(__file__).resolve().parents[2] / "data" / "system" / "secrets" / "application.json"
class SystemSecretError(RuntimeError): pass
@contextmanager
def _system_lock(target:Path):
 for attempt in range(100):
  try:
   with action_state_lock(target): yield
   return
  except Exception as exc:
   if str(exc)!="IPO_ACTION_ALREADY_RUNNING" or attempt==99: raise
   time.sleep(.01)

def resolve_application_secret(*, path: Path | None = None) -> str:
    """Return env compatibility override, or atomically create/read the persistent secret."""
    override=os.getenv("DASHBOARD_SECRET_KEY", "").strip()
    if override: return override
    configured_root=os.getenv("WEALTH_DATA_DIR", "").strip()
    target=path or ((Path(configured_root)/"system"/"secrets"/"application.json") if configured_root else APPLICATION_SECRET_FILE)
    with _system_lock(target):
        if target.exists():
            try: data=json.loads(target.read_text(encoding="utf-8"))
            except Exception as exc: raise SystemSecretError("APPLICATION_SECRET_STATE_INVALID") from exc
            if not isinstance(data,dict) or set(data)!={"version","dashboard_secret_key"} or data["version"]!=1 or not isinstance(data["dashboard_secret_key"],str) or not data["dashboard_secret_key"]: raise SystemSecretError("APPLICATION_SECRET_STATE_INVALID")
            return data["dashboard_secret_key"]
        value=secrets.token_urlsafe(48); tmp=target.with_suffix(".tmp")
        try:
            target.parent.mkdir(parents=True,exist_ok=True)
            if os.name=="posix": os.chmod(target.parent,0o700)
            with open(tmp,"x",encoding="utf-8") as f: json.dump({"version":1,"dashboard_secret_key":value},f,allow_nan=False);f.flush();os.fsync(f.fileno())
            os.replace(tmp,target)
            if os.name=="posix": os.chmod(target,0o600)
            return value
        except Exception: tmp.unlink(missing_ok=True);raise
