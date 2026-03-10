# Reverse Engineering Challenge: corpchat-admin

**Category:** Reverse Engineering
**Difficulty:** Medium
**Flag:** `CTF{r3v_3ng_b4ackd00r_4cc3ss!}`

---

## Overview

While exploring the CorpChat server you find a binary sitting on the filesystem: `corpchat-admin`. It's a compiled admin tool that requires credentials separate from the web platform. The goal is to reverse engineer it, extract the hidden backdoor credentials, and use them to access a maintenance menu that reveals system root credentials.

---

## Step 1 — Initial Reconnaissance

Start with standard recon on the binary.

```bash
$ file corpchat-admin
corpchat-admin: ELF 64-bit LSB executable, x86-64, dynamically linked

$ checksec corpchat-admin
    Arch:     amd64-64-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE
```

No PIE and no stack canary — good to know, though we won't need exploits here. Now run `strings` to do a quick survey:

```bash
$ strings corpchat-admin
```

You'll see some interesting output:

```
Please login with your username and password:
Access denied.
=== CorpChat Admin Tool ===
    1. Backup Database
    ...
===== Maintenance Menu =====
 3. Decrypt Master Key
[SYSTEM ROOT CREDENTIALS]
xor_decode
enc_backdoor_user
enc_backdoor_pass
enc_master_creds
viel spaß!
```

Several things stand out immediately:
- There's a **maintenance menu** that isn't listed in the normal menu
- There are symbols called `enc_backdoor_user`, `enc_backdoor_pass`, and `enc_master_creds`
- There's a function called `xor_decode` with a German comment ("viel spaß!" = "have fun!")
- Login seems straightforward but the credentials are encoded

---

## Step 2 — Static Analysis

Load the binary into Ghidra (free) or IDA. The binary is not stripped, so function names are preserved — this is intentional.

### Finding the XOR Key

In Ghidra, navigate to the `main` function. You'll see it calls `xor_decode` twice before prompting for login:

```c
xor_decode(enc_backdoor_user, decoded_user, 10);
xor_decode(enc_backdoor_pass, decoded_pass, 14);
```

Now look at the `xor_decode` function:

```c
void xor_decode(const unsigned char *encoded, char *output, int len) {
    int key_len = strlen(xor_key);
    for (int i = 0; i < len; i++) {
        output[i] = encoded[i] ^ xor_key[i % key_len];
    }
    output[len] = '\0';
}
```

Simple repeating-key XOR. Now find `xor_key` in the `.rodata` section. In Ghidra it shows up as a global string:

```
xor_key = "49ced06182fcef842e713c81b59025d24857d3ee409d6e719932a3de94f77a11"
```

Looks like a SHA256 hash but it's actually just used as a key — 64 ASCII characters of key material.

### Finding the Encoded Byte Arrays

In the `.rodata` section, locate the three encoded arrays. Ghidra will show them as byte arrays. Note down the values for `enc_backdoor_user` (10 bytes) and `enc_backdoor_pass` (14 bytes):

```
enc_backdoor_user = { 0x47, 0x4f, 0x00, 0x3a, 0x06, 0x51, 0x55, 0x5a, 0x4d, 0x42 }
enc_backdoor_pass = { 0x5a, 0x5c, 0x17, 0x11, 0x01, 0x42, 0x70, 0x54, 0x5f, 0x57, 0x14, 0x55, 0x5c, 0x45 }
```

---

## Step 3 — Decoding the Credentials

Now write a quick decode script. XOR each byte against the corresponding character of the key (repeating):

```python
key = "49ced06182fcef842e713c81b59025d24857d3ee409d6e719932a3de94f77a11"

enc_user = [0x47, 0x4f, 0x00, 0x3a, 0x06, 0x51, 0x55, 0x5a, 0x4d, 0x42]
enc_pass = [0x5a, 0x5c, 0x17, 0x11, 0x01, 0x42, 0x70, 0x54, 0x5f, 0x57, 0x14, 0x55, 0x5c, 0x45]

username = ''.join(chr(enc_user[i] ^ ord(key[i % len(key)])) for i in range(len(enc_user)))
password = ''.join(chr(enc_pass[i] ^ ord(key[i % len(key)])) for i in range(len(enc_pass)))

print(f"Username: {username}")
print(f"Password: {password}")
```

Output:
```
Username: svc_backup
Password: netterFeger69#
```

---

## Step 4 — Finding the Hidden Menu

Back in the decompiled `main_menu` function, look at the switch statement. Options 1–5 and 0 are visible in the printed menu. But there's one more case hidden in the switch:

```c
case 69:
    if (g_priv_level >= 2) {
        maintenance_menu();
        break;
    } else {
        printf("Invalid option.\n");
        break;
    }
```

Option **69** exists but is never printed. It also checks `g_priv_level >= 2`.

Now look at `main` — what sets `g_priv_level`?

```c
if (strcmp(username, decoded_user) == 0 && strcmp(password, decoded_pass) == 0) {
    g_priv_level = 2;    // backdoor user gets level 2
    main_menu();
} else if (strcmp(username, "admin") == 0 && strcmp(password, "admin2026!") == 0) {
    g_priv_level = 1;    // normal admin gets level 1 — NOT enough
    main_menu();
}
```

The normal `admin` account only gets `priv_level = 1`, which is **not enough** to access option 69. Only the backdoor account `svc_backup` gets level 2. This confirms you need the decoded credentials.

---

## Step 5 — Getting the Flag

Login with the backdoor credentials:

```
$ ./corpchat-admin
[banner]

Please login with your username and password:
svc_backup
netterFeger69#
```

You're now in the main menu. Enter `69`:

```
=== CorpChat Admin Tool ===
    1. Backup Database
    2. List Users
    ...
    0. Exit

 Select option: 69

===== Maintenance Menu =====
 1. Create Emergency Admin
 2. Export Hashes
 3. Decrypt Master Key
 0. Go back to Main Menu
============================
```

Select option `3` — Decrypt Master Key:

```
[SYSTEM ROOT CREDENTIALS]
Use these to access the underlying host system.
Credentials: admin_master:CTF{r3v_3ng_b4ackd00r_4cc3ss!}
```

**Flag: `CTF{r3v_3ng_b4ackd00r_4cc3ss!}`**

---

## Alternative: Dynamic Analysis (Easier Path)

If static analysis is too tedious, you can use `gdb` to grab the credentials at runtime — they're decoded into stack variables before the `strcmp` calls:

```bash
$ gdb ./corpchat-admin
(gdb) break strcmp
(gdb) run
# Enter garbage credentials when prompted
# GDB will break on the first strcmp — inspect arguments:
(gdb) x/s $rdi    # or $rsi, depending on calling convention
```

Both arguments to `strcmp` will be visible in memory: your input and the decoded expected value.

Alternatively, use `ltrace` to intercept library calls:

```bash
$ ltrace ./corpchat-admin 2>&1 | grep strcmp
```

This will print both arguments to every `strcmp`, directly revealing the decoded username and password.

---

## Intended Exploit Chain Summary

```
1. Find corpchat-admin binary on the server
2. Run strings → notice XOR decode functions and maintenance menu
3. Open in Ghidra → identify xor_key and encoded arrays in .rodata
4. Decode enc_backdoor_user / enc_backdoor_pass → svc_backup / netterFeger69#
5. Notice hidden option 69 in main_menu switch, requires priv_level >= 2
6. Log in as svc_backup (only account with priv_level = 2)
7. Enter option 69 → maintenance menu
8. Select option 3 → flag printed: CTF{r3v_3ng_b4ackd00r_4cc3ss!}
9. Use admin_master credentials to SSH into the container as root
```
