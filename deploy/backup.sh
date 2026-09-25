#!/bin/sh
# Veritabanı yedeği (forum kullanıcısıyla). KEEP_DAYS günden eski yedekler silinir (KVKK metnindeki süre).
set -eu
DIR=/var/backups/forum
KEEP_DAYS=30
umask 077  # yedekte kişisel veri var: yalnızca forum kullanıcısı okur
file="$DIR/forum-$(date +%Y%m%d-%H%M%S).dump"
pg_dump --format=custom --file="$file.tmp" forum
mv "$file.tmp" "$file"  # yarım kalan yedek, tam yedek gibi görünmesin
find "$DIR" -name 'forum-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$file"
