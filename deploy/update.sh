#!/bin/sh
# Güncelleme ve geri alma (sunucuda root): /srv/forum/deploy/update.sh <etiket ya da commit>
# Önce yedek alır, sonra kodu o sürüme geçirir, denetler, veritabanını günceller ve uygulamayı yeniden başlatır.
# Bütün adımlar main() içinde: git bu dosyayı değiştirse de kabuk en baştan okuduğu sürümü çalıştırır.
set -eu

main() {
	ref=${1:?Kullanım: update.sh <etiket ya da commit>}
	cd /srv/forum
	app() { sudo -u forum "$@"; }
	app deploy/backup.sh
	app git fetch --tags origin
	app git checkout --detach "$ref"
	app .venv/bin/python -m pip install --quiet -r requirements.txt
	app .venv/bin/python manage.py check --deploy --fail-level WARNING
	app .venv/bin/python manage.py migrate --noinput
	app .venv/bin/python manage.py collectstatic --noinput --verbosity 0
	systemctl restart forum
	echo "Yayında: $(app git describe --tags --always)"
}

main "$@"
