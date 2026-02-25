#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sqlite3.h>
#include <sys/stat.h>
#include <time.h>
#include <strings.h>

#define DB_PATH     "./data/corpchat.db"
#define BACKUP_DIR  "./data/backups"
#define VERSION     "corpchat-admin v1.0.3-internal"

static const char xor_key[] = "49ced06182fcef842e713c81b59025d24857d3ee409d6e719932a3de94f77a11";
static const unsigned char enc_backdoor_user[] = {0x47, 0x4f, 0x00, 0x3a, 0x06, 0x51, 0x55, 0x5a, 0x4d, 0x42 }; // len=10
static const unsigned char enc_backdoor_pass[] = {0x5a, 0x5c, 0x17, 0x11, 0x01, 0x42, 0x70, 0x54, 0x5f, 0x57, 0x14, 0x55, 0x5c, 0x45 }; // len=14
static const unsigned char enc_master_creds[] = {0x55, 0x5d, 0x0e, 0x0c, 0x0a, 0x6f, 0x5b, 0x50, 0x4b, 0x46, 0x03, 0x11, 0x5f, 0x25, 0x6c, 0x72, 0x49, 0x17, 0x04, 0x47, 0x6c, 0x50, 0x56, 0x56, 0x3d, 0x57, 0x0d, 0x51, 0x51, 0x5e, 0x00, 0x02, 0x04, 0x4a, 0x6a, 0x03, 0x07, 0x50, 0x56, 0x16, 0x47, 0x11, 0x44 }; // len=43
static int g_priv_level = 0;
static sqlite3 *g_db = NULL;


void banner() {
    printf(" ██████╗ ██████╗ ██████╗ ██████╗  ██████╗██╗  ██╗ █████╗ ████████╗          \n");
    printf("██╔════╝██╔═══██╗██╔══██╗██╔══██╗██╔════╝██║  ██║██╔══██╗╚══██╔══╝          \n");
    printf("██║     ██║   ██║██████╔╝██████╔╝██║     ███████║███████║   ██║             \n");
    printf("██║     ██║   ██║██╔══██╗██╔═══╝ ██║     ██╔══██║██╔══██║   ██║             \n");
    printf("╚██████╗╚██████╔╝██║  ██║██║     ╚██████╗██║  ██║██║  ██║   ██║             \n");
    printf("╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝      ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝              \n");
    printf("                                                                            \n");
    printf(" █████╗ ██████╗ ███╗   ███╗██╗███╗   ██╗████████╗ ██████╗  ██████╗ ██╗      \n");
    printf("██╔══██╗██╔══██╗████╗ ████║██║████╗  ██║╚══██╔══╝██╔═══██╗██╔═══██╗██║      \n");
    printf("███████║██║  ██║██╔████╔██║██║██╔██╗ ██║   ██║   ██║   ██║██║   ██║██║      \n");
    printf("██╔══██║██║  ██║██║╚██╔╝██║██║██║╚██╗██║   ██║   ██║   ██║██║   ██║██║      \n");
    printf("██║  ██║██████╔╝██║ ╚═╝ ██║██║██║ ╚████║   ██║   ╚██████╔╝╚██████╔╝███████╗ \n");
    printf("╚═╝  ╚═╝╚═════╝ ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝   ");
}


void xor_decode(const unsigned char *encoded, char *output, int len) {
    // viel spaß!
    int key_len = strlen(xor_key);
    for (int i = 0; i < len; i++) {
        output[i] = encoded[i] ^ xor_key[i % key_len];
    }
    output[len] = '\0';
}

void open_db() {
    if (g_db != NULL) return;
    if (sqlite3_open(DB_PATH, &g_db) != SQLITE_OK) {
        fprintf(stderr, "Database error: %s\n", sqlite3_errmsg(g_db));
        exit(1);
    }
}

void backup_database() {
    open_db();
    time_t now = time(NULL);
    struct tm *t = localtime(&now);
    char backup_path[256];

    mkdir(BACKUP_DIR, 0755);

    snprintf(backup_path, sizeof(backup_path),
             "%s/corpchat_backup_%04d%02d%02d_%02d%02d%02d.db",
             BACKUP_DIR,
             t->tm_year + 1900, t->tm_mon + 1, t->tm_mday,
             t->tm_hour, t->tm_min, t->tm_sec);

    sqlite3 *backup_db;
    if (sqlite3_open(backup_path, &backup_db) != SQLITE_OK) {
        fprintf(stderr, "Backup error: %s\n", sqlite3_errmsg(backup_db));
        return;
    }

    sqlite3_backup *backup = sqlite3_backup_init(backup_db, "main", g_db, "main");
    if (backup) {
        sqlite3_backup_step(backup, -1);
        sqlite3_backup_finish(backup);
    }

    if (sqlite3_errcode(backup_db) == SQLITE_OK) {
        printf("Backup created: %s\n", backup_path);
    } else {
        fprintf(stderr, "Backup failed: %s\n", sqlite3_errmsg(backup_db));
    }

    sqlite3_close(backup_db);
}

void list_users() {
    open_db();
    sqlite3_stmt *stmt;
    const char *sql = "SELECT id, username, email, role, is_active FROM users ORDER BY id";

    if (sqlite3_prepare_v2(g_db, sql, -1, &stmt, NULL) != SQLITE_OK) {
        fprintf(stderr, "Query error: %s\n", sqlite3_errmsg(g_db));
        return;
    }

    printf("\n%-5s %-20s %-30s %-10s %-8s\n", "ID", "Username", "Email", "Role", "Active");
    printf("----------------------------------------------------------------------\n");

    while (sqlite3_step(stmt) == SQLITE_ROW) {
        printf("%-5d %-20s %-30s %-10s %-8s\n",
               sqlite3_column_int(stmt, 0),
               (const char *)sqlite3_column_text(stmt, 1),
               (const char *)sqlite3_column_text(stmt, 2),
               (const char *)sqlite3_column_text(stmt, 3),
               sqlite3_column_int(stmt, 4) ? "Yes" : "No");
    }

    sqlite3_finalize(stmt);
}

void add_audit_entry() {
    open_db();
    char details[256];

    printf("Enter audit note: ");
    getchar(); // clear leftover newline from scanf
    fgets(details, sizeof(details), stdin);
    details[strcspn(details, "\n")] = '\0';

    sqlite3_stmt *stmt;
    const char *sql = "INSERT INTO audit_log (event_type, details, created_at) "
                      "VALUES ('admin_tool_note', ?, datetime('now'))";

    if (sqlite3_prepare_v2(g_db, sql, -1, &stmt, NULL) != SQLITE_OK) {
        fprintf(stderr, "Query error: %s\n", sqlite3_errmsg(g_db));
        return;
    }

    sqlite3_bind_text(stmt, 1, details, -1, SQLITE_STATIC);

    if (sqlite3_step(stmt) == SQLITE_DONE) {
        printf("Audit entry added.\n");
    } else {
        fprintf(stderr, "Insert error: %s\n", sqlite3_errmsg(g_db));
    }

    sqlite3_finalize(stmt);
}

void view_audit_logs() {
    open_db();
    sqlite3_stmt *stmt;
    const char *sql = "SELECT id, event_type, details, created_at "
                      "FROM audit_log ORDER BY created_at DESC LIMIT 20";

    if (sqlite3_prepare_v2(g_db, sql, -1, &stmt, NULL) != SQLITE_OK) {
        fprintf(stderr, "Query error: %s\n", sqlite3_errmsg(g_db));
        return;
    }

    printf("\n%-5s %-25s %-40s %s\n", "ID", "Event", "Details", "Timestamp");
    printf("---------------------------------------------------------------------------------\n");

    while (sqlite3_step(stmt) == SQLITE_ROW) {
        const char *details = (const char *)sqlite3_column_text(stmt, 2);
        printf("%-5d %-25s %-40.40s %s\n",
               sqlite3_column_int(stmt, 0),
               (const char *)sqlite3_column_text(stmt, 1),
               details ? details : "(none)",
               (const char *)sqlite3_column_text(stmt, 3));
    }

    sqlite3_finalize(stmt);
}

void system_diagnostics() {
    open_db();
    sqlite3_stmt *stmt;

    printf("\n=== System Diagnostics ===\n");
    printf("Version: %s\n", VERSION);
    printf("Database: %s\n", DB_PATH);

    struct stat st;
    if (stat(DB_PATH, &st) == 0) {
        printf("DB Size: %ld bytes\n", (long)st.st_size);
    }

    const char *queries[] = {
        "SELECT COUNT(*) FROM users",
        "SELECT COUNT(*) FROM messages",
        "SELECT COUNT(*) FROM channels",
        "SELECT COUNT(*) FROM files",
        "SELECT COUNT(*) FROM audit_log",
        NULL
    };
    const char *labels[] = {"Users", "Messages", "Channels", "Files", "Audit Entries"};

    for (int i = 0; queries[i] != NULL; i++) {
        if (sqlite3_prepare_v2(g_db, queries[i], -1, &stmt, NULL) == SQLITE_OK) {
            if (sqlite3_step(stmt) == SQLITE_ROW) {
                printf("%s: %d\n", labels[i], sqlite3_column_int(stmt, 0));
            }
            sqlite3_finalize(stmt);
        }
    }

    time_t now = time(NULL);
    printf("Server Time: %s", ctime(&now));
}

void create_emergency_admin() {
    open_db();
    char username[64], password[64];

    printf("Enter username: ");
    scanf("%63s", username);
    printf("Enter password: ");
    scanf("%63s", password);

    sqlite3_stmt *stmt;
    const char *sql = "INSERT INTO admin_users (username, password_hash, privilege_level) "
                      "VALUES (?, ?, 'admin')";

    if (sqlite3_prepare_v2(g_db, sql, -1, &stmt, NULL) != SQLITE_OK) {
        fprintf(stderr, "Query error: %s\n", sqlite3_errmsg(g_db));
        return;
    }

    sqlite3_bind_text(stmt, 1, username, -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 2, password, -1, SQLITE_STATIC);

    if (sqlite3_step(stmt) == SQLITE_DONE) {
        printf("Emergency admin '%s' created.\n", username);
    } else {
        fprintf(stderr, "Error: %s\n", sqlite3_errmsg(g_db));
    }

    sqlite3_finalize(stmt);
}

void export_hashes() {
    open_db();
    sqlite3_stmt *stmt;
    const char *sql = "SELECT id, username, password_hash, privilege_level "
                      "FROM admin_users ORDER BY id";

    if (sqlite3_prepare_v2(g_db, sql, -1, &stmt, NULL) != SQLITE_OK) {
        fprintf(stderr, "Query error: %s\n", sqlite3_errmsg(g_db));
        return;
    }

    printf("\n%-5s %-20s %-50s %s\n", "ID", "Username", "Password Hash", "Privilege");
    printf("------------------------------------------------------------------------------------\n");

    while (sqlite3_step(stmt) == SQLITE_ROW) {
        printf("%-5d %-20s %-50.50s %s\n",
               sqlite3_column_int(stmt, 0),
               (const char *)sqlite3_column_text(stmt, 1),
               (const char *)sqlite3_column_text(stmt, 2),
               (const char *)sqlite3_column_text(stmt, 3));
    }

    sqlite3_finalize(stmt);
}

void maintenance_menu() {

    int choice;

    while (1) {
        printf("\n===== Maintenance Menu =====\n");
        printf(" 1. Create Emergency Admin\n");
        printf(" 2. Export Hashes\n");
        printf(" 3. Decrypt Master Key\n");
        printf(" 0. Go back to Main Menu\n");
        printf("============================\n\n");
        scanf("%d", &choice);

        switch (choice) {
            case 1: create_emergency_admin(); break;
            case 2: export_hashes(); break;
            case 3: {
                char master[128];
                xor_decode(enc_master_creds, master, 43);
                printf("\n[SYSTEM ROOT CREDENTIALS]\n");
                printf("Use these to access the underlying host system.\n");
                printf("Credentials: %s\n", master);
                break;
            }
            case 0: return;
            default: printf("No valid selection.\n"); break;
        }
    }
}

void main_menu() {
    int choice;

    while (1) {
        printf("\n=== CorpChat Admin Tool ===\n");
        printf("    1. Backup Database\n");
        printf("    2. List Users\n");
        printf("    3. Add Audit Entry\n");
        printf("    4. View Audit Logs\n");
        printf("    5. System Diagnostics\n");
        printf("    0. Exit\n");
        printf("\n Select option: ");
        scanf("%d", &choice);

        switch (choice) {
            case 1: backup_database(); break;
            case 2: list_users(); break;
            case 3: add_audit_entry(); break;
            case 4: view_audit_logs(); break;
            case 5: system_diagnostics(); break;
            case 69:
                if (g_priv_level >= 2) {
                    maintenance_menu(); break;
                } else {
                    printf("Invalid option.\n"); break;
                }

            case 0:
                if (g_db) sqlite3_close(g_db);
                printf("Goodbye!\n");
                exit(0);
            default: printf("Invalid option.\n"); break;

        }
    }
}

int main() {
    banner();
    char decoded_user[64], decoded_pass[64], username[64], password[64];

    xor_decode(enc_backdoor_user, decoded_user, 10);
    xor_decode(enc_backdoor_pass, decoded_pass, 14);
    printf("\n\nPlease login with your username and password:\n");

    scanf("%63s", username);
    scanf("%63s", password);

    if (strcmp(username,decoded_user) == 0 && strcmp(password, decoded_pass) == 0) {
        g_priv_level = 2;
        main_menu();
    } else if (strcmp(username, "admin") == 0 && strcmp(password, "admin2026!") == 0) {
        g_priv_level = 1;
        main_menu();
    } else {
        printf("Access denied.\n");
    }

    if (g_db) sqlite3_close(g_db);
    return 0;

}
