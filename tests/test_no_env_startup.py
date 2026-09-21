import os,subprocess,sys,tempfile,unittest
from pathlib import Path
class NoEnvStartupTests(unittest.TestCase):
 def test_import_without_env_creates_persistent_system_secret(self):
  with tempfile.TemporaryDirectory() as d:
   env=dict(os.environ);env['PYTHONPATH']='.';env['WEALTH_DATA_DIR']=d;env['WEALTH_ENV']='production';env['WEALTH_DISABLE_ENV_FILE']='1'
   for key in list(env):
    if key=='DASHBOARD_SECRET_KEY' or key.startswith(('TELEGRAM_','KIS_','KIWOOM_','NHPLUG_','KB_','TOSS_')):env.pop(key,None)
   code="import app.main;print(bool(app.main.SECRET_KEY))"
   first=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=20);self.assertEqual(first.returncode,0,first.stderr);self.assertIn('True',first.stdout)
   p=Path(d)/'system'/'secrets'/'application.json';self.assertTrue(p.exists());before=p.read_bytes()
   second=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=20);self.assertEqual(second.returncode,0,second.stderr);self.assertEqual(p.read_bytes(),before)
