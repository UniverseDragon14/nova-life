#!/usr/bin/env python3
import importlib.util, json, subprocess, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; FIXTURES=Path(__file__).resolve().parent/'fixtures'; LOOP=ROOT/'loop.py'
spec=importlib.util.spec_from_file_location('network_loop',LOOP); network_loop=importlib.util.module_from_spec(spec); spec.loader.exec_module(network_loop)
class NetworkDiagnosisTests(unittest.TestCase):
    def test_every_fixture_row_via_cli(self):
        files=sorted(FIXTURES.glob('*.json')); self.assertGreaterEqual(len(files),8)
        for path in files:
            expected=json.loads(path.read_text())['expected']; p=subprocess.run([sys.executable,str(LOOP),'--fixture',str(path),'--no-write'],capture_output=True,text=True,timeout=4,check=True); out=json.loads(p.stdout); self.assertEqual(out['diagnosis'],expected,path.name); self.assertTrue(out['problem_key'].startswith('network_diagnosis+diagnose+'))
    def test_restricted_lte_route_never_selected(self):
        routes=[{'iface':'tun_srsue','gateway':'10.0.0.1','metric':1,'excluded':True},{'iface':'ogstun','gateway':'10.45.0.1','metric':2,'excluded':True},{'iface':'wlan0','gateway':'192.0.2.1','metric':600,'excluded':False}]; self.assertEqual(network_loop.choose_route(routes)['iface'],'wlan0')
    def test_problem_key_shape(self):
        route={'iface':'wlan0','gateway':'192.0.2.1','metric':600,'excluded':False}; iface=network_loop.choose_route([route])['iface']; self.assertEqual(f'network_diagnosis+diagnose+{iface}','network_diagnosis+diagnose+wlan0')
    def test_registry_probe_guards(self):
        data=json.loads((ROOT/'action_registry.json').read_text())
        for name,row in data['actions'].items():
            if name.startswith('probe_'): self.assertEqual(row['zone'],'Green'); self.assertTrue(row['verifier']); self.assertLessEqual(row['timeout_seconds'],3)
        self.assertLessEqual(network_loop.WHOLE_RUN_TIMEOUT,20)
    def test_diagnosis_precedence(self):
        self.assertEqual(network_loop.derive_diagnosis(False,True,True,True,True),'local_gateway_problem_suspected'); self.assertEqual(network_loop.derive_diagnosis(True,True,False,True,True),'captive_portal_or_filtered_suspected'); self.assertEqual(network_loop.derive_diagnosis(True,True,True,False,True),'local_resolver_suspected')
if __name__=='__main__': unittest.main()
