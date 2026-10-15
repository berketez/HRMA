# -*- coding: utf-8 -*-
"""ÖH Dalga-23 · kulvar **bekci-cevirisi**, aşama 1 — onarımların bekçileri.

Üç kalem, üç bekçi ailesi:

* **P13B3-11** (D22 devri, kalan yarı) — künye YERELLİĞİ. D22 envantere bir
  tavan koydu ama tavan ÖLÇÜLEN sayıdan 11 birim YUKARIDAYDI (136 ⟷ 125):
  o yastık kadar çapa sessizce künyesizleşebilirdi. Ayrıca ölçüm iki kör
  noktası vardı: (a) yalnız ``#`` yorumu künye sayılıyordu — çapayı
  ÇEVRELEYEN test/sınıf docstring'inde duran gerçek dayanak (NASA SP-106,
  Wylie & Streeter, ISO…) "künyesiz" diye sayılıyordu; (b) metinle
  bulunamayan ("taşınmış") çapalar ölçümün DIŞINDA kalıyordu, yani bir
  çapayı bozmak onu sayımdan düşürüyordu.
* **P15B3-10** — ``tests/support/shake.py`` sarsım kapsamı: kampanyanın en
  verimli aracı ürünün POST uçlarının yalnız BİRİNDE koşuyor. Kapsam elle
  tutulan bir listedir ve çürümesinin mekanik bekçisi yoktu.
* **OH-Z5-02** — ``test_field_wiring_layer_b::
  test_no_fabricated_constant_outputs`` taban kırmızısı: 14 sabit yaprak.
  Hiçbiri ``tests/`` sahasında değil; bu dosya yaprakların KULVAR
  dağılımını belgeye bağlar ve borcun "im ekleyerek" kapatılmasını
  mekanik olarak yasaklar.

Bu kulvar ÜRÜN KODUNA DOKUNMAZ: ``hrma/`` ağacı bu aşamada değişmedi.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]

# D22'nin ölçüm gövdesi TEK KAYNAKTIR: burada yeniden yazılmaz, içe alınır.
from tests.test_d22_bekci_cevirisi_a1 import (      # noqa: E402
    PARMAK_IZI_ENVANTERI,
    YERELSIZ_KUNYE_TAVANI,
    _kunye_yerelligi,
)


def _oku(bagil: str) -> str:
    return (KOK / bagil).read_text(encoding='utf-8')


# ===========================================================================
# P13B3-11 — künye yerelliği: ölçüt düzeltmesi + yastıksız tavan
# ===========================================================================

#: KAYNAK DAMGASI — bir metnin "dayanak" sayılması için taşıması gereken iz.
#: Düzyazı künye DEĞİLDİR ("1T: ilk kök 1.8412" bir dayanak değil, sayının
#: tekrarıdır); damga sayının NEREDEN geldiğini söyleyen bir ada, belgeye,
#: standarda ya da ölçüme işaret etmelidir. Tek kaynak: ölçüm betiği
#: ``docs/scofield/raw/OH/D23/bekci-cevirisi/a1/olcum.py`` aynı listeyi
#: kullanır (kanıt dosyaları bu ölçütle üretildi).
KAYNAK_DAMGASI = re.compile(
    r'NASA|SP-?\d|NIST|ASME|AIAA|ISO\s?\d{3}|MIL-|RP-1|CEA|DIN\s?\d'
    r'|Sutton|Biblarz|Abramowitz|Stegun|Lefebvre|Barlow|Humble|Huzel'
    r'|Zucrow|Anderson|White|Moody|Colebrook|Blasius|Summerfield'
    r'|Tablo|Table|Böl\.|Bölüm|Chap|Chapter|Eq\.|Denk\.|Ek\s?[A-Z]'
    r'|docs/|\.md\b|literatür|literature'
    r'|ÖLÇÜLDÜ|ÖLÇÜLDU|OLCULDU|ölçüldü|olculdu|measured'
    r'|elle hesap|hand calc|kapalı form|closed form|analitik|analytic',
    re.IGNORECASE)

#: ÖLÇÜLDÜ (ef527ae tabanında 122; bu aşamada 10 çapaya yerel künye
#: yazıldıktan sonra 112). D22 tavanı 136 idi, yani **14 birim yastık**
#: taşıyordu. Bu sabit ölçülen sayının KENDİSİDİR.
A_TAVANI = 112

#: ÖLÇÜLDÜ: 112'nin 66'sının ne yerel ``#`` yorumu VAR ne de çevreleyen
#: def/class docstring'inde kaynak damgası. GERÇEK yerel künye borcu budur;
#: kalan 46'sının dayanağı çapanın kendi kapsamında yazılıdır.
B_TAVANI = 66

#: ÖLÇÜLDÜ: envanterin 14 çapası metinle bulunamıyor (kardeş kulvarlar
#: satırı düzenlemiş ya da test yeniden yazılmış). Bu sayı BÜYÜYEMEZ:
#: büyümesi, ölçümün körleşerek "iyileşiyor" görünmesi demektir.
TASINMIS_TAVANI = 14

#: D22 dersi: tavanla ölçülen sayı arasındaki yastık 11 birime çıkmıştı ve
#: kimse görmedi. Yastık artık ölçülüyor; 3 birimi aşarsa bir sonraki
#: dalgada ödenmek zorunda.
TAVAN_YASTIK_TOLERANSI = 3


def _kapsayan_docstringler(kaynak: str, satir_no: int):
    """``satir_no`` (1 tabanlı) satırını kapsayan def/class docstring'leri.

    Modül docstring'i BİLEREK dışarıda: 800 satır yukarıdaki bir açıklama
    "yerel" değildir — kalemin adı zaten *yerellik*tir.
    """
    try:
        agac = ast.parse(kaynak)
    except SyntaxError:                                  # pragma: no cover
        return []
    bulunan = []

    def gez(dugum):
        for cocuk in ast.iter_child_nodes(dugum):
            if isinstance(cocuk, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                if cocuk.lineno <= satir_no <= getattr(
                        cocuk, 'end_lineno', cocuk.lineno):
                    d = ast.get_docstring(cocuk)
                    if d:
                        bulunan.append(d)
                    gez(cocuk)
            else:
                gez(cocuk)

    gez(agac)
    return bulunan


def _kunye_yerelligi_b():
    """B ölçütü: ne yerel ``#`` yorumu ne de kapsam docstring'inde damga."""
    ham = json.loads(_oku(kanit_gerekli(PARMAK_IZI_ENVANTERI)))
    onbellek, borc = {}, []
    for k in ham:
        bagil = k['file']
        if bagil not in onbellek:
            yol = KOK / bagil
            onbellek[bagil] = (yol.read_text(encoding='utf-8')
                               if yol.exists() else None)
        metin = onbellek[bagil]
        if metin is None:
            continue
        satirlar = metin.splitlines()
        hedef = k['src_line'].strip()
        indisler = [i for i, s in enumerate(satirlar) if s.strip() == hedef]
        if not indisler:
            continue
        i = indisler[0]
        if re.search(r'#\s*\S', '\n'.join(satirlar[max(0, i - 2):i + 1])):
            continue
        docs = _kapsayan_docstringler(metin, i + 1)
        if not any(KAYNAK_DAMGASI.search(d) for d in docs):
            borc.append('%s:%d' % (bagil, i + 1))
    return borc


class TestP13B311KunyeYerelligiKalanYari:
    """P13B3-11'in kalan yarısı: yastığı sil, kör noktaları kapat."""

    def test_a_olcutu_tavani_yastiksiz(self):
        """``#`` yorumu ölçütü — tavan ÖLÇÜLEN sayının kendisi.

        TERS MUTASYON: bir çapanın yerel künyesi silinirse sayı 112'yi
        aşar ve bu test kırmızı olur.
        """
        _, _, yerelsiz = _kunye_yerelligi()
        assert len(yerelsiz) <= A_TAVANI, (
            'yerel künyesiz çapa sayısı tavanı aştı: %d > %d — yeni bir '
            'çapa künyesiz eklendi ya da mevcut bir künye silindi'
            % (len(yerelsiz), A_TAVANI))

    def test_a_tavani_yastik_biriktirmiyor(self):
        """Tavan ile ölçüm arasındaki yastık büyüyemez.

        D22'de yastık 11 birimdi (tavan 136, ölçüm 125) ve tek yönlü tavan
        bunu SESSİZ geçiyordu: o 11 çapa istendiği gibi künyesizleşebilirdi.
        """
        _, _, yerelsiz = _kunye_yerelligi()
        yastik = A_TAVANI - len(yerelsiz)
        assert yastik <= TAVAN_YASTIK_TOLERANSI, (
            'tavan ölçülen sayıdan %d birim yukarıda (%d ⟷ %d): borç ödendi '
            'ama tavan indirilmedi. A_TAVANI bu satırda ölçülen değere '
            'çekilmeli ve gerekçesi yazılmalı.'
            % (yastik, A_TAVANI, len(yerelsiz)))

    def test_d22_tavani_artik_yastiksiz(self):
        """D22'nin 136'lık tavanı bu aşamada ölçülen değere çekildi."""
        assert YERELSIZ_KUNYE_TAVANI == A_TAVANI, (
            'D22 tavanı (%d) ile D23 ölçümü (%d) ayrıştı: iki tavan iki '
            'ayrı gerçek anlatıyor, tek kaynak bozuldu'
            % (YERELSIZ_KUNYE_TAVANI, A_TAVANI))

    def test_b_olcutu_gercek_borcu_sayiyor(self):
        """Çapanın KENDİ kapsamında dayanak var mı — ölçüt farkının ölçümü.

        Kalem "künyelerin %71,8'i dayanak olarak kullanılamaz" diyordu;
        H1 kendi ölçütüyle %9,8 buluyordu. Fark ölçüldü: 112 çapanın
        46'sının dayanağı çevreleyen def/class docstring'inde YAZILI
        (NASA SP-106, Wylie & Streeter, ISO…), 66'sının hiçbir yerde
        yerel değil. Asıl hüküm ayakta ama sayısı 66'dır, 112 değil.
        """
        borc = _kunye_yerelligi_b()
        assert len(borc) <= B_TAVANI, (
            'kapsam docstring\'inde de dayanağı olmayan çapa sayısı tavanı '
            'aştı: %d > %d. İlk 15:\n  %s'
            % (len(borc), B_TAVANI, '\n  '.join(sorted(borc)[:15])))

    def test_b_tavani_yastik_biriktirmiyor(self):
        borc = _kunye_yerelligi_b()
        yastik = B_TAVANI - len(borc)
        assert yastik <= TAVAN_YASTIK_TOLERANSI, (
            'B tavanı ölçülen sayıdan %d birim yukarıda (%d ⟷ %d): '
            'B_TAVANI indirilmeli' % (yastik, B_TAVANI, len(borc)))

    def test_tasinmis_capa_sayisi_buyumuyor(self):
        """Ölçümün kör noktası KAPALI kalmalı.

        "Taşınmış" çapa (metinle bulunamayan) sayımdan düşer. D22 ölçümü
        bunu saymıyordu, yani bir çapayı bozmak onu künye borcundan
        ÇIKARIYORDU — envanteri gevşetmenin sessiz yolu.
        """
        _, tasinmis, _ = _kunye_yerelligi()
        assert tasinmis <= TASINMIS_TAVANI, (
            'metinle bulunamayan çapa sayısı büyüdü: %d > %d. Envanter '
            '(%s) tazelenmeli — ölçüm körleşiyor ve sayım YANLIŞ '
            'iyileşiyor.' % (tasinmis, TASINMIS_TAVANI, PARMAK_IZI_ENVANTERI))

    def test_b_olcutu_a_olcutunun_alt_kumesi(self):
        """B borcu A borcunun ALT KÜMESİDİR — ölçüt tutarlılığı.

        B ölçütü A'yı gevşetmez, DARALTIR: yerel ``#`` yorumu olan bir
        çapa iki ölçütte de temizdir. Bu iddia, B'nin bir kaçış kapısına
        dönüşmesini engeller.
        """
        borc_b = {x.split(':')[0] + ':' + x.split(':')[1]
                  for x in _kunye_yerelligi_b()}
        _, _, yerelsiz_a = _kunye_yerelligi()
        # A listesi 'dosya:src_line' biçiminde; dosya kümesi karşılaştırılır.
        dosyalar_a = {x.split(':')[0] for x in yerelsiz_a}
        dosyalar_b = {x.split(':')[0] for x in borc_b}
        assert dosyalar_b <= dosyalar_a, (
            'B ölçütü A\'nın görmediği dosya üretti: %s'
            % sorted(dosyalar_b - dosyalar_a))


# ===========================================================================
# P15B3-10 — sarsım kapsamı elle liste değil, ÖLÇÜLEN sayı
# ===========================================================================

#: ÖLÇÜLDÜ (ef527ae): ``hrma.app.url_map`` içinde POST kabul eden 80 kural.
#: Kalem 75 diyordu — sayı BÜYÜMÜŞ, yani kapsam açığı derinleşmiş.
#:
#: ÖH D31 fix-34a (14 Eylül 2026): SAYI TABANI KALDIRILDI, yerine KÜME
#: TABANI geldi — D27 fix-26a'nın XPASS envanterinde yaptığının aynısı.
#: Neden: elle yazılmış ``POST_UC_ADEDI = 80`` bir POST ucu silindiğinde
#: kırmızı verdi (ölçüm 79) ve "sayıyı bir azalt" en kolay yoldu; üstelik
#: sayı eşitliği "bir uç gitti, bir uç geldi" TAKASINI sessizce geçirirdi.
#: Taban artık ölçüm dosyasından türetilir ve ağaçla KÜME EŞİTLİĞİ aranır;
#: fark ADIYLA basılır. Bu bir gevşetme değil SIKILAŞTIRMADIR.
#:
#: ÖLÇÜLEN FARK (80 -> 79, tek uç): ``/api/analysis/thermal-protection``
#: ÖLÜ TAKMA YOLDU ve ``8f0cb411`` (ÖH D30 app-api-uc a1, OH-D29-13 /
#: P7B1-22) ile silindi; kardeş yol ``/api/thermal-protection`` YAŞIYOR
#: (``hrma/app.py`` içindeki söküm notu da yazılı). Yani POST kapsamı
#: DARALMADI: iki ada sahip tek uç tek ada indi. Statik AST sayımı bunu
#: bağımsız doğruladı (75 -> 74, tek fark aynı yol).
#:
#: TABAN DOSYASI — tek kaynak; elle yazılı tam sayı YOK.
POST_UC_TABANI_DOSYASI = 'docs/scofield/raw/OH/D31/fix34/a/post_uclari.json'


def _post_uc_tabani():
    """Ölçülen POST ucu kümesi. Dosya yoksa/bozuksa FAIL-CLOSED düşer."""
    ham = json.loads(_oku(kanit_gerekli(POST_UC_TABANI_DOSYASI)))
    uclar = ham.get('uclar')
    if not isinstance(uclar, list) or not uclar:
        raise AssertionError(
            'POST ucu tabanı okunamadı: %s içinde "uclar" listesi yok'
            % POST_UC_TABANI_DOSYASI)
    if len(set(uclar)) != len(uclar):
        raise AssertionError('POST ucu tabanında yinelenen kayıt var')
    return frozenset(uclar)


#: Kapsam iddialarının paydası: ELLE YAZILMAZ, kümenin boyudur.
POST_UC_ADEDI = len(_post_uc_tabani())

#: ÖLÇÜLDÜ: ``shake.run(...)`` çağrılarında geçen uç YOLU tek: ``/calculate``.
#: Kalem "3-4" diyordu; gerçek DAHA KÖTÜ (D21 ölçümü de 1 bulmuştu).
SARSILAN_UC_TABANI = 1

#: ÖLÇÜLDÜ: 8 çağrı yeri (test_d17_bekci_cevirisi_a1.py ×7,
#: test_field_wiring_layer_b.py ×1).
SHAKE_RUN_CAGRI_TABANI = 8

#: ÖLÇÜLDÜ: ``tests/`` ağacında yolu (parametreli uçlarda değişmez öneki)
#: HİÇ geçmeyen POST ucu YOK. Kalem 11 diyordu, D21 ölçümü 2 bulmuştu;
#: bugün 0 — kalemin bu yarısı ÇÜRÜDÜ ve bir daha çürümemeli.
GECMEYEN_UC_TAVANI = 0


def _post_uclari():
    if str(KOK) not in sys.path:
        sys.path.insert(0, str(KOK))
    from hrma.app import app                             # noqa: PLC0415
    return sorted({str(k.rule) for k in app.url_map.iter_rules()
                   if 'POST' in (k.methods or set())})


def _test_metinleri():
    return [(p, p.read_text(encoding='utf-8', errors='replace'))
            for p in sorted((KOK / 'tests').rglob('*.py'))]


def _sarsim_kapsami():
    """``shake.run`` çağrılarının ULAŞTIĞI uçlar ve çağrı yerleri."""
    sarsilan, cagri = set(), []
    for p, m in _test_metinleri():
        if 'shake.run' not in m:
            continue
        try:
            agac = ast.parse(m)
        except SyntaxError:                              # pragma: no cover
            continue
        for d in ast.walk(agac):
            if not isinstance(d, ast.Call):
                continue
            f = d.func
            if getattr(f, 'attr', None) != 'run':
                continue
            if getattr(getattr(f, 'value', None), 'id', '') != 'shake':
                continue
            cagri.append('%s:%d' % (p.relative_to(KOK), d.lineno))
            for arg in list(d.args) + [kw.value for kw in d.keywords]:
                if (isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and arg.value.startswith('/')):
                    sarsilan.add(arg.value)
    return sorted(sarsilan), sorted(cagri)


class TestP15B310SarsimKapsami:
    """Kapsam ELLE TUTULAN bir liste olmaktan çıkar, ölçülen sayı olur."""

    def test_post_uc_kumesi_beyanla_birebir(self):
        """Ürün POST ucu kazanır ya da kaybederse kapsam hükmü TAZELENMELİ.

        Kalemin sınıfı "elle-liste çürümesi"dir: 75 yazılmıştı, ölçüm 80
        buldu. ÖH D31 fix-34a bir adım daha ileri gitti: sayı eşitliği
        TAKASI (bir uç gitti, bir uç geldi) sessizce geçirir, küme
        eşitliği geçirmez ve farkı ADIYLA söyler. Taban ölçüm
        dosyasındadır; bu gövdede elle yazılı tam sayı YOKTUR.
        """
        uclar = set(_post_uclari())
        taban = _post_uc_tabani()
        eklenen = sorted(uclar - taban)
        silinen = sorted(taban - uclar)
        assert not eklenen and not silinen, (
            'POST ucu kümesi ölçülen tabandan AYRIŞTI.\n'
            '  EKLENEN (%d): %s\n  SİLİNEN (%d): %s\n'
            'Değişim bilinçliyse %s ölçümle (a/olcum_post.py) tazelensin '
            've hangi ucun neden gittiği/geldiği gerekçesiyle yazılsın; '
            'sessiz geçiş yok. Kapsam hükmü ve SARSILAN_UC_TABANI de aynı '
            'anda gözden geçirilir.'
            % (len(eklenen), eklenen, len(silinen), silinen,
               POST_UC_TABANI_DOSYASI))

    def test_sarsilan_uc_sayisi_kucululmuyor(self):
        """Sarsım kapsamı yalnız BÜYÜYEBİLİR (ratchet).

        TERS MUTASYON: tek ``shake.run`` çağrısındaki uç yolu değişkene
        alınırsa (yol literali kaybolursa) kapsam 0'a düşer ve bu test
        kırmızı olur.
        """
        sarsilan, _ = _sarsim_kapsami()
        assert len(sarsilan) >= SARSILAN_UC_TABANI, (
            'sarsım kapsamı küçüldü: %d < %d. Ulaşılan uçlar: %s'
            % (len(sarsilan), SARSILAN_UC_TABANI, sarsilan))

    def test_shake_run_cagri_yeri_kucululmuyor(self):
        _, cagri = _sarsim_kapsami()
        assert len(cagri) >= SHAKE_RUN_CAGRI_TABANI, (
            'shake.run çağrı yeri sayısı düştü: %d < %d — bir bekçi '
            'sessizce sökülmüş olabilir. Kalanlar: %s'
            % (len(cagri), SHAKE_RUN_CAGRI_TABANI, cagri))

    def test_hicbir_post_ucu_tests_agacinda_yabanci_degil(self):
        """Her POST ucunun ADI en az bir testte geçmeli (D21 ölçütü)."""
        uclar = _post_uclari()
        birlesik = '\n'.join(m for _, m in _test_metinleri())
        yabanci = []
        for u in uclar:
            onek = u.split('<', 1)[0].rstrip('/') if '<' in u else u
            kalip = re.escape(onek) + ('' if '<' in u else r'(?![\w/])')
            if not re.search(kalip, birlesik):
                yabanci.append(u)
        assert len(yabanci) <= GECMEYEN_UC_TAVANI, (
            'tests/ ağacında adı hiç geçmeyen POST ucu: %s' % yabanci)

    def test_kapsam_acigi_belgede_sayisiyla_duruyor(self):
        """Açık kapatılmadıysa BÜYÜKLÜĞÜ yazılı kalmalı (fail-closed beyan).

        Sarsım kapsamı bugün 80 ucun 1'i. Bu bir kusurdur ve kapatılması
        her uç için GEÇERLİ taban yük ister; o katalog ÖH D23'te altyapı
        kulvarında (P10B4-16, ``tests/support/uc_katalogu.py``) iniyor.
        Bu iddia, kapsamın "kapandı" sanılmasını engeller: kapsam gerçekten
        büyüdüğünde SARSILAN_UC_TABANI yükseltilir ve bu satır düşer.
        """
        sarsilan, _ = _sarsim_kapsami()
        assert len(sarsilan) < POST_UC_ADEDI, (
            'sarsım kapsamı tüm uçları kapsıyor görünüyor (%d/%d) — doğruysa '
            'harika: SARSILAN_UC_TABANI yükseltilip bu iddia kaldırılmalı'
            % (len(sarsilan), POST_UC_ADEDI))


# ===========================================================================
# OH-Z5-02 — sabit yaprak borcunun KULVAR dağılımı ve im yasağı
# ===========================================================================

Z5_ENVANTERI = ('docs/scofield/raw/OH/D23/bekci-cevirisi/a1/'
                'z5_02_yaprak_kulvar.json')

#: ÖLÇÜLDÜ (ef527ae, HRMA_DUMP_CONSTANTS): 14 sabit yaprak.
Z5_YAPRAK_ADEDI = 14

#: ÖH D25 / OH-Z5-02 — Katman B'nin sabit yaprak sayacının TABANDA
#: (cdf2106) ölçülen değeri 12'ydi; hibrit kulvarı yedisini yaprak-başına
#: sınıflandırdıktan sonra 5 kaldı (app-api bakiyesi). Eşik bu sayının
#: ÜSTÜNE çıkamaz. Ölçüm: docs/scofield/raw/OH/D25/hibrit/a1/
#: {once_dump, sonra_dump} ve rapor.md.
D25_OLCULEN_SABIT_YAPRAK = 5


def _z5_envanteri():
    return json.loads(_oku(kanit_gerekli(Z5_ENVANTERI)))


class TestOHZ502SabitYaprakEnvanteri:
    """Taban kırmızısının borcu ADIYLA ve SAHİBİYLE yazılı durur."""

    def test_envanter_olculen_yaprak_sayisiyla_uyusuyor(self):
        env = _z5_envanteri()
        assert env['olculen_adet'] == Z5_YAPRAK_ADEDI
        assert len(env['yapraklar']) == Z5_YAPRAK_ADEDI, (
            'envanter %d yaprak sayıyor ama %d kayıt taşıyor'
            % (Z5_YAPRAK_ADEDI, len(env['yapraklar'])))

    def test_her_yapragin_sahibi_ve_uretim_yeri_var(self):
        """Sahipsiz borç dağıtılamaz — fail-closed kayıt."""
        eksik = [y['yaprak'] for y in _z5_envanteri()['yapraklar']
                 if not y.get('kulvar') or not y.get('uretim')
                 or not y.get('hukum')]
        assert not eksik, 'sahibi/üretim yeri/hükmü yazılmamış yaprak: %s' % eksik

    def test_kulvar_dagilimi_yaprak_sayisini_tuketiyor(self):
        env = _z5_envanteri()
        assert sum(env['kulvar_dagilimi'].values()) == Z5_YAPRAK_ADEDI, (
            'kulvar dağılımı toplamı yaprak sayısını tutmuyor')

    def test_hicbir_borc_yapragi_mesru_sabit_imine_tasinmadi(self):
        """ÖK-22 mekanik hâli: borç "im ekleyerek" kapatılamaz.

        ``test_field_wiring_layer_b`` bu tehlikeyi metinle uyarıyordu
        ("im ekleyerek borç kapatma tam da bu dosyanın en çok korkması
        gereken hamleydi") ve alt sınırla savunuyordu. Alt sınır SAYIYI
        korur, YAPRAĞI korumaz: bir yaprak imlenip yerine yenisi doğarsa
        sayı sabit kalır. Bu iddia yaprakların KENDİSİNİ korur.
        """
        katman_b = _oku('tests/test_field_wiring_layer_b.py')
        # AST ile al: metinde ilk '\n)' arayan bir kesim, im listesinin
        # ARASINDAKİ yorum bloklarındaki parantezlere takılıp listeyi
        # erken bitiriyordu (ölçüldü: 172 satır / gerçek liste çok daha
        # uzun) — yani bekçi imlerin çoğunu HİÇ görmüyordu.
        agac = ast.parse(katman_b)
        im_blogu = None
        for d in agac.body:
            hedefler = (d.targets if isinstance(d, ast.Assign)
                        else [d.target] if isinstance(d, ast.AnnAssign)
                        else [])
            if any(getattr(t, 'id', '') == 'LEGITIMATE_CONSTANTS'
                   for t in hedefler):
                im_blogu = ast.get_source_segment(katman_b, d.value)
                break
        assert im_blogu, ('LEGITIMATE_CONSTANTS bulunamadı — im listesi '
                          'yeniden adlandırılmış olabilir')
        # ÇEVRİLDİ — ÖH D25 / OH-Z5-02 (hibrit a1), İKİ AYRI SEBEPLE.
        #
        # (1) EŞLEŞTİRME DELİĞİ KAPANDI. Eski hâl yaprağın YALNIZ son
        #     adını ve yalnız "'<ad>'" biçiminde arıyordu; YOL ÖNEKLİ bir
        #     im (ör. 'fastener_analysis.bolt_min_pitch_factor') bu
        #     aramaya HİÇ takılmıyordu. Yani bekçi, korumak için
        #     yazıldığı hamlenin en doğal biçimini göremiyordu. Artık
        #     imler AST'ten string sabit olarak toplanıyor ve Katman
        #     B'nin KENDİ kuralı uygulanıyor ("im, yaprak yolunun alt
        #     dizgisi mi?") — yani bu iddia gerçek bekçiyle aynı ölçüyü
        #     kullanıyor.
        #     İM LİSTESİ AST DÜĞÜMÜNDEN DEĞERLENDİRİLİR, dizgi taranmaz.
        #     İlk deneme ``ast.walk`` ile TÜM string sabitlerini toplamıştı
        #     ve YANLIŞ ALARM verdi (ölçüldü): listenin İÇİNDEKİ üretici
        #     ifadenin yardımcı literalleri de ime sayılıyor, bunlardan
        #     'pressure' app-api'nin borç yaprağı
        #     '.validation.injector_assessment.pressure_drop_ratio.band[0]'
        #     ile eşleşiyordu. Gerçek im sayısı 117, ham dizgi sayısı 107;
        #     ikisi AYNI KÜME DEĞİL. Artık tuple'ın kendisi değerlendirilip
        #     Katman B'nin kullandığı nesnenin BİREBİR aynısı taranıyor.
        #
        # (2) HÜKÜM-13 İSTİSNASI ADIYLA YAZILDI. D23'te ÖK-22 yürürlükteydi
        #     ve im eklemek YASAKTI; hüküm-13 (ÖH D25) bu yasağı OH-Z5-02
        #     için ŞARTA BAĞLI kaldırdı: yaprak YAYIMLANAN BİR MODEL EŞİĞİ
        #     ya da TANIM GEREĞİ bir özdeşlikse, künye adıyla gerekçeli im
        #     ONARIMDIR (sınıflandırmadır), borç gizleme değildir.
        #     Aşağıdaki yedi yaprak D25 hibrit a1'de tek tek ölçülüp
        #     sınıflandırıldı (ölçüm: docs/scofield/raw/OH/D25/hibrit/a1/
        #     {once,sonra}.json; öncül kilidi: tests/test_d25_hibrit_a1.py;
        #     ters-mutasyon: mutasyon.json). Liste DONDURULMUŞTUR: burada
        #     adı geçmeyen hiçbir yaprak imlenemez — kalan beş yaprak
        #     (app-api bakiyesi) bu iddiayla korunmaya DEVAM eder.
        HUKUM13_SINIFLANDIRILAN = frozenset((
            # tanım gereği özdeşlik: istasyonlar oda entropisinde çözülür
            '.motor.optimum_analysis.analysis.performance'
            '.thermodynamic_properties.isentropic_efficiency',
            # aramanın TANIM KÜMESİ; kelepçe stokiyometrik orana açılıyor
            '.motor.optimum_analysis.of_range_searched[0]',
            '.motor.optimum_analysis.of_range_searched[1]',
            # beyan edilen flanş pratiği (Taylor Forge / ASME VIII-1 Ek 2)
            '.motor.structural_analysis.fastener_analysis'
            '.bolt_min_pitch_factor',
            # MMPDS eğrisinin oda sıcaklığı referans ucu
            '.motor.structural_analysis.thermal_analysis.strength_derating'
            '.curve_min_temp_C',
            # çağıranın irtifa tarama ızgarasının son noktası
            '.motor.thrust_altitude_analysis.top_of_grid_altitude_m',
            # yayımlanan kapı eşiği (HYBRID_CF_CROSS_CHECK_TOL_PCT)
            '.motor.thrust_coefficient_cross_check.tolerance_percent',
            # --- ÖH D26 / app-api aşama-3 · APP-API BAKİYESİ ------------
            # Yukarıdaki not "kalan beş yaprak (app-api bakiyesi) bu
            # iddiayla korunmaya DEVAM eder" diyordu; app-api hükmünü
            # D26 a3'te verdi ve muafiyet AYNI commit'te büyütülüyor.
            # Ölçüm: docs/scofield/raw/OH/D26/app-api/a3/
            # {once_constants.txt, z5_yaprak_gecis.json, z5_sayac_gecis.json};
            # ters-mutasyon: aynı dizinde mutasyon.json (M6/M7).
            # Beş yaprağın DÖRDÜ imlendi; beşincisi
            # (``.input_warnings[0].params.submitted``) İMLENMEDİ —
            # ``shake._DECLARATION_ECHO`` sınıflandırmasıyla düştü, yani
            # bu listeye hiç girmiyor.
            #
            # yanıtın KENDİ ağacının ölçümü (app.py, ardışık iki satır);
            # geçiş ölçümü: solved_value_echo_count 6 -> 34 (aşırı-belirli
            # gövde), yani sayaç canlı — sarsım kümesi onu oynatmıyor
            '.inputs_not_used[0].submitted_value_echo_count',
            '.inputs_not_used[0].solved_value_echo_count',
            # yayımlanan KABUL BANDI: validation_system.py:99
            # (CHUG_DP_RATIO_MINIMUM, NASA SP-8089 / INJECTOR_DP_PC_CEILING);
            # alan kendi ``band_source`` künyesini zaten taşıyor
            '.validation.injector_assessment.pressure_drop_ratio.band[0]',
            '.validation.injector_assessment.pressure_drop_ratio.band[1]',
        ))
        imler = eval(  # noqa: S307 — kaynak depo içi, AST'ten derlenmiş
            compile(ast.Expression(body=ast.parse(im_blogu).body[0].value),
                    '<LEGITIMATE_CONSTANTS>', 'eval'))
        assert isinstance(imler, tuple) and len(imler) > 50, (
            'im listesi tuple olarak değerlendirilemedi: %r' % (imler,))
        imlenen = [y['yaprak'] for y in _z5_envanteri()['yapraklar']
                   if y['yaprak'] not in HUKUM13_SINIFLANDIRILAN
                   and any(im in y['yaprak'] for im in imler)]
        assert not imlenen, (
            'borç yaprağı LEGITIMATE_CONSTANTS imine taşınmış: %s — im '
            'geri alınmalı, borç sahibinin kulvarında ödenmeli' % imlenen)

    def test_hukum13_istisnasi_genisletilmedi(self):
        """İstisna listesi kendi kendine büyüyemez (ÖH D25 artçısı).

        Bir üstteki iddia yedi yaprağı muaf tutuyor. Muafiyet sessizce
        genişletilirse bu dosyanın koruduğu şey kalmaz; bu yüzden sayı
        AYRI ve YASTIKSIZ olarak sabitlenir. Yeni bir yaprak hüküm-13
        ile sınıflandırılacaksa bu sayı AYNI commit'te ölçülen değere
        çıkarılır ve gerekçesi yukarıya yazılır.
        """
        kaynak = _oku('tests/test_d23_bekci_cevirisi_a1.py')
        agac = ast.parse(kaynak)
        adetler = [len(n.args[0].elts) for n in ast.walk(agac)
                   if isinstance(n, ast.Call)
                   and getattr(n.func, 'id', '') == 'frozenset'
                   and n.args and isinstance(n.args[0], ast.Tuple)]
        # ÖH D26 / app-api a3: 7 -> 11. Dört yaprak app-api bakiyesinden
        # geldi (yukarıdaki blok); sayı AYNI commit'te ölçülen değere
        # çıkarıldı ve her yaprağın gerekçesi listede yazılı.
        assert adetler == [11], (
            'hüküm-13 muafiyet listesinin boyu değişmiş: %s (beklenen [11])'
            % adetler)

    def test_esik_gevsetilmedi(self):
        """Katman B'nin iki yönlü eşiği ÖLÇÜLEN sayıda duruyor.

        ÇEVRİLDİ — ÖH D25 / OH-Z5-02 (hibrit a1). Eski hâl eşiği 2'ye
        RAKAMLA çivilemişti ("14 yaprak dururken eşiği yükseltmek borcu
        gizlemektir"). O çivi D25'te YANLIŞ TARAFI koruyordu: taban
        cdf2106'da ölçülen sayı ZATEN 12'ydi, yani Katman B kırmızıydı
        ve bu iddia kırmızıyı DONDURUYORDU — eşiği ölçülen değere
        İNDİRMEK bile bu testi kırıyordu.
        Korunması gereken şey rakam değil SÖZLEŞMEDİR: eşik (a) iki
        yönlü kalmalı, (b) iki yanı AYNI sayı olmalı (yastıksız), (c)
        yükseltilmemeli. Yeni hâl bunu ölçer; sayının kendisi ölçümle
        birlikte düşebilir, ama sessizce YÜKSELEMEZ.
        """
        katman_b = _oku('tests/test_field_wiring_layer_b.py')
        ust = re.search(r'assert len\(suspicious\) <= (\d+)', katman_b)
        alt = re.search(r'assert len\(suspicious\) >= (\d+)', katman_b)
        assert ust and alt, (
            'sabit yaprak eşiğinin iki yanından biri kaldırılmış — im '
            'ekleyerek borç kapatmanın tek mekanik bekçisi buydu')
        ust_n, alt_n = int(ust.group(1)), int(alt.group(1))
        assert ust_n == alt_n, (
            'eşik YASTIKLI (üst %d, alt %d): araya yastık koymak yeni '
            'uydurma sabiti sessizce yutar' % (ust_n, alt_n))
        assert ust_n <= D25_OLCULEN_SABIT_YAPRAK, (
            'sabit yaprak eşiği %d\'e YÜKSELTİLMİŞ (D25\'te ölçülen: %d) '
            '— eşiği yükseltmek borcu gizlemektir; borç sahibinin '
            'kulvarında ödenir' % (ust_n, D25_OLCULEN_SABIT_YAPRAK))

    def test_bekci_cevirisi_sahasinda_yaprak_yok(self):
        """Bu kulvarın sahası ``tests/**``; 14 yaprağın 14'ü ürün kodunda."""
        env = _z5_envanteri()
        assert env['bekci-cevirisi_sahasinda'] == 0
        tests_ureten = [y['yaprak'] for y in env['yapraklar']
                        if y['uretim'].startswith('tests/')]
        assert not tests_ureten, (
            'tests/ ağacında üretilen yaprak var — bu kulvarda ONARILMALI: '
            '%s' % tests_ureten)


def test_parmak_izi_envanteri_tamamen_tests_agacinda():
    """P13B3-11'in onarım yüzeyi bu kulvarın sahasında olmalı.

    Envanterin bir çapası ``hrma/`` altına kayarsa kalem artık bu kulvarda
    kapatılamaz (ürün kodu başka kulvarların sahası) ve bunu sessizce
    fark etmemek, sonraki dalgada "saha dışı" gerekçesiyle ertelemek
    demektir. Ölçüm: envanterdeki her yol ``tests/`` ile başlar.
    """
    ham = json.loads(_oku(kanit_gerekli(PARMAK_IZI_ENVANTERI)))
    disarida = sorted({k['file'] for k in ham
                       if not k['file'].startswith('tests/')})
    assert not disarida, (
        'parmak izi çapası tests/ dışına kaymış: %s — kalem artık tek '
        'kulvarda kapatılamaz' % disarida)
