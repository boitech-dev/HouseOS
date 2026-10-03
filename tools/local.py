#!/usr/bin/env python3
"""Fresh local instance helper. Does not install services or discover/control devices."""
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get('HOUSEOS_PERSONAL_STATE', str(Path.home()/'.local/share/houseos-personal')))
CONFIG = STATE/'settings.json'

def load():
    values = json.loads(CONFIG.read_text())
    return {**os.environ, **values, 'PYTHONPATH': str(ROOT/'backend'), 'PYTHONDONTWRITEBYTECODE': '1'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['init','migrate','run','bootstrap'])
    args=parser.parse_args()
    if args.action=='init':
        if CONFIG.exists(): raise SystemExit('Configuration already exists; edit it locally. No changes made.')
        STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
        for name in ('run','audio','cinema','transcode'): (STATE/name).mkdir(exist_ok=True,mode=0o700)
        user=input('Your dedicated MariaDB user: ').strip()
        schema=input('Your dedicated MariaDB schema: ').strip()
        password=getpass.getpass('MariaDB password (stored only in your private local settings): ')
        if not user or not schema or not password: raise SystemExit('All database fields are required.')
        values={
            'HOUSEOS_DATABASE_URL':f'mysql+pymysql://{urllib.parse.quote(user,safe="")}:{urllib.parse.quote(password,safe="")}@127.0.0.1:3306/{urllib.parse.quote(schema,safe="")}',
            'HOUSEOS_RUNTIME_ROOT':str(STATE),'HOUSEOS_AUDIO_SOCKET':str(STATE/'run/audio.sock'),
            'HOUSEOS_FRONTEND_DIST':str(ROOT/'frontend/dist'),
            'HOUSEOS_ALLOWED_ORIGINS':'http://127.0.0.1:8990','HOUSEOS_COOKIE_SECURE':'false',
            'HOUSEOS_BOOTSTRAP_TOKEN':secrets.token_urlsafe(40),'HOUSEOS_ENCRYPTION_KEY':base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            'HOUSEOS_AUDIO_ENABLED':'false','HOUSEOS_EXTERNAL_FETCH_ENABLED':'false',
            'HOUSEOS_STORAGE_UUID':'','HOUSEOS_DATA_ROOT':str(STATE/'unconfigured-storage'),
            'HOUSEOS_RECEIVER_BASE_URL':'','HOUSEOS_CAST_LAN_CIDR':''}
        fd=os.open(CONFIG,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f:json.dump(values,f,indent=2);f.write('\n')
        print('Private configuration created. Next: migrate, then run. Storage and devices require your own setup.')
    elif args.action=='migrate':
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT/'backend',env=load(),check=True)
    elif args.action=='run':
        env=load();children=[]
        def stop(*_): raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,stop)
        try:
            for command in ([sys.executable,'-m','uvicorn','houseos.main:app','--host','127.0.0.1','--port','8990','--no-access-log'],[sys.executable,'-m','houseos.worker']):
                children.append(subprocess.Popen(command,cwd=ROOT/'backend',env=env))
            print('HouseOS: http://127.0.0.1:8990 — Ctrl+C stops only these local processes.',flush=True)
            while True:
                for child in children:
                    if child.poll() is not None: raise SystemExit('A local component exited; see its output above.')
                import time
                time.sleep(1)
        except KeyboardInterrupt:pass
        finally:
            for child in children:
                if child.poll() is None:child.terminate()
            for child in children:
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:child.kill();child.wait()
    else:
        env=load();username=input('First administrator username: ').strip()
        password=getpass.getpass('New administrator password: ')
        if password!=getpass.getpass('Repeat password: '):raise SystemExit('Passwords do not match.')
        data=json.dumps({'username':username,'name':username,'password':password,'setup_token':env['HOUSEOS_BOOTSTRAP_TOKEN']}).encode()
        req=urllib.request.Request('http://127.0.0.1:8990/api/v1/auth/bootstrap',data=data,headers={'Origin':'http://127.0.0.1:8990','Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=20) as response:
                if response.status not in (200,201):raise SystemExit('Bootstrap did not succeed.')
        except urllib.error.HTTPError as exc:raise SystemExit(f'Bootstrap rejected (HTTP {exc.code}); check password/username rules and whether an administrator already exists.')
        print('Administrator created. Sign in through the local page.')
if __name__=='__main__':main()
