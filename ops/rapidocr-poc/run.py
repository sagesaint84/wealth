"""Native Docker orchestrator and lightweight in-container process supervisor."""
import argparse
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent


def final_pass(records):
    return bool(records) and all(row.get('status')=='PASS' for row in records)


def cgroup_peak():
    try:return int(Path('/sys/fs/cgroup/memory.peak').read_text().strip())
    except (OSError,ValueError):return None


def supervise(commands, timeout=75):
    import psutil
    running=[];results=[];peak_rss=peak_vms=0
    try:
        for command in commands:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
            running.append((process,time.monotonic()))
        # Worker output is small and bounded; pipes cannot fill with OCR text.
        while any(p.poll() is None for p,_ in running):
            rss=vms=0
            for process,start in running:
                if process.poll() is not None:continue
                try:
                    tree=[psutil.Process(process.pid),*psutil.Process(process.pid).children(recursive=True)]
                    for child in tree:
                        try:memory=child.memory_info();rss+=memory.rss;vms+=memory.vms
                        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                except psutil.NoSuchProcess:pass
                if time.monotonic()-start>timeout:
                    os.killpg(process.pid,signal.SIGKILL)
            peak_rss=max(peak_rss,rss);peak_vms=max(peak_vms,vms);time.sleep(.02)
        for process,_ in running:
            output,_=process.communicate(timeout=5)
            try:
                if len(output)>32768 or process.returncode:raise ValueError()
                row=json.loads(output)
                if row.get('status') not in {'PASS','FAIL','BLOCKED','PENDING'}:raise ValueError()
            except (ValueError,TypeError):
                row={'status':'FAIL','code':'CPU_TIMEOUT' if process.returncode==-signal.SIGXCPU else 'WORKER_EXIT_UNCLASSIFIED'}
            results.append(row)
        return results,{'tree_rss_sampled_peak_bytes':peak_rss,'tree_vms_sampled_peak_bytes':peak_vms}
    finally:
        for process,_ in running:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)


def inside(args):
    if platform.system()!='Linux' or platform.machine()!=args.machine:
        print(json.dumps({'status':'FAIL','code':'UNSUPPORTED_PLATFORM'}));return 1
    cases=json.loads((args.bundle/'cases.json').read_text(encoding='utf-8'))
    records=[]
    def command(case):return [sys.executable,str(HERE/'worker.py'),'--bundle',str(args.bundle),'--case',case,'--machine',args.machine,'--limit-mib',str(args.limit_mib)]
    for case in cases:
        rows,memory=supervise([command(case['id'])]);row=rows[0]
        row.update(id=case['id'],limit_mib=args.limit_mib,**memory);records.append(row)
        print(json.dumps(row,allow_nan=False),flush=True)
        if row.get('code') in ('FINANCE_WRITE_DETECTED','OFFLINE_FAIL'):
            records.append({'status':'BLOCKED','code':'UNSAFE_REMAINING_CASES'});break
    else:
        rows,memory=supervise([command('bank_1800'),command('pension_history_png')])
        records.append({'id':'concurrent_two','status':'PASS' if final_pass(rows) else 'FAIL',
                        'code':'OK' if final_pass(rows) else 'CONCURRENT_FAIL','workers':len(rows),**memory})
        print(json.dumps(records[-1]),flush=True)
    peak=cgroup_peak()
    records.append({'id':'cgroup_peak','status':'PASS' if peak is not None else 'FAIL',
                    'code':'OK' if peak is not None else 'METRIC_UNKNOWN','memory_peak_bytes':peak})
    finance_clean=not Path('/tmp/finance').exists()
    records.append({'id':'financial_files','status':'PASS' if finance_clean else 'FAIL',
                    'code':'OK' if finance_clean else 'FINANCE_WRITE_DETECTED'})
    print(json.dumps({'profile_mib':args.limit_mib,'status':'PASS' if final_pass(records) else 'FAIL',
                      'checks':len(records),'cgroup_memory_peak_bytes':peak,'finance_clean':finance_clean}),flush=True)
    return 0 if final_pass(records) else 1


def host(args):
    info=subprocess.run(['docker','image','inspect','--format','{{.Os}}/{{.Architecture}}',args.image],capture_output=True,check=True,text=True).stdout.strip()
    expected='linux/'+('amd64' if args.machine=='x86_64' else 'arm64')
    if info!=expected or platform.system()!='Linux' or platform.machine()!=args.machine:
        print('UNSUPPORTED_PLATFORM');return 1
    failures=[]
    for limit in (512,2048):
        # 2048 is diagnostic only, never a replacement for the 512 gate.
        name=f'wealth-rapidocr-poc-{args.machine}-{os.getpid()}-{limit}'
        command=['docker','run','--rm','--name',name,'--platform',expected,'--network','none','--read-only',
                 '--cap-drop','ALL','--security-opt','no-new-privileges','--user','65534:65534',
                 '--memory','3g','--memory-swap','3g','--pids-limit','128',
                 '--tmpfs','/tmp:rw,noexec,nosuid,size=256m,mode=1777',
                 '--mount',f'type=bind,src={args.bundle.resolve()},dst=/bundle,readonly',args.image,
                 '--machine',args.machine,'--bundle','/bundle','--limit-mib',str(limit)]
        try:
            result=subprocess.run(command,timeout=1100,check=False)
            failures.append(result.returncode!=0)
        except subprocess.TimeoutExpired:
            # Container has a bounded profile timeout; do not report success.
            print(json.dumps({'profile_mib':limit,'status':'FAIL','code':'CPU_TIMEOUT'}));failures.append(True)
        finally:
            # Also kills the container's descendants if the Docker client timed out.
            subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,check=False)
    return 1 if any(failures) else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--inside',action='store_true')
    parser.add_argument('--machine',required=True);parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--image');parser.add_argument('--limit-mib',type=int,default=512)
    args=parser.parse_args();raise SystemExit(inside(args) if args.inside else host(args))
