# CTFS Back Bash Completion

Completion script untuk CLI `app.py`.

## Instalasi

```bash
chmod +x completion/install.sh completion/uninstall.sh completion/ctfs-back-completion.bash
./completion/install.sh
```

## Penggunaan

```bash
./app.py <TAB>
./app.py inspect <TAB>
./app.py enable <TAB>
./app.py export <TAB>
./app.py clean <TAB>
```

## Uninstall

```bash
./completion/uninstall.sh
```

## Catatan

- Completion ini mengambil daftar challenge dari output `./app.py list`.
- Nama challenge yang belum ada di database tidak akan muncul sampai kamu jalankan sync/list yang menghasilkan data.
