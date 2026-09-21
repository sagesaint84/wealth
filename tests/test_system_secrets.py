import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app.services.system_secrets import resolve_application_secret
class SystemSecretTests(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=Path(self.t.name)/'system'/'secrets'/'application.json'
 def test_first_boot_and_restart(self):
  with patch.dict(os.environ,{'DASHBOARD_SECRET_KEY':''}):
   a=resolve_application_secret(path=self.p);b=resolve_application_secret(path=self.p)
  self.assertEqual(a,b);self.assertGreater(len(a),40);self.assertEqual(json.loads(self.p.read_text())['version'],1)
 def test_concurrent_first_boot_same_value(self):
  code="from pathlib import Path;from app.services.system_secrets import resolve_application_secret;import sys;print(resolve_application_secret(path=Path(sys.argv[1])))"
  env=dict(os.environ);env['PYTHONPATH']='.';env.pop('DASHBOARD_SECRET_KEY',None)
  ps=[subprocess.Popen([sys.executable,'-c',code,str(self.p)],env=env,stdout=subprocess.PIPE,text=True) for _ in range(2)]
  values=[p.communicate(timeout=10)[0].strip() for p in ps];self.assertEqual([p.returncode for p in ps],[0,0]);self.assertEqual(values[0],values[1])
