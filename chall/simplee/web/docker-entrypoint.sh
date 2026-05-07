#!/usr/bin/env bash
set -euo pipefail

# Jika FLAG ada, tulis ke /flag.txt tetapi JANGAN ubah permission/ownership.
# Ini akan membuat file baru atau menimpa file yang ada dengan default owner/perm.
echo ${FLAG} > /flag.txt
echo ${FLAG_DECOY1} > /flag.txt
echo ${FLAG_DECOY2} > /home/aria/flag.txt
echo ${FLAG_DECOY2} > /home/aria/.ssh/id_rsa

cat << EOF > /home/aria/.bash_history
echo ${FLAG} > /flag.txt
echo ${FLAG_DECOY1} > /flag.txt
echo ${FLAG_DECOY2} > /home/aria/flag.txt
echo ${FLAG_DECOY2} > /home/aria/.ssh/id_rsa
EOF

# jalankan default command (apache)
exec "$@"
