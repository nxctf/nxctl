#include <stdio.h>

struct user {
    char username[16];
    int is_admin;
};

int main() {
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stdin, NULL, _IONBF, 0);

    struct user u;
    u.is_admin = 0;

    printf("Masukkan username: ");
    gets(u.username);

    if (u.is_admin == 1) {
        puts("Selamat! Kamu admin.");
        puts("Flag: FGTE{REDECTED}");
    } else {
        puts("Akses ditolak. Kamu bukan admin.");
    }
}
