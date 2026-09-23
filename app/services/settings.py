"""Strict, non-secret per-user notification and automation settings (D1)."""
from __future__ import annotations
import copy, json, os, re, threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from app.services.user_manager import get_user_data_dir

SETTINGS_VERSION = 1
_TIME = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
_LOCKS: dict[str, threading.Lock] = {}; _LOCKS_GUARD = threading.Lock()
class SettingsError(RuntimeError): pass
class SettingsValidationError(SettingsError): pass

def default_settings() -> dict[str, Any]:
    return {"version": 1, "telegram": {"enabled": False, "chat_id": None, "allowed_user_id": None, "allowed_chat_id": None}, "automation": {"timezone": "Asia/Seoul", "ipo_refresh_morning": {"enabled": True, "time": "07:30"}, "ipo_reminders": {"enabled": True, "times": ["09:00", "12:00", "15:00"]}, "ipo_listing_reminders": {"enabled": True, "times": ["08:50", "14:50"]}, "ipo_refresh_evening": {"enabled": True, "time": "18:30"}, "daily_close": {"enabled": True, "time": "21:00"}}, "toss_wts": {"session_check_enabled": False}}

def time_to_slot_id(value: str) -> str:
    if not _TIME.fullmatch(value): raise SettingsValidationError("INVALID_TIME")
    return value.replace(":", "")

def _path(username: str) -> Path:
    if not isinstance(username, str) or not username.strip() or any(x in username for x in ("/", "\\", "..")) or Path(username).is_absolute(): raise SettingsValidationError("INVALID_USERNAME")
    return get_user_data_dir(username) / "settings.json"

@contextmanager
def settings_lock(path: Path):
    with _LOCKS_GUARD: lock = _LOCKS.setdefault(str(path.resolve()), threading.Lock())
    if not lock.acquire(blocking=False): raise SettingsError("SETTINGS_ALREADY_RUNNING")
    handle=None
    try:
        lock_path=path.with_suffix(".lock"); lock_path.parent.mkdir(parents=True,exist_ok=True); handle=open(lock_path,"a+b")
        try:
            if os.name=="nt":
                import msvcrt
                if lock_path.stat().st_size==0: handle.write(b"0");handle.flush()
                handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl; fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc: raise SettingsError("SETTINGS_ALREADY_RUNNING") from exc
        yield
    finally:
        try:
            if handle:
                handle.seek(0)
                if os.name=="nt":
                    import msvcrt;msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    import fcntl;fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
                handle.close()
        except OSError: pass
        lock.release()

def _merge(base: dict, patch: dict) -> dict:
    out=copy.deepcopy(base)
    for key,value in patch.items(): out[key]=_merge(out[key],value) if isinstance(value,dict) and isinstance(out.get(key),dict) else copy.deepcopy(value)
    return out
def _validate(doc: Any) -> dict:
    # ``toss_wts`` was added after version 1 had already been persisted.  An
    # absent section is therefore a valid legacy document and is normalized to
    # the safe disabled default instead of invalidating all existing users.
    if not isinstance(doc,dict) or set(doc) - {"version","telegram","automation","toss_wts"} or not {"version","telegram","automation"}.issubset(doc) or doc["version"]!=1: raise SettingsValidationError("INVALID_SETTINGS")
    # Version-1 settings predate both Toss and listing reminders.  Normalize
    # absent additive sections before exact validation, preserving all stored
    # user choices without a schema-version bump.
    if "toss_wts" not in doc or "ipo_listing_reminders" not in (doc.get("automation") or {}): doc = _merge(default_settings(), doc)
    t,a=doc["telegram"],doc["automation"]
    if not isinstance(t,dict) or set(t)!={"enabled","chat_id","allowed_user_id","allowed_chat_id"}: raise SettingsValidationError("INVALID_TELEGRAM_SETTINGS")
    if type(t["enabled"]) is not bool or any(v is not None and (type(v) is not int) for k,v in t.items() if k!="enabled"): raise SettingsValidationError("INVALID_TELEGRAM_ID")
    if not isinstance(a,dict) or set(a)!={"timezone","ipo_refresh_morning","ipo_reminders","ipo_listing_reminders","ipo_refresh_evening","daily_close"} or a["timezone"]!="Asia/Seoul": raise SettingsValidationError("INVALID_AUTOMATION_SETTINGS")
    for name in ("ipo_refresh_morning","ipo_refresh_evening","daily_close"):
        x=a[name]
        if not isinstance(x,dict) or set(x)!={"enabled","time"} or type(x["enabled"]) is not bool or not isinstance(x["time"],str) or not _TIME.fullmatch(x["time"]): raise SettingsValidationError("INVALID_TIME")
    for reminder_name in ("ipo_reminders", "ipo_listing_reminders"):
        r=a[reminder_name]
        if not isinstance(r,dict) or set(r)!={"enabled","times"} or type(r["enabled"]) is not bool or not isinstance(r["times"],list) or not r["times"] or any(not isinstance(x,str) or not _TIME.fullmatch(x) for x in r["times"]) or len(set(r["times"]))!=len(r["times"]): raise SettingsValidationError("INVALID_REMINDER_TIMES")
        r["times"].sort()
    toss = doc["toss_wts"]
    if not isinstance(toss, dict) or set(toss) != {"session_check_enabled"} or type(toss["session_check_enabled"]) is not bool: raise SettingsValidationError("INVALID_TOSS_WTS_SETTINGS")
    return doc
def load_stored_settings(username:str, *, path:Path|None=None)->dict|None:
    path=path or _path(username)
    if not path.exists(): return None
    try: return _validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError,UnicodeError,SettingsError) as exc: raise SettingsError("SETTINGS_STATE_INVALID") from exc
def _save(doc:dict,path:Path)->None:
    tmp=path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        with open(tmp,"w",encoding="utf-8") as f: json.dump(doc,f,ensure_ascii=False,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    except Exception: tmp.unlink(missing_ok=True);raise
def _env_id(key:str)->int|None:
    raw=os.getenv(key,"").strip()
    try:return int(raw) if raw else None
    except ValueError:return None
def get_effective_settings(username:str, *, path:Path|None=None)->dict:
    path=path or _path(username); stored=load_stored_settings(username,path=path); result=_merge(default_settings(),stored or {})
    bound=os.getenv("TELEGRAM_WEALTH_USERNAME","").strip()==username
    sources={}
    if bound:
        for field,key in (("chat_id","TELEGRAM_CHAT_ID"),("allowed_user_id","TELEGRAM_ALLOWED_USER_ID"),("allowed_chat_id","TELEGRAM_ALLOWED_CHAT_ID")):
            if stored is None or stored["telegram"].get(field) is None:
                value=_env_id(key)
                if value is not None: result["telegram"][field]=value;sources[f"telegram.{field}"]="environment"
    result["telegram"].update({"bot_token_configured":bool(os.getenv("TELEGRAM_BOT_TOKEN","").strip()) and bound,"bot_token_source":"environment" if bound and os.getenv("TELEGRAM_BOT_TOKEN","").strip() else "none","webhook_secret_configured":bool(os.getenv("TELEGRAM_WEBHOOK_SECRET","").strip()) and bound,"webhook_secret_source":"environment" if bound and os.getenv("TELEGRAM_WEBHOOK_SECRET","").strip() else "none","sources":sources})
    return result
def patch_settings(username:str, patch:dict, *, path:Path|None=None)->dict:
    path=path or _path(username)
    if not isinstance(patch,dict) or "version" in patch: raise SettingsValidationError("INVALID_PATCH")
    with settings_lock(path):
        current=load_stored_settings(username,path=path) or default_settings(); candidate=_validate(_merge(current,patch)); _save(candidate,path)
    return get_effective_settings(username,path=path)
