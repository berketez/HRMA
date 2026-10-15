# -*- coding: utf-8 -*-
"""ÖH D28 · termo-ucus a1 — OH-D27-12 (homoglif borcu) bekçisi.

ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D28/termo-ucus/a1/once_taban.json``)
-------------------------------------------------------------------------
Taban ağacında (``7cd08bcc``) depo genelindeki **tüm** karıştırılabilir
tanımlayıcı nüfusu 3'tü ve üçü de tek dosyadaydı:
``tests/test_z5s_isi_zinciri.py:520-522``, ``aciklik`` yerel adı — son
harfi U+043A CYRILLIC SMALL LETTER KA (K1, K2).

D27'de bu dosya termo-ucus kulvarının elindeydi; bekci-cevirisi a1 buna
dokunamadı ve borcu **adlı bir muafiyetle** kayda geçirdi
(``HOMOGLIF_BASKA_KULVAR_MUAFIYETI``, toplam tavan 3). Borcu ödemek
dosyanın sahibine, yani bu kulvara düştü.

NEDEN KUSUR (ölçüldü, K4 — beyan değil, sayı)
---------------------------------------------
Kiril ``к`` ekranda Latin ``k`` ile aynıdır. Taban ağacında:

* ``\\baciklik\\b`` (saf ASCII) araması dosyada **0 satır** tutuyordu;
  aynı adın Kiril yazımı **3 satır** tutuyordu. Yani adı ekrandan okuyup
  arayan geliştirici hiçbir şey bulamıyordu.
* Adı ASCII yazıp okumaya kalkan kod ``NameError: name 'aciklik' is not
  defined. Did you mean: 'aciklik'?`` alıyordu — Python'ın kendi önerisi
  bile iki adı ayırt edilemez basıyor.

D27 bekçisi bu tuzağın **düğüm adı** ayağını kanıtlamıştı (``pytest
dosya::ad`` → çıkış kodu 4, "no tests ran"). Buradaki ayak farklıdır:
düğüm adı zaten ASCII'ydi, kaçak **yerel değişkendeydi** — yani sessizdi,
pytest'e hiç yansımıyordu.

ONARIM
------
1. Üç kullanım ASCII'ye çevrildi (``tests/test_z5s_isi_zinciri.py``).
2. Muafiyet kaydı ÖLDÜ: ``HOMOGLIF_BASKA_KULVAR_MUAFIYETI`` boş kümeye,
   ``HOMOGLIF_TOPLAM_TAVANI`` 3 → 0 (``tests/test_d27_bekci_cevirisi_a1
   .py``; çift sahalı kalem — ürünü onaran kulvar imi de kaldırır).
3. Tarayıcının kayıt metni (``tests/support/homoglif_tarayici.py``
   docstring'i) muafiyetin öldüğünü söyler; aşağıdaki bekçi metin ile
   mandalın AYNI gerçeği söylemesini şart koşar.
"""

import ast
import os
import re
import subprocess
import sys

from tests.support import homoglif_tarayici as ht
from tests.support.homoglif_tarayici import (
    KIRIL_HOMOGLIFLER, ascii_disi_dugumler, pytest_dugum_adlari, tara,
)
from tests.test_d27_bekci_cevirisi_a1 import (
    ASCII_DISI_DUGUM_TAVANI, HOMOGLIF_BASKA_KULVAR_MUAFIYETI,
    HOMOGLIF_TAVANI, HOMOGLIF_TOPLAM_TAVANI,
)

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEDEF = 'tests/test_z5s_isi_zinciri.py'
DUGUM = 'test_izgara_govdeyi_kapsiyor'
ASCII_AD = 'aciklik'

#: Kiril yazımı KAYNAKTA durmasın diye kod noktasından kurulur; bu dosya
#: da saf ASCII kalır (kendi bekçisine yem olmaz).
KIRIL_YAZIM = ASCII_AD[:-1] + chr(0x043A)


def _hedef_govde():
    with open(os.path.join(_KOK, HEDEF), encoding='utf-8') as f:
        return f.read()


class TestOHD2712HomoglifBorcuOdendi:
    """Kusurun kendisi: dosyada karıştırılabilir harf kalmadı."""

    def test_depo_genelinde_homoglif_tanimlayici_nufusu_SIFIR(self):
        """Taban ağacında 3'tü (K1); muafiyet dahil toplam sıfırlandı."""
        bulgular = tara(_KOK)
        assert bulgular == [], (
            'karıştırılabilir harf taşıyan tanımlayıcı kaldı: '
            + '; '.join('%s:%d %s %r -> %s' % (
                b['dosya'], b['satir'], b['tur'], b['ad'],
                [k['kod'] for k in b['kacak']]) for b in bulgular))

    def test_hedef_dosyada_HICBIR_kiril_harf_yok(self):
        """Bu dosyanın meşru Kiril kullanımı YOKTUR (tarayıcının kendi
        sınama verisinden farkı budur): metin düzeyinde de sıfır."""
        kacak = sorted({c for c in _hedef_govde() if c in KIRIL_HOMOGLIFLER})
        assert kacak == [], (
            f'{HEDEF} içinde Kiril harf: '
            + ', '.join('U+%04X' % ord(c) for c in kacak))

    def test_onarilan_yerel_ad_SAF_ASCII_ve_ayni_dugumde_bagli(self):
        """Onarım "sil"me değil "çevir"medir: ad hâlâ aynı düğümde,
        bir kez atanıp iki kez okunuyor — ama saf ASCII."""
        import ast
        agac = ast.parse(_hedef_govde())
        dugum = [d for d in ast.walk(agac)
                 if isinstance(d, ast.FunctionDef) and d.name == DUGUM]
        assert len(dugum) == 1, f'{DUGUM} bulunamadı'
        adlar = [d.id for d in ast.walk(dugum[0]) if isinstance(d, ast.Name)]
        assert adlar.count(ASCII_AD) == 3, (
            f'{DUGUM} içinde {ASCII_AD!r} 3 kez geçmeli (1 atama + 2 '
            f'okuma); bulunan {adlar.count(ASCII_AD)}: {adlar}')
        assert KIRIL_YAZIM not in adlar, 'Kiril yazım geri geldi'

    def test_ascii_adla_arama_ARTIK_TUTUYOR(self):
        """K4'ün doğrudan tersi: taban ağacında 0 satır tutuyordu."""
        satirlar = _hedef_govde().splitlines()
        ascii_tutan = [i + 1 for i, s in enumerate(satirlar)
                       if re.search(r'\b%s\b' % ASCII_AD, s)]
        kiril_tutan = [i + 1 for i, s in enumerate(satirlar)
                       if KIRIL_YAZIM in s]
        assert len(ascii_tutan) == 3, (
            f'ASCII ad {len(ascii_tutan)} satırda; 3 bekleniyor '
            f'({ascii_tutan})')
        assert kiril_tutan == [], f'Kiril yazım hâlâ var: {kiril_tutan}'

    def test_hedef_dosyanin_DUGUM_adlari_saf_ASCII(self):
        """Aynı ailenin (OH-D26-14) üçüncü ayağı, bu dosyada ödendi.

        Türkçe harf ekranda ayırt EDİLİR — homoglif değildir — ama
        ``pytest dosya::ad`` elle yazıldığında yine "no tests ran"
        üretir. Ölçüldü: bu dosya iki böyle düğüm taşıyordu
        (``…gerçek…``, ``…marş…``); ikisi de ASCII'ye çevrildi ve depo
        envanteri 57 → 55'e indi (``ASCII_DISI_DUGUM_TAVANI`` = 56).
        Yerel değişken adlarında Türkçe harf depo geneli teamüldür
        (ölçüm: tests/ altında 178 geçiş) — bu bekçi onları kapsamaz.
        """
        kacak = [(satir, ad) for satir, ad
                 in pytest_dugum_adlari(os.path.join(_KOK, HEDEF))
                 if any(ord(c) > 127 for c in ad)]
        assert kacak == [], (
            f'{HEDEF} içinde ASCII-dışı pytest düğüm adı: {kacak}')

    def test_depo_dugum_envanteri_TAVANIN_altinda(self):
        """Envanter TEK YÖNLÜ mandal; bu onarım onu 2 düşürdü."""
        d = ascii_disi_dugumler(_KOK)
        assert len(d) <= ASCII_DISI_DUGUM_TAVANI, (
            f'ASCII-dışı pytest düğüm adı {len(d)}, tavan '
            f'{ASCII_DISI_DUGUM_TAVANI}: '
            f'{sorted({b["dosya"] for b in d})}')
        assert not [b for b in d if b['dosya'] == HEDEF], (
            f'{HEDEF} envanterden çıkmalıydı')


class TestOHD2712MuafiyetKaydiOldu:
    """Borç ödendiğine göre muafiyet kaydı da ölür — im kalkar."""

    def test_muafiyet_kumesi_bos_ve_iki_tavan_da_sifir(self):
        assert HOMOGLIF_BASKA_KULVAR_MUAFIYETI == frozenset(), (
            'D27 muafiyeti D28 termo-ucus a1 ile ödendi; küme boş '
            f'kalmalı: {sorted(HOMOGLIF_BASKA_KULVAR_MUAFIYETI)}')
        assert HOMOGLIF_TOPLAM_TAVANI == 0, (
            f'toplam tavan 0 olmalı, {HOMOGLIF_TOPLAM_TAVANI}')
        assert HOMOGLIF_TAVANI == 0, (
            f'serbest tavan 0 olmalı, {HOMOGLIF_TAVANI}')

    def test_tavan_OLCULEN_nufusun_ustunde_kalmiyor(self):
        """Mandal gevşek bırakılamaz: tavan, ölçülen nüfusa eşit."""
        assert HOMOGLIF_TOPLAM_TAVANI == len(tara(_KOK)), (
            'tavan ölçülen nüfusla aynı olmalı — aradaki boşluk '
            'gelecekteki bir kaçağa sessiz kredi açar: tavan '
            f'{HOMOGLIF_TOPLAM_TAVANI}, nüfus {len(tara(_KOK))}')

    def test_tarayici_KAYDI_ile_bekci_MANDALI_ayni_gercegi_soyluyor(self):
        """Belge ile mandal birbirinden kaymasın (iki yönlü)."""
        ilan_yok = 'MUAFİYET YOKTUR' in (ht.__doc__ or '')
        kume_bos = HOMOGLIF_BASKA_KULVAR_MUAFIYETI == frozenset()
        assert ilan_yok == kume_bos, (
            'tarayıcı docstringi ile muafiyet kümesi çelişiyor: '
            f'docstring "muafiyet yok" diyor mu={ilan_yok}, '
            f'küme boş mu={kume_bos}')


class TestOHD2712YerelAdAyagiCanliKanit:
    """Kusurun mekanizması — D27'nin düğüm-adı ayağının EKSİK yarısı.

    D27 ``pytest dosya::ad`` yolunu ölçmüştü. Burada düğüm adı zaten saf
    ASCII'ydi; kaçak yerel değişkendeydi, yani pytest'e hiç yansımıyordu
    ve ancak dosyayı elle okuyan biri takılıyordu.
    """

    def test_kiril_yerel_ad_ASCII_okumada_NameError_uretiyor(self, tmp_path):
        p = tmp_path / 'ornek.py'
        p.write_text('%s = 12.5\nprint(round(%s, 1))\n'
                     % (KIRIL_YAZIM, ASCII_AD), encoding='utf-8')
        r = subprocess.run([sys.executable, str(p)], capture_output=True,
                           text=True, timeout=120)
        assert r.returncode == 1, (r.stdout, r.stderr)
        assert 'NameError' in r.stderr, r.stderr
        assert ASCII_AD in r.stderr

    def test_ayni_kod_SAF_ASCII_yazilinca_calisiyor(self, tmp_path):
        """Yanlış pozitif yok: fark adın yazılışında, kodda değil."""
        p = tmp_path / 'ornek.py'
        p.write_text('%s = 12.5\nprint(round(%s, 1))\n'
                     % (ASCII_AD, ASCII_AD), encoding='utf-8')
        r = subprocess.run([sys.executable, str(p)], capture_output=True,
                           text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == '12.5'


# ===========================================================================
# OH-D27-11 (termo-ucus payı) — ÖDENDİ (ÖH D30 / termo-ucus a1, OH-D29-06)
# ===========================================================================
#: D27b app-api a3 rapor.md §4 tablosunun termo-ucus satırı: merkezî
#: ``hrma/utils/input_guard`` dışında kalan bağımsız çevirici tanımları.
#:
#: D28'DEKİ ENGEL (kayıt): merkezîleştirmenin hedefi ``input_guard`` o
#: dalgada **ihracat kulvarının** elindeydi (commit ``ac29bda7``); gereken
#: sözleşme — ``0``/``''``/``None``/negatif = VERİLMEDİ → ``None``, istisna
#: ATMAZ — bu ağaçta henüz YOKTU. Kardeş-dal kuralı gereği dokunulmadı ve
#: aşağıdaki mandallar borcu ÖDEMEDEN büyümesini engelledi.
#:
#: D30'DA ENGEL KALKTI (ölçüldü, ``D30/termo-ucus/a1/once.json`` K1):
#: birleşmeden sonra ``finite_positive`` / ``finite_number`` /
#: ``first_finite_positive`` / ``mm_to_m_read`` bu ağaçta VAR. Borç ödendi:
#:
#:   ``heat_transfer_analysis._positive_length`` → ``finite_positive``
#:   ``flight_vehicle._num``                     → ``finite_number``
#:   ``flight_vehicle._mm_to_m``                 → ``mm_to_m_read`` (D26'da)
#:
#: ÖLÇÜLEN KAZANÇ (``once.json`` → ``sonra.json``): bağımsız çevirici
#: nüfusu **5 → 3**; yerel-merkez karar ayrışması ``_positive_length``te
#: **2 → 0**, ``_num``da **2 → 0**. Ürün yüzeyinde kapanan sızıntı: tüm
#: zorunlu ısı-analizi alanları ``True`` gönderildiğinde
#: ``missing_heat_transfer_inputs`` 5 alanın 5'ini de "verilmiş" sayıyordu
#: (True = 1,0 Pa hazne basıncı); ``normalize('hybrid', {'thrust':
#: np.bool_(True)})`` uçan araç şemasına 1,0 N itki yazıyordu. İkisi de
#: artık ``None``/"eksik".
#:
#: Mandallar KALDI ve SIKILDI (gevşetilmedi): tavan ölçülen yeni nüfusa
#: indi, yani ödenen borç geri alınamaz.
OHD2711_SAHA_DOSYALARI = (
    'hrma/analysis/flight_vehicle.py',
    'hrma/analysis/heat_transfer_analysis.py',
    'hrma/analysis/nozzle_flow_1d.py',
    'hrma/analysis/six_dof_trajectory.py',
    'hrma/analysis/trajectory_analysis.py',
    'hrma/analysis/regen_cooling.py',
    'hrma/analysis/thermal_protection.py',
    'hrma/analysis/kinetic_efficiency.py',
    'hrma/analysis/acoustic_modes.py',
)

#: D27b app-api a3 §4 tablosunun termo-ucus satırında ADIYLA yazılı olan
#: iki dosya / üç tanım. ÖLÇÜM bu tablonun EKSİK olduğunu gösterdi (aşağı
#: bak) — kayıt yine de adıyla durur, borç izlenebilsin diye.
OHD2711_D27B_TABLOSU = {
    'hrma/analysis/flight_vehicle.py': ('_num', '_mm_to_m'),
    'hrma/analysis/heat_transfer_analysis.py': ('_positive_length',),
}

#: ÖLÇÜLEN nüfus. D28 tabanında (``7cd08bcc``) **5**'ti —
#: ``flight_vehicle._num``,
#: ``heat_transfer_analysis._positive_length``,
#: ``nozzle_flow_1d._json_safe``, ``six_dof_trajectory._require_finite``,
#: ``trajectory_analysis._finite_or_none``. Son üçü D27b §4 tablosunda
#: YOKTU; yani tablo termo-ucus için eksikti (D28 rapor.md §5).
#:
#: D30'da ilk ikisi merkeze bağlandı; tavan ÖLÇÜLEN yeni nüfusa indi
#: (``D30/termo-ucus/a1/sonra.json`` K2 = 3). Sayı YÜKSELTİLMEZ; düşen
#: tavan ödenen borcun geri alınamamasını sağlar.
OHD2711_OLCULEN_NUFUS = 3

#: Kalan üçün merkeze bağlanMAmasının ADLI gerekçesi (borç değil, sözleşme
#: farkı — ölçüldü, ``D30/.../sonra.json`` K3):
#:
#: ``nozzle_flow_1d._json_safe``       özyinelemeli JSON dönüştürücü
#:     (dict/list/ndarray gezer); değer kapısı DEĞİLDİR.
#: ``six_dof_trajectory._require_finite``  YÜKSELTEN kapı (``ValueError``);
#:     karşılığı ``finite_number`` değil ``_input_guards.require_positive``
#:     ailesidir.
#: ``trajectory_analysis._finite_or_none``  ``finite_number`` ile AYNI
#:     sözleşme, 4 kararda ayrışıyor (``bool``/``numpy.bool_``). GERÇEK
#:     borç; OH-D29-06 kaleminin adlı kapsamı dışında (kalem yalnız
#:     ``_positive_length`` / ``_num`` / ``_mm_to_m`` diyor) — devir
#:     kaydı D30 termo-ucus a1 rapor §5'tedir.
OHD2711_MERKEZE_BAGLANAN = {
    'hrma/analysis/heat_transfer_analysis.py': (
        '_positive_length', 'finite_positive'),
    'hrma/analysis/flight_vehicle.py': ('_num', 'finite_number'),
}


def _cevirici_bicimli(yol):
    """Modül düzeyi, ada DEĞİL BİÇİME bakan çevirici avcısı.

    Ölçüt: ``_`` ile başlayan modül düzeyi işlev, gövdesinde ``float(``
    çağrısı VE (``except (TypeError, ValueError)`` yakalaması YA DA
    ``isfinite`` sonluluk sınaması). Bu, "istemci değerini sayıya çevir,
    bozuksa sessizce None dön" desenidir — OH-D27-11'in konusu tam budur.
    Ada bakan bir mandal yeni ADLA yazılan çeviriciyi kaçırırdı (ölçüldü:
    mutasyon M6 ada bakan sürümde HAYATTA KALDI).
    """
    import ast
    with open(yol, encoding='utf-8') as f:
        kaynak = f.read()
    bulunan = []
    for d in ast.parse(kaynak).body:
        if not isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not d.name.startswith('_'):
            continue
        govde = ast.get_source_segment(kaynak, d) or ''
        if 'float(' in govde and (
                'except (TypeError, ValueError)' in govde
                or 'isfinite' in govde):
            bulunan.append(d.name)
    return sorted(bulunan)


class TestOHD2711TermoPayiEnvanteri:
    """Merkezîleşmemiş çevirici borcu adlıdır ve BÜYÜYEMEZ."""

    def _saha_nufusu(self):
        nufus = {}
        for bagil in OHD2711_SAHA_DOSYALARI:
            yol = os.path.join(_KOK, bagil)
            if os.path.exists(yol):
                bulunan = _cevirici_bicimli(yol)
                if bulunan:
                    nufus[bagil] = bulunan
        return nufus

    def test_bagimsiz_cevirici_nufusu_ARTMIYOR(self):
        """TEK YÖNLÜ mandal: yeni bağımsız çevirici yazılamaz."""
        nufus = self._saha_nufusu()
        toplam = sum(len(v) for v in nufus.values())
        assert toplam <= OHD2711_OLCULEN_NUFUS, (
            f'termo-ucus sahasında modül düzeyi bağımsız çevirici {toplam}, '
            f'ölçülen tavan {OHD2711_OLCULEN_NUFUS} — yeni çevirici yazmak '
            'yerine merkezî hrma/utils/input_guard kullanılmalı: '
            f'{nufus}')

    def test_D27b_tablosunun_EKSIK_oldugu_kayitli(self):
        """Ölçüm tabloyu düzeltti: §4 termo-ucus satırı eksikti.

        Tabloda 2 dosya / 3 tanım yazıyordu; biçime bakan ölçüm 5 dosyada
        5 tanım buldu. D30'da tablodaki İKİ dosya merkeze bağlandı, tablo
        DIŞINDAKİ üçü yerinde kaldı (adlı gerekçeleri yukarıda). Bu bekçi
        farkın GÖRÜNÜR kalmasını sağlar — ana model devri buna göre yapar.
        """
        nufus = self._saha_nufusu()
        tablo_disi = {d: a for d, a in nufus.items()
                      if d not in OHD2711_D27B_TABLOSU}
        assert set(tablo_disi) == {
            'hrma/analysis/nozzle_flow_1d.py',
            'hrma/analysis/six_dof_trajectory.py',
            'hrma/analysis/trajectory_analysis.py'}, (
            'D27b §4 tablosunun dışında kalan çevirici kümesi değişti; '
            f'devir kaydı güncellenmeli: {tablo_disi}')

    def test_D27b_tablosundaki_iki_dosya_ARTIK_bagimsiz_DEGIL(self):
        """ÖH D30 / OH-D29-06: ödenen borç geri alınamaz.

        D28'de bu iki dosya kendi çeviricisini yazıyordu (biçim avcısı
        ikisini de görüyordu). Merkeze bağlandıktan sonra gövdede ne
        ``float(`` ne ``except (TypeError, ValueError)`` kaldı; avcı
        onları artık GÖRMEZ. Biri yeniden satır içine alınırsa bu bekçi
        kırmızıya döner.
        """
        nufus = self._saha_nufusu()
        geri_donen = sorted(d for d in OHD2711_MERKEZE_BAGLANAN
                            if d in nufus)
        assert geri_donen == [], (
            'merkeze bağlanmış çevirici yeniden BAĞIMSIZ tanıma döndü: '
            f'{ {d: nufus[d] for d in geri_donen} } — hüküm '
            'hrma/utils/input_guard içindedir (TEK KAYNAK).')

    def test_merkezi_kapi_SOZLESMESI_VAR_ve_saha_ona_bagli(self):
        """ÖH D30 / OH-D29-06 — D28'deki "sözleşme yok" mandalının yerine.

        D28'de bu düğüm ``not hasattr(input_guard, 'finite_positive')``
        diyordu: engeli ÖLÇÜYORDU ("yapamadım" beyanı değil, sayı) ve
        birleşmeden sonra kırmızıya dönüp borcun ödenebilir hâle geldiğini
        SÖYLEDİ — tasarım gereği. Borç ödendikten sonra o iddia YANLIŞ
        oldu; yerine geçen bu düğüm mandalı GEVŞETMEZ, tersine üç ayakla
        SIKAR:

        1. Sözleşme bu ağaçta VAR (dört ad).
        2. Saha çeviricileri gerçekten merkeze DELEGE EDER (gövde AST'i:
           tek ``return input_guard.<kapı>(value)``) — takma ad, kopya
           değil.
        3. Kararlar 18 probda BİT-AYNI: ``bool`` ve ``numpy.bool_`` bir
           ölçü DEĞİLDİR (yerel tanımların deliği tam buydu; ölçüldü,
           ``D30/termo-ucus/a1/once.json`` K3 = 2 + 2 ayrışma).
        """
        from hrma.utils import input_guard
        from hrma.analysis import flight_vehicle as fv
        from hrma.analysis import heat_transfer_analysis as hta

        # (1) sözleşme var
        eksik = [ad for ad in ('finite_positive', 'finite_number',
                               'first_finite_positive', 'mm_to_m_read')
                 if not hasattr(input_guard, ad)]
        assert eksik == [], (
            f'merkezî DEĞER katmanı kapıları kayboldu: {eksik} — '
            'OH-D27-11 borcu bu kapılara bağlandı.')

        # (2) gövde DELEGE ediyor mu? (kopya tanım sessizce ayrışır)
        beklenen = {
            (hta.__file__, '_positive_length'): 'finite_positive',
            (fv.__file__, '_num'): 'finite_number',
            (fv.__file__, '_mm_to_m'): 'mm_to_m_read',
        }
        for (yol, fn_adi), kapi in beklenen.items():
            with open(yol, encoding='utf-8') as f:
                agac = ast.parse(f.read())
            dugum = next(d for d in agac.body
                         if isinstance(d, ast.FunctionDef)
                         and d.name == fn_adi)
            cagrilar = {
                n.func.attr for n in ast.walk(dugum)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == 'input_guard'}
            assert cagrilar == {kapi}, (
                f'{os.path.basename(yol)}::{fn_adi} merkezî kapı '
                f'{kapi!r} yerine {cagrilar or "hiçbir input_guard kapısı"} '
                'çağırıyor — TEK KAYNAK bozuldu (CLAUDE.md kural #11).')

        # (3) karar eşitliği — 18 prob
        import numpy as np
        problar = [None, '', 0, 0.0, -3.0, 2.5, '4.5', 'abc',
                   float('nan'), float('inf'), True, False,
                   np.bool_(True), np.bool_(False), np.float64(7.25),
                   np.int64(3), [1.0], {}]
        ciftler = (
            (hta._positive_length, input_guard.finite_positive),
            (fv._num, input_guard.finite_number),
            (fv._mm_to_m, lambda v: input_guard.mm_to_m_read(v)[0]),
        )
        for yerel, merkez in ciftler:
            for prob in problar:
                assert repr(yerel(prob)) == repr(merkez(prob)), (
                    f'{yerel.__name__} girdi {prob!r} için merkezden '
                    f'ayrıştı: {yerel(prob)!r} != {merkez(prob)!r}')

    def test_dogruluk_degeri_URUN_yuzeyinde_olcu_sayilmiyor(self):
        """Borcun ürün ayağı: ``True`` bir hazne basıncı değildir.

        ÖLÇÜLDÜ (``D30/termo-ucus/a1/once.json`` K4) — taban ağacında:

        * ``missing_heat_transfer_inputs`` tüm zorunlu alanları ``True``
          aldığında **5 alanın 5'ini de** "verilmiş" sayıyordu; yani
          1,0 Pa hazne basıncı ve 1,0 m hazne çapı ile ısı analizine
          giriliyordu (doktrin 1 — fail-closed ihlali).
        * ``normalize('hybrid', {'thrust': np.bool_(True), ...})`` uçan
          araç şemasına 1,0 N itki / 1,0 s yanma süresi yazıyordu.
        """
        import numpy as np
        from hrma.analysis import flight_vehicle as fv
        from hrma.analysis import heat_transfer_analysis as hta

        zorunlu = list(hta.HEAT_TRANSFER_REQUIRED_FIELDS)
        assert zorunlu, 'zorunlu alan listesi boşaldı — ölçüt anlamsızlaşır'
        for bool_deger in (True, np.bool_(True), False, np.bool_(False)):
            eksik = set(hta.missing_heat_transfer_inputs(
                {k: bool_deger for k in zorunlu}))
            kabul = sorted(k for k in zorunlu if k not in eksik)
            assert kabul == [], (
                f'{bool_deger!r} bir ÖLÇÜ sayıldı: {kabul} alanları '
                '"verilmiş" bildirildi.')

        arac = fv.normalize('hybrid', {
            'thrust': np.bool_(True), 'burn_time': np.bool_(True),
            'propellant_mass_total': np.bool_(True)})
        for alan in ('thrust', 'burn_time', 'propellant_mass'):
            assert arac[alan] is None, (
                f'uçan araç şemasında {alan} = {arac[alan]!r}; '
                'numpy doğruluk değeri sayıya çevrildi.')
