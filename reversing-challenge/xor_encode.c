#include <stdio.h>
#include <string.h>

int main() {

    const char *key = "49ced06182fcef842e713c81b59025d24857d3ee409d6e719932a3de94f77a11";
    int key_len = strlen(key); 

    const char *strings[] = {
        "svc_backup",
        "Bkp#Svc4dm!n26",
        "admin_master:CTF{r3v_3ng_b4ackd00r_4cc3ss!}",
    };

    const char *names[] = {
        "enc_backdoor_user",
        "enc_backdoor_pass",
        "enc_master_creds",
    };

    for (int i = 0; strings[i] != NULL; i++) {
        int len = strlen(strings[i]);
        printf("static const unsigned char %s[] = {", names[i]);
        for (int j = 0; j < len; j++) {
            printf("0x%02x", (unsigned char)(strings[i][j]^key[j % key_len]));
            if (j < len -1 ) printf(", ");
        }
        printf(" }; // len=%d\n", len);
    }
    return 0;
}