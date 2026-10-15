# -*- coding: utf-8 -*-
"""ÖH D27 · bekci-cevirisi a1 — OH-D26-14 (homoglif) + OH-D26-08 (trapz).

Bu dosya iki kalemin bekçisidir. Her iddia ÖNCE ölçülmüş, sonra
onarılmıştır; ölçüm kanıtı
``docs/scofield/raw/OH/D27/bekci-cevirisi/a1/{once_taban,sonra}.json``,
ters-mutasyon kanıtı aynı dizindeki ``mutasyon*.json`` dosyalarıdır.

OH-D26-14 — KARIŞTIRILABİLİR (HOMOGLİF) TANIMLAYICI
---------------------------------------------------
ÖLÇÜLEN KUSUR (once_taban.json, K2): taban ağacında 2 dosyada 4
tanımlayıcı Kiril harf taşıyordu —

* ``tests/test_d26_arayuz_a2.py:263`` ``…_baglі`` (U+0456 CYRILLIC SMALL
  LETTER BYELORUSSIAN-UKRAINIAN I; ekranda Latin ``i``den ayırt
  edilemez),
* ``tests/test_z5s_isi_zinciri.py:499-501`` ``aciklik`` (U+043A CYRILLIC
  SMALL LETTER KA), üç kullanım. **D28 · termo-ucus a1 (OH-D27-12):
  ödendi** — dosyanın sahibi üç adı ASCII'ye çevirdi, adlı muafiyet
  kaldırıldı, iki tavan da 0'a indi.

NEDEN TEHLİKELİ: düğüm adı Latin harfle yazılıp ``pytest dosya::ad``
koşulduğunda pytest istisna atmaz; ``no tests ran`` basar ve çıkış kodu
``4`` (``USAGE_ERROR`` — düğüm bulunamadı) döner; ``-k`` yolunda ``5``
(``NO_TESTS_COLLECTED``). İkisi de ÖLÇÜLDÜ (bu dosyanın
``test_yanlis_dugum_adi_HATA_DEGIL_bos_kosum_uretiyor`` bekçisi gerçek
pytest alt süreci koşar). Mutasyon turunda bu "bekçi kırmızı olmadı"
diye değil "bekçi koştu ve yeşildi" diye okunur — oysa bekçi HİÇ
KOŞMAMIŞTIR. D26 yapisal-sistem a1'de üç mutasyon kaydı tam olarak böyle
sessizce eksik kalmıştı (kaynak: hukum15_notlar.md, öğretici bulgu 1).

OH-D26-08 — ``np.trapz`` BORCU
------------------------------
ÖLÇÜLEN KUSUR (once_taban.json, K1): NumPy 2.0 ``np.trapz`` adını
kaldırdı (``np.trapezoid``). Taban ağacında ``tests/`` altında 29 çağrı
sitesi vardı; güvenli çözücüler hariç 25'i borçtu ve tavan 24 olduğu için
``test_kalan_bekci_borcu_BUYUMUYOR`` zaten KIRMIZIYDI. Ayrıca ÜRÜN
kodunda ``hrma/analysis/curve_sampling.py`` 2 site taşıyordu (D26
yapisal-sistem a1'de eklenen ``trapezoid_error_permil``) — yani
``test_urun_kodunda_np_trapz_adi_KALMADI`` da taban ağacında kırmızıydı.
"""

import os
import subprocess
import sys

import pytest

from tests.support.homoglif_tarayici import (
    HOMOGLIFLER, KIRIL_HOMOGLIFLER, PYTEST_BOS_KOSUM_CIKIS_KODU,
    PYTEST_DUGUM_BULUNAMADI_CIKIS_KODU, YUNAN_HOMOGLIFLER,
    ascii_disi_dugumler, bos_kosum_mu, karistirilabilir_harfler, tara,
)

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ===========================================================================
# OH-D26-14 — homoglif tanımlayıcı taraması
# ===========================================================================
#: MUAFİYET ÖLDÜ — boş küme (ÖH D28 · termo-ucus a1, OH-D27-12).
#: D27'de tek adlı muafiyet vardı: ``tests/test_z5s_isi_zinciri.py`` o
#: sırada termo-ucus kulvarının elindeydi, bu yüzden bekci-cevirisi
#: oradaki 3 kullanıma dokunamamıştı. D28'de dosyanın SAHİBİ olan
#: termo-ucus borcu ödedi (``aciklik`` yerel adından U+043A söküldü;
#: ölçüm ``docs/scofield/raw/OH/D28/termo-ucus/a1/{once_taban,sonra}
#: .json``, K1/K2). Küme artık boştur ve TEK YÖNLÜDÜR: yeniden
#: doldurulamaz (aşağıdaki bekçi bunu sınar). Yeni bir kulvar çakışması
#: çıkarsa çare muafiyet değil, dosyanın sahibine kalem açmaktır.
HOMOGLIF_BASKA_KULVAR_MUAFIYETI = frozenset()

#: Muafiyet DIŞINDA kalan nüfusun tavanı: SIFIR. Kiril harf bu depoda
#: hiçbir bağlamda meşru değildir (arayüz dilleri Türkçe/İngilizce).
HOMOGLIF_TAVANI = 0

#: Muafiyet DAHİL toplam. D27'de 3'tü (ödenmemiş borç); D28 termo-ucus a1
#: onarımıyla ÖLÇÜLEN nüfus 0'a düştü, tavan da 0'a indirildi. TEK
#: YÖNLÜ mandal: yalnız küçülür.
HOMOGLIF_TOPLAM_TAVANI = 0


class TestOHD2614HomoglifTanimlayici:
    """Kiril/Yunan homoglifi taşıyan tanımlayıcı bırakılamaz."""

    def test_hicbir_tanimlayici_KARISTIRILABILIR_harf_tasimiyor(self):
        bulgular = tara(_KOK)
        serbest = [b for b in bulgular
                   if b['dosya'] not in HOMOGLIF_BASKA_KULVAR_MUAFIYETI]
        assert len(serbest) <= HOMOGLIF_TAVANI, (
            'karıştırılabilir harf taşıyan tanımlayıcı: '
            + '; '.join('%s:%d %s %r -> %s' % (
                b['dosya'], b['satir'], b['tur'], b['ad'],
                [k['kod'] for k in b['kacak']]) for b in serbest)
            + '. Bu harfler ekranda Latin ikizinden ayırt edilemez; adı '
              'elle yazan herkes "no tests ran" alır (hata DEĞİL).')

    def test_muafiyet_kumesi_dahil_TOPLAM_buyumuyor(self):
        bulgular = tara(_KOK)
        assert len(bulgular) <= HOMOGLIF_TOPLAM_TAVANI, (
            f'toplam homoglif tanımlayıcı {len(bulgular)}, tavan '
            f'{HOMOGLIF_TOPLAM_TAVANI} — muafiyet kümesi büyüyemez. '
            f'{sorted({b["dosya"] for b in bulgular})}')

    def test_muafiyet_kumesi_ODENDI_ve_geri_gelmiyor(self):
        """Muafiyet bir kaçış kapısı değildi, adlı bir borçtu — ödendi.

        ÖH D28 · termo-ucus a1 (OH-D27-12): kaydın gösterdiği 3 kullanım
        ASCII'ye çevrildi, kümenin gerekçesi kalmadı. Mandal TEK YÖNLÜ:
        küme yeniden doldurulamaz, tavan yükseltilemez.
        """
        assert HOMOGLIF_BASKA_KULVAR_MUAFIYETI == frozenset(), (
            'muafiyet kümesi ÖLÜ olmalı; yeniden doldurmak borcu '
            'gizlemektir — çare, dosyanın sahibine kalem açmaktır: '
            f'{sorted(HOMOGLIF_BASKA_KULVAR_MUAFIYETI)}')
        assert HOMOGLIF_TOPLAM_TAVANI == HOMOGLIF_TAVANI == 0, (
            'muafiyet öldüğüne göre iki tavan da SIFIR olmalı; alınan '
            f'toplam={HOMOGLIF_TOPLAM_TAVANI}, serbest={HOMOGLIF_TAVANI}')

    def test_D26_arayuz_dugumu_ARTIK_saf_ASCII(self):
        """Onarımın kendisi: U+0456 taşıyan düğüm adı ASCII'ye çevrildi."""
        yol = os.path.join(_KOK, 'tests', 'test_d26_arayuz_a2.py')
        govde = open(yol, encoding='utf-8').read()
        assert 'test_cevirici_var_ve_listelere_bagli' in govde
        assert not any(c in KIRIL_HOMOGLIFLER for c in govde), (
            'test_d26_arayuz_a2.py içinde hâlâ Kiril harf var')


class TestOHD2614TarayiciGercektenYakaliyor:
    """Tarayıcının kendisi sınanır — ölçmeyen bekçi bekçi değildir."""

    def test_KIRIL_i_yi_yakaliyor(self, tmp_path):
        p = tmp_path / 'ornek.py'
        p.write_text('def test_baglі():\n    pass\n', encoding='utf-8')
        (tmp_path / 'tests').mkdir()
        os.replace(str(p), str(tmp_path / 'tests' / 'ornek.py'))
        bulgular = tara(str(tmp_path), alt_dizinler=('tests',))
        assert len(bulgular) == 1, bulgular
        assert bulgular[0]['kacak'][0]['kod'] == 'U+0456'
        assert bulgular[0]['kacak'][0]['latin_ikizi'] == 'i'

    def test_saf_ASCII_ikizini_yakalamiyor(self, tmp_path):
        """Yanlış pozitif yok: aynı ad Latin harflerle yazılınca temiz."""
        (tmp_path / 'tests').mkdir()
        (tmp_path / 'tests' / 'ornek.py').write_text(
            'def test_bagli():\n    pass\n', encoding='utf-8')
        assert tara(str(tmp_path), alt_dizinler=('tests',)) == []

    def test_YUNAN_harf_JS_etiketinde_MESRU_sayiliyor(self, tmp_path):
        """``ρ``/``α`` arayüz etiketlerinde fizik gösterimidir; JS'te
        Yunan aranmaz, Kiril aranır."""
        (tmp_path / 'hrma').mkdir()
        js = tmp_path / 'hrma' / 'x.js'
        js.write_text('const etiket = "ρ (kg/m³)";\n',
                      encoding='utf-8')
        assert tara(str(tmp_path), alt_dizinler=('hrma',)) == []
        js.write_text('const рho = 1;\n', encoding='utf-8')   # Kiril r
        assert len(tara(str(tmp_path), alt_dizinler=('hrma',))) == 1

    def test_YUNAN_harf_PYTHON_tanimlayicisinda_KUSUR(self, tmp_path):
        (tmp_path / 'hrma').mkdir()
        (tmp_path / 'hrma' / 'x.py').write_text(
            'ρ = 1.0\n', encoding='utf-8')          # Yunan rho = ad
        bulgular = tara(str(tmp_path), alt_dizinler=('hrma',))
        assert len(bulgular) == 1, bulgular
        assert bulgular[0]['kacak'][0]['kod'] == 'U+03C1'

    def test_kume_ayrimi_KASITLI_ve_kesisimsiz(self):
        assert not (set(KIRIL_HOMOGLIFLER) & set(YUNAN_HOMOGLIFLER))
        assert set(HOMOGLIFLER) == (set(KIRIL_HOMOGLIFLER)
                                    | set(YUNAN_HOMOGLIFLER))
        assert karistirilabilir_harfler('baglі') == ['і']
        assert karistirilabilir_harfler('ρ', KIRIL_HOMOGLIFLER) == []


# ===========================================================================
# OH-D26-14 (ikinci ayak) — "no tests ran = KIRMIZI" kuralı
# ===========================================================================
class TestOHD2614BosKosumKirmizidir:
    """Mutasyon düzeneklerinin sözleşmesi: boş koşum YEŞİL sayılamaz."""

    def test_yanlis_dugum_adi_HATA_DEGIL_bos_kosum_uretiyor(self, tmp_path):
        """Kusurun mekanizmasının canlı kanıtı — gerçek pytest koşumu.

        Aynı görünen iki addan biriyle (Kiril) tanımlanmış test, öbürüyle
        (Latin) seçilmeye çalışılır. pytest çökmez, ``no tests ran`` der.
        """
        t = tmp_path / 'test_ornek.py'
        t.write_text('def test_baglі():\n    assert True\n',
                     encoding='utf-8')
        ini = tmp_path / 'pytest.ini'
        ini.write_text('[pytest]\n', encoding='utf-8')
        ortak = [sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider',
                 '-p', 'no:randomly', '-q', '--no-header', '-c', str(ini)]

        # (a) DÜĞÜM yolu: ``dosya::ad``. ÖLÇÜLDÜ — çıkış kodu 4
        # (USAGE_ERROR), istisna yok, "no tests ran" + "ERROR: not found".
        latin = subprocess.run(
            ortak + [f'{t}::test_bagli'], capture_output=True, text=True,
            cwd=str(tmp_path), timeout=180)
        assert latin.returncode == PYTEST_DUGUM_BULUNAMADI_CIKIS_KODU, (
            'düğüm bulunamadığında beklenen çıkış kodu 4; alınan '
            f'{latin.returncode}\n{latin.stdout}\n{latin.stderr}')
        assert 'no tests ran' in (latin.stdout + latin.stderr).lower()
        assert bos_kosum_mu(latin.returncode, latin.stdout + latin.stderr)

        # (b) ``-k`` yolu: seçici hiçbir şeyi tutmaz -> çıkış kodu 5.
        secici = subprocess.run(
            ortak + ['-k', 'test_bagli', str(t)], capture_output=True,
            text=True, cwd=str(tmp_path), timeout=180)
        assert secici.returncode == PYTEST_BOS_KOSUM_CIKIS_KODU, (
            'boş seçicide beklenen çıkış kodu 5; alınan '
            f'{secici.returncode}\n{secici.stdout}\n{secici.stderr}')
        assert bos_kosum_mu(secici.returncode,
                            secici.stdout + secici.stderr)

        # (c) DOĞRU (Kiril) adla koşum gerçekten yeşil — yani fark
        # bekçinin varlığında değil, ADIN YAZILIŞINDA.
        kiril = subprocess.run(
            ortak + [f'{t}::test_baglі'], capture_output=True,
            text=True, cwd=str(tmp_path), timeout=180)
        assert kiril.returncode == 0, kiril.stdout + kiril.stderr
        assert not bos_kosum_mu(kiril.returncode,
                                kiril.stdout + kiril.stderr)

    @pytest.mark.parametrize('kod,cikti,beklenen', [
        (PYTEST_BOS_KOSUM_CIKIS_KODU, '', True),
        (PYTEST_DUGUM_BULUNAMADI_CIKIS_KODU, '', True),
        (0, 'ERROR: not found: x.py::test_a', True),
        (0, 'no tests ran in 0.01s', True),
        (0, 'collected 0 items', True),
        (0, '1 passed in 0.10s', False),
        (1, '1 failed in 0.10s', False),
        # ÖLÇÜLDÜ (mutasyon turu M1): gerçek bir KIRMIZI, iletisinde
        # "no tests ran" ifadesini AÇIKLAMA olarak taşıyabilir. Ham metin
        # araması bunu boş koşum sanıp mutasyonu "kaldı" gösterir.
        (1, 'AssertionError: ... "no tests ran" alır (hata DEGIL)', False),
    ])
    def test_bos_kosum_karari_dogru(self, kod, cikti, beklenen):
        assert bos_kosum_mu(kod, cikti) is beklenen

    def test_kural_KAYNAKTA_yazili(self):
        """Kural bu oturumun raporunda değil, kodda durur."""
        from tests.support import homoglif_tarayici as ht
        assert 'KIRMIZI' in (ht.bos_kosum_mu.__doc__ or '')
        assert ht.PYTEST_BOS_KOSUM_CIKIS_KODU == 5


# ===========================================================================
# OH-D26-14 (üçüncü ayak) — ASCII-dışı pytest düğüm adı envanteri
# ===========================================================================
#: ÖLÇÜLDÜ (once_taban.json, K2b): taban ağacında 57 düğüm adı / 45 dosya
#: ASCII-dışı harf taşıyordu (Türkçe ``ı ş ö ü ç ğ`` + 1 Kiril). Kiril
#: olan onarıldı; Türkçe harfli olanlar EKRANDA ayırt edilebilir, yani
#: aynı sınıfta değildir — ama ``pytest ::ad`` elle yazıldığında yine
#: "no tests ran" üretirler. Envanter TEK YÖNLÜ mandal: büyüyemez.
#:
#: TAVAN, ÖLÇÜMÜN KENDİSİDİR — yastık bırakılmaz (ÖH D30 / fix-29a).
#: D28'de 55 ölçülmüş, tavan 56 yazılmıştı; o bir birimlik yastığı D29
#: arayüz-panel aşamaları sessizce doldurdu (55 -> 57) ve mandal iki
#: dalgada kırmızıya döndü. Üç düğüm ASCII'ye çevrildi (a2'de ``akı`` ve
#: ``gölgelemeye``, a3'te ``kalmıyor``; Türkçe docstring'ler AYNEN kaldı,
#: değişen yalnız tanımlayıcı adı) ve tavan bugünkü ölçüme indirildi:
#: bundan sonra ASCII-dışı TEK bir yeni düğüm adı doğduğu anda kırmızı
#: yanar. Sayı elle seçilmez; ``ascii_disi_dugumler`` ile ölçülür ve
#: yalnız AŞAĞI yazılır.
#:
#: ÖH V3 taban-b (14 Eki 2026): 12 Eki taban ölçümünde 56 > 54 KIRMIZI.
#: Yeni gelen ÜÇ ad (ölçüldü, a473505a tabanına karşı düğüm adı farkı)
#: ASCII'ye çevrildi — ``bileşince`` (test_d35_on_sembolik) ve iki
#: ``koşuda`` (test_d37_sahte_veri_b1); docstring'ler AYNEN. Aynı arada
#: bir ad (test_fazb_yogunluk_matrisi ``koşulsuz``) kalkmıştı; ölçüm 53.
#: Tavan ölçüme indirildi (yastık yok).
ASCII_DISI_DUGUM_TAVANI = 53


class TestOHD2614DugumAdiEnvanteri:

    def test_ascii_disi_dugum_nufusu_BUYUMUYOR(self):
        d = ascii_disi_dugumler(_KOK)
        assert len(d) <= ASCII_DISI_DUGUM_TAVANI, (
            f'ASCII-dışı pytest düğüm adı {len(d)}, tavan '
            f'{ASCII_DISI_DUGUM_TAVANI} — yeni düğüm adları saf ASCII '
            'yazılmalı (elle çağrıldığında "no tests ran" üretmesin). '
            f'Yeni gelenler: {sorted({b["dosya"] for b in d})}')

    def test_envanterde_KIRIL_kalmadi(self):
        """Türkçe harf ayırt edilebilir; Kiril edilemez — o SIFIR olmalı."""
        kalan = [b for b in ascii_disi_dugumler(_KOK) if b['homoglif']]
        assert kalan == [], (
            'pytest düğüm adında karıştırılabilir harf: '
            + '; '.join('%s:%d %r' % (b['dosya'], b['satir'], b['ad'])
                        for b in kalan))


# ===========================================================================
# OH-D26-08 — np.trapz borcunun kapandığının bağımsız çapası
# ===========================================================================
class TestOHD2608TrapzBorcuKapandi:
    """``tests/test_d26_termo_ucus_a1.py`` tavanı düşürdü; burada onarımın
    ÜRÜN ayağı ve tek kaynağın gerçekliği ayrıca çapalanır."""

    def test_urun_kodunda_np_trapz_KALMADI(self):
        """Taban ağacında ``hrma/analysis/curve_sampling.py`` 2 site
        taşıyordu (D26'da eklenen ``trapezoid_error_permil``); NumPy 2
        altında bu işlev ``AttributeError`` verirdi."""
        import ast as _ast
        kotu = []
        for dizin, altlar, adlar in os.walk(os.path.join(_KOK, 'hrma')):
            altlar[:] = [a for a in altlar
                         if a not in ('__pycache__', 'vendor')]
            for ad in adlar:
                if not ad.endswith('.py'):
                    continue
                tam = os.path.join(dizin, ad)
                bagil = os.path.relpath(tam, _KOK).replace(os.sep, '/')
                if bagil == 'hrma/utils/numeric_compat.py':
                    continue            # adın çözüldüğü TEK yer
                try:
                    agac = _ast.parse(open(tam, encoding='utf-8').read())
                except (SyntaxError, UnicodeDecodeError):
                    continue
                for d in _ast.walk(agac):
                    if (isinstance(d, _ast.Attribute) and d.attr == 'trapz'
                            and isinstance(d.value, _ast.Name)
                            and d.value.id in ('np', 'numpy')):
                        kotu.append((bagil, d.lineno))
        assert kotu == [], (
            f'ürün kodunda np.trapz kaldı: {kotu} — adı '
            'hrma.utils.numeric_compat.trapezoid üzerinden ithal et.')

    def test_curve_sampling_NUMPY2_altinda_kosuyor(self):
        """Onarımın davranış ayağı: ad alanından ``trapz`` silinse bile
        ``trapezoid_error_permil`` çalışır (ithal anında bağlanmıştır)."""
        import numpy as np
        from hrma.analysis.curve_sampling import trapezoid_error_permil
        t = [0.0, 1.0, 2.0, 3.0, 4.0]
        F = [0.0, 10.0, 10.0, 10.0, 0.0]
        tam = trapezoid_error_permil(t, F, [0, 1, 2, 3, 4])
        assert tam == pytest.approx(0.0, abs=1e-9)
        seyrek = trapezoid_error_permil(t, F, [0, 2, 4])
        assert seyrek is not None and seyrek < 0.0

        vardi, yedek = hasattr(np, 'trapz'), getattr(np, 'trapz', None)
        trapezoid_vardi = hasattr(np, 'trapezoid')
        try:
            if not trapezoid_vardi:
                setattr(np, 'trapezoid', yedek)
            if vardi:
                delattr(np, 'trapz')            # NumPy 2 taklidi
            assert trapezoid_error_permil(t, F, [0, 2, 4]) == (
                pytest.approx(seyrek, rel=1e-12))
        finally:
            if vardi:
                setattr(np, 'trapz', yedek)
            elif hasattr(np, 'trapz'):
                delattr(np, 'trapz')
            if not trapezoid_vardi and hasattr(np, 'trapezoid'):
                delattr(np, 'trapezoid')

    def test_cevrilen_bekci_dosyalari_TEK_KAYNAKTAN_ithal_ediyor(self):
        """24 sitenin çevrildiği 14 dosya adı gerçekten ithal ediyor."""
        cevrilenler = [
            'tests/cfd/test_duz_levha.py',
            'tests/fea/test_yapisal_dogrulama.py',
            'tests/test_d15_kati_a2.py',
            'tests/test_d16_kati_a2.py',
            'tests/test_faz6_f8_motor.py',
            'tests/test_hibrit_egri_ornekleme.py',
            'tests/test_hibrit_sure_cf.py',
            'tests/test_kati_rapor_ornekleme.py',
            'tests/test_scofield_analiz.py',
            'tests/test_scofield_kati.py',
            'tests/test_six_dof_coriolis.py',
            'tests/test_solid_codex_fixes.py',
            'tests/test_star_grain_model.py',
            'tests/test_z5s_openrocket_eng.py',
        ]
        eksik = []
        for bagil in cevrilenler:
            govde = open(os.path.join(_KOK, bagil), encoding='utf-8').read()
            if 'from hrma.utils.numeric_compat import trapezoid' not in govde:
                eksik.append(bagil)
        assert eksik == [], f'tek kaynaktan ithal etmiyor: {eksik}'
