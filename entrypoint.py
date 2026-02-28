#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import time

# Obfuscated system credentials, I dont want to make it super easy for you guys...
_k = "49ced06182fcef842e713c81b59025d24857d3ee409d6e719932a3de94f77a11"
_d = [0x55, 0x5d, 0x0e, 0x0c, 0x0a, 0x6f, 0x5b, 0x50, 0x4b, 0x46,
      0x03, 0x11, 0x5f, 0x25, 0x6c, 0x72, 0x49, 0x17, 0x04, 0x47,
      0x6c, 0x50, 0x56, 0x56, 0x3d, 0x57, 0x0d, 0x51, 0x51, 0x5e,
      0x00, 0x02, 0x04, 0x4a, 0x6a, 0x03, 0x07, 0x50, 0x56, 0x16,
      0x47, 0x11, 0x44]


def _x():
    return ''.join(chr(_d[i] ^ ord(_k[i % len(_k)])) for i in range(len(_d)))


def run(cmd, **kwargs):
    return subprocess.run(cmd, **kwargs)


# ── NetBird ────────────────────────────────────────────────────────────────────

def setup_netbird():
    if not shutil.which('netbird'):
        print('[netbird] Not installed — skipping', flush=True)
        return

    # Netbird needs to get new priv key that's different from the docker build
    for state_dir in ('/var/lib/netbird', '/etc/netbird'):
        if os.path.isdir(state_dir):
            shutil.rmtree(state_dir)
            os.makedirs(state_dir, exist_ok=True)
            print(f'[netbird] cleared state dir {state_dir}', flush=True)

    ver = run(['netbird', 'version'], capture_output=True, text=True)
    print(f"[netbird] Found: {ver.stdout.strip() or 'version unknown'}", flush=True)

    # Ensure /dev/net/tun exists (required by NetBird)
    tun = '/dev/net/tun'
    if not os.path.exists(tun):
        print('[netbird] /dev/net/tun missing, attempting to create...', flush=True)
        os.makedirs('/dev/net', exist_ok=True)
        r = run(['mknod', tun, 'c', '10', '200'], capture_output=True)
        if r.returncode == 0:
            os.chmod(tun, 0o666)
            print('[netbird] tun device created', flush=True)
        else:
            print('[netbird] WARNING: could not create tun device', flush=True)
    else:
        print('[netbird] /dev/net/tun exists', flush=True)

    run(['netbird', 'service', 'install'], capture_output=True)
    run(['netbird', 'service', 'start'],   capture_output=True)

    setup_key = os.environ.get('NETBIRD_SETUP_KEY', '')
    mgmt_url  = os.environ.get('NETBIRD_MGMT_URL', '')
    hostname  = os.environ.get('HOSTNAME', 'pwnbox')

    if setup_key and mgmt_url:
        print(f"[netbird] Connecting to {mgmt_url} with key {setup_key[:8]}...", flush=True)
        subprocess.Popen(
            ['netbird', 'up', '--setup-key', setup_key,
             '--management-url', mgmt_url, '--hostname', hostname],
            stdout=sys.stdout, stderr=sys.stderr,
        )
        time.sleep(5)
        r = run(['netbird', 'status'], capture_output=True, text=True)
        print(f"[netbird] Status:\n{r.stdout or r.stderr}", flush=True)
    else:
        print('[netbird] WARNING: NETBIRD_SETUP_KEY or NETBIRD_MGMT_URL not set — skipping', flush=True)


# ── SSH ────────────────────────────────────────────────────────────────────────

def setup_sshd():
    print('[sshd] Generating host keys...', flush=True)
    r = run(['ssh-keygen', '-A'], capture_output=True, text=True)
    if r.returncode == 0:
        print('[sshd] Host keys ready', flush=True)
    else:
        print(f"[sshd] WARNING: ssh-keygen failed: {r.stderr.strip()}", flush=True)

    # Dump effective config so mismatches are obvious in docker logs
    r = run(['sshd', '-T'], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if any(k in line for k in ('passwordauthentication', 'usepam', 'permitrootlogin', 'loglevel')):
            print(f'[sshd -T] {line}', flush=True)
    if r.returncode != 0:
        print(f"[sshd] WARNING: config test failed: {r.stderr.strip()}", flush=True)

    subprocess.Popen(['/usr/sbin/sshd', '-D', '-e'], stderr=sys.stderr, stdout=subprocess.DEVNULL)
    print('[sshd] sshd started (auth logs → docker logs -f)', flush=True)


# ── Cron ───────────────────────────────────────────────────────────────────────

def setup_cron():
    r = run(['cron'], capture_output=True, text=True)
    if r.returncode == 0:
        print('[cron] cron started', flush=True)
    else:
        print(f"[cron] WARNING: cron failed: {r.stderr.strip()}", flush=True)


# ── System user ────────────────────────────────────────────────────────────────

def setup_system_user():
    creds = _x()
    user, passwd = creds.split(':', 1)

    result = run(['id', user], capture_output=True)
    if result.returncode != 0:
        print(f'[entrypoint] Creating user {user}...', flush=True)
        run(['useradd', '-m', '-s', '/bin/bash', user], check=True)
        p = subprocess.Popen(['chpasswd'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, err = p.communicate(f'{user}:{passwd}\n'.encode())
        if p.returncode != 0:
            print(f'[entrypoint] WARNING: chpasswd failed: {err.decode().strip()}', flush=True)
        else:
            print(f'[entrypoint] User {user} created and password set', flush=True)
    else:
        print(f'[entrypoint] User {user} already exists', flush=True)

    # Confirm password status
    r = run(['passwd', '-S', user], capture_output=True, text=True)
    print(f'[entrypoint] passwd -S {user}: {r.stdout.strip()}', flush=True)

    os.makedirs('/data/uploads', exist_ok=True)
    os.chmod('/data/uploads', 0o777)
    print('[entrypoint] /data/uploads set to 777', flush=True)


# ── Challenge setup ────────────────────────────────────────────────────────────

def setup_challenge():
    flag_path = '/root/flag.txt'
    if not os.path.exists(flag_path):
        with open(flag_path, 'w') as f:
            f.write('CTF{w1ldcard_t4r_g0t_r00t!}\n')
        os.chmod(flag_path, 0o600)

    cron_path = '/etc/cron.d/corpchat-backup'
    if not os.path.exists(cron_path):
        with open(cron_path, 'w') as f:
            f.write('* * * * * root cd /data/uploads && tar -czf /tmp/uploads_backup.tar.gz *\n')
        os.chmod(cron_path, 0o644)


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('[entrypoint] Container starting up...', flush=True)
    setup_netbird()
    setup_sshd()
    setup_cron()
    setup_system_user()
    setup_challenge()
    print('[entrypoint] Handing off to app.py...', flush=True)
    os.execvp('python', ['python', 'app.py'])
