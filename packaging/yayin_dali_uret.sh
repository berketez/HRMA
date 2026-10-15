#!/usr/bin/env bash
# yayin_dali_uret.sh — docs'suz YAYIN DALI üretir (Berke kuralı 15 Eyl 2026: iç dokümanlar push'lanmaz).
#
# Varsayılan: KURU KOŞU (rapor yazar, dal üretmez). Dal üretmek için --uret.
#   packaging/yayin_dali_uret.sh                 # rapor: hangi yollar düşer, kaç dosya, okuyan test var mı
#   packaging/yayin_dali_uret.sh --uret          # yayin/<sürüm> dalını üretir (push ETMEZ)
#   HARIC="docs/scofield docs/arastirma docs/tasarim" packaging/yayin_dali_uret.sh   # dışlama listesini değiştir
#
# Yöntem (tek commit / "kare"): origin/main'in ÜSTÜNE, main ağacının dışlanan yollar çıkarılmış hâlini
# TEK commit olarak koyar. Böylece (a) dışlanan içerik push geçmişine hiç girmez, (b) dal origin/main'den
# ileri-sarılabilir (force push gerekmez), (c) main'e dokunulmaz. Bedel: aradaki yerel commit geçmişi
# GitHub'da tek commit olarak görünür (git filter-repo kurulu değil; kurulursa --filtre kipi eklenir).
set -euo pipefail
KOK="$(git rev-parse --show-toplevel)"; cd "$KOK"
SURUM="$(python3 -c "import re;print(re.search(r'__version__\s*=\s*\"([^\"]+)\"',open('hrma/__init__.py').read()).group(1))")"
HARIC="${HARIC:-docs/scofield docs/arastirma docs/tasarim docs/kabul}"
TABAN="${TABAN:-origin/main}"; KAYNAK="${KAYNAK:-main}"; DAL="yayin/${SURUM}"
URET=0; [ "${1:-}" = "--uret" ] && URET=1

echo "sürüm: $SURUM | kaynak: $KAYNAK ($(git rev-parse --short "$KAYNAK")) | taban: $TABAN ($(git rev-parse --short "$TABAN")) | dal: $DAL"
git merge-base --is-ancestor "$TABAN" "$KAYNAK" && echo "taban kaynağın atası: EVET (ileri-sarım mümkün)" || { echo "taban kaynağın atası DEĞİL — durduruldu"; exit 2; }
echo "dışlanan yollar: $HARIC"
toplam=0
for y in $HARIC; do n=$(git ls-tree -r --name-only "$KAYNAK" -- "$y" | wc -l | tr -d ' '); echo "  $y: $n dosya"; toplam=$((toplam+n)); done
kalan=$(( $(git ls-tree -r --name-only "$KAYNAK" | wc -l | tr -d ' ') - toplam ))
echo "düşen: $toplam dosya | kalan: $kalan dosya"
# ÖLÇÜLDÜ (16 Eyl 2026): buradaki eski dedektör YALANCI GÜVEN veriyordu — üç test
# dosyası bildiriyordu, gerçekte 403 test dosyası bu yolları anıyor ve en az biri
# İÇE AKTARMA anında okuyup pytest'in TOPLAMA aşamasını düşürüyor
# (tests/test_d23_bekci_cevirisi_a1.py -> docs/scofield/raw/OH/D31/fix34/a/post_uclari.json).
# İki kusuru vardı:
#   1. Yol süzgeci 'tests/*.py' 'tests/cfd/*.py' idi; tests/fea/ ve tests/support/
#      hiç taranmıyordu.
#   2. Deseni okuma çağrısının AYNI SATIRDA olmasını şart koşuyordu; yol bir
#      sabite atanıp (KANIT = os.path.join(KOK, '...')) başka satırda okunduğunda
#      göremiyordu — depodaki baskın kalıp tam olarak budur.
# Yeni dedektör yol dizesini ANDIĞI için sayar (yalancı pozitif kabul edilir,
# yalancı negatif edilmez) ve dizeleri gerçek dosya/dizine çözerek kaç dosyanın
# taşınması gerektiğini de söyler.
echo "dışlanan yolları ANAN testler (yorum/docstring dahil; ANMAK okumak değildir — okuma aşağıda ayrıca ölçülür):"
python3 - "$KAYNAK" $HARIC <<'PY'
import re, subprocess, sys, os
kaynak, haric = sys.argv[1], sys.argv[2:]
kalip = '|'.join(re.escape(h) for h in haric)
desen = re.compile(r"['\"]((?:%s)[^'\"]*)['\"]" % kalip)
dosyalar = subprocess.run(['git', 'grep', '-l', '-E', kalip, kaynak, '--', 'tests/'],
                          capture_output=True, text=True).stdout.split()
# Kapının kendi uygulaması dışlanan dizinleri TANIMLAR (HARIC kümesi); onu
# saymak 'docs/scofield' kökünü "anılan kanıt" diye ikinci kez ekler.
kapinin_kendisi = {'tests/support/kanit.py', 'tests/support/kanit_tarayici.py'}
dosyalar = [d for d in dosyalar
            if (d.split(':', 1)[1] if ':' in d else d) not in kapinin_kendisi]
yollar = {}
for d in dosyalar:
    ad = d.split(':', 1)[1] if ':' in d else d
    ham = subprocess.run(['git', 'show', '%s:%s' % (kaynak, ad)],
                         capture_output=True, text=True).stdout
    for m in desen.finditer(ham):
        yollar.setdefault(m.group(1), set()).add(ad)
print('  anan test dosyasi: %d | ayrik yol dizesi: %d' % (len(dosyalar), len(yollar)))
toplam_dosya = toplam_bayt = 0
for y in sorted(yollar):
    if os.path.isfile(y):
        toplam_dosya += 1; toplam_bayt += os.path.getsize(y)
    elif os.path.isdir(y):
        for kok, _, adlar in os.walk(y):
            for a in adlar:
                t = os.path.join(kok, a)
                toplam_dosya += 1; toplam_bayt += os.path.getsize(t)
print('  bu dizelerin cozdugu kanit dosyasi: %d (%.0f MB)' % (toplam_dosya, toplam_bayt/1e6))
print('  EN GENIS dizeler (tasima maliyetini bunlar belirler):')
genis = []
for y in yollar:
    n = 1 if os.path.isfile(y) else (sum(len(a) for _, _, a in os.walk(y)) if os.path.isdir(y) else 0)
    genis.append((n, y, len(yollar[y])))
for n, y, k in sorted(genis, reverse=True)[:8]:
    print('    %7d dosya  %-56s (%d test)' % (n, y[:56], k))
PY
# ÖH D36 kanit-atlama (23 Eyl 2026): anmak okumak değildir. Yayın dalında
# kırmızıya dönen yalnız ÇALIŞMA ANINDA okumadır; test kodu kanıtı
# tests/support/kanit.py kapısından (kanit_gerekli / kanit_cikti) okur ve kanıt
# yoksa gerekçeli atlar. Aşağıdaki ölçüm bekçiyle (tests/test_kanit_atlama_kapisi.py)
# AYNI tarayıcıyı, KAYNAK ağacındaki sürümüyle koşar: sıfırdan büyükse yayın dalı
# CI'da FileNotFoundError / toplama düşmesi verir.
echo "dışlanan yolları kapı DIŞINDA OKUYAN testler (tests/support/kanit_tarayici.py; 0 olmalı):"
python3 - "$KAYNAK" <<'PY'
import subprocess, sys, types
kaynak = sys.argv[1]
def goster(ad):
    return subprocess.run(['git', 'show', '%s:%s' % (kaynak, ad)],
                          capture_output=True, text=True)
t = goster('tests/support/kanit_tarayici.py')
if t.returncode != 0:
    print('  ÖLÇÜLEMEDİ: %s ağacında tests/support/kanit_tarayici.py yok '
          '(kapı öncesi ağaç) — anan dosyaların okuyup okumadığı bilinmiyor' % kaynak)
    sys.exit(0)
mod = types.ModuleType('kanit_tarayici')
sys.modules['kanit_tarayici'] = mod
exec(compile(t.stdout, 'kanit_tarayici.py', 'exec'), mod.__dict__)
kapinin_kendisi = {'tests/support/kanit.py', 'tests/support/kanit_tarayici.py'}
adlar = subprocess.run(['git', 'ls-tree', '-r', '--name-only', kaynak, '--', 'tests/'],
                       capture_output=True, text=True).stdout.split()
kaynaklar = {ad: goster(ad).stdout for ad in adlar
             if ad.endswith('.py') and ad not in kapinin_kendisi}
# Modüller arası: bir test modülünün kanıt sabitini ithal eden modül de sayılır.
tarama = (mod.tara_agac(kaynaklar) if hasattr(mod, 'tara_agac')
          else {ad: mod.tara(k) for ad, k in kaynaklar.items()})
ihlal, cagri, kapili = [], 0, 0
for ad, s in sorted(tarama.items()):
    ihlal += ['%s:%d: %s' % (ad, i.satir, i.ifade) for i in s.ihlaller]
    cagri += len(s.kapi_cagrilari)
    kapili += bool(s.kapi_cagrilari)
print('  kapı DIŞINDA okuma: %d yer / %d dosya'
      % (len(ihlal), len({x.split(':', 1)[0] for x in ihlal})))
print("  kapıdan geçen okuma: %d çağrı / %d dosya (docs'suz dalda bu düğümler gerekçeyle atlanır)"
      % (cagri, kapili))
for x in ihlal[:20]:
    print('    ' + x[:150])
if len(ihlal) > 20:
    print('    ... %d yer daha' % (len(ihlal) - 20))
PY
echo "dışlanan yolları OKUYAN ürün/araç kodu (docstring anmaları hariç):"
for y in $HARIC; do git grep -n -E "(open\(|read_text|json\.load|Path\().*$y" "$KAYNAK" -- 'hrma/*.py' 'tools/*.py' 'packaging/*' '.github/*' | sed 's/^[^:]*://' | cut -c1-140 || true; done
[ "$URET" = 1 ] || { echo "KURU KOŞU bitti (dal üretilmedi; üretmek için --uret)"; exit 0; }

# --- üretim: dizin ağacı = kaynak ağacı − dışlananlar; tek commit, ebeveyn = taban
[ -z "$(git status --porcelain)" ] || { echo "çalışma ağacı temiz değil — durduruldu"; exit 3; }
export GIT_INDEX_FILE="$(mktemp -t yayin-index)"; rm -f "$GIT_INDEX_FILE"
git read-tree "$KAYNAK"
for y in $HARIC; do git rm -r -q --cached -- "$y" 2>/dev/null || true; done
AGAC=$(git write-tree)
MESAJ="HRMA v${SURUM} yayın (docs iç dokümanları hariç: ${HARIC}) — kaynak ${KAYNAK}@$(git rev-parse --short "$KAYNAK")"
COMMIT=$(printf '%s\n' "$MESAJ" | git commit-tree "$AGAC" -p "$TABAN")
unset GIT_INDEX_FILE
git branch -f "$DAL" "$COMMIT"
echo "ÜRETİLDİ: $DAL = $(git rev-parse --short "$COMMIT") (ebeveyn $(git rev-parse --short "$TABAN")); push ETMEDİ."
echo "doğrulama: git diff --stat $KAYNAK $DAL -- . ':!docs' | tail -1  (boş olmalı) ; git ls-tree -d --name-only $DAL docs/"
echo "push (Berke onayıyla): git push origin $DAL:main"
