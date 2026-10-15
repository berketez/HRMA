# -*- coding: utf-8 -*-
"""ÖH D30 · termo-ucus a1 — OH-D29-06 (OH-D27-11 termo payı) bekçisi.

KALEM
-----
``OH-D29-06``: "OH-D27-11 termo-ucus payı hâlâ açık:
``test_d28_termo_ucus_a1`` merkezî kapı sözleşmesi bekçisi TASARIM GEREĞİ
kırmızı (``_positive_length``→``finite_positive``,
``flight_vehicle._num``→``finite_number``, ``_mm_to_m``→``mm_to_m_read``)."

D28'de merkezîleştirmenin hedefi ``hrma/utils/input_guard`` ihracat
kulvarının dalındaydı; kardeş-dal kuralı gereği dokunulamadı ve engel bir
mandalla ÖLÇÜLDÜ (``not hasattr(input_guard, 'finite_positive')``). O
mandal birleşmeden sonra kırmızıya döndü — tasarım gereği: borcun
ÖDENEBİLİR hâle geldiğini söylüyordu. Bu dalgada borç ödendi.

ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D30/termo-ucus/a1/once.json``)
-------------------------------------------------------------------
K1  Merkezî kapılar bu ağaçta VAR (``finite_positive`` / ``finite_number``
    / ``first_finite_positive`` / ``mm_to_m_read``) → engel kalkmış.
K2  Saha genelinde modül düzeyi bağımsız çevirici nüfusu: **5**.
K3  Yerel tanım ile merkezî karşılığı 18 probda kıyaslandı:
    ``_positive_length`` **2** kararda, ``_num`` **2** kararda ayrışıyor.
    İkisi de aynı delik: ``float(True) == 1.0``. (``_mm_to_m`` D26'da
    zaten bağlanmıştı: 0 ayrışma.)
K4  ÜRÜN YÜZEYİ — beyan değil, sayı:
      * ``missing_heat_transfer_inputs`` zorunlu 5 alanın 5'ini de ``True``
        ile "verilmiş" sayıyordu (True = 1,0 Pa hazne basıncı, 1,0 m hazne
        çapı). Fail-closed ihlali (doktrin 1).
      * ``normalize('hybrid', {'thrust': np.bool_(True), ...})`` uçan araç
        şemasına 1,0 N itki / 1,0 s yanma süresi / 1,0 kg propelan
        yazıyordu. ``numpy.bool_`` Python ``bool``un alt sınıfı DEĞİLDİR,
        yerel ``isinstance(value, bool)`` süzgeci onu kaçırıyordu.

ONARIM (``sonra.json``)
-----------------------
``_positive_length`` ve ``_num`` gövdeleri merkezî kapıya DELEGE edildi
(takma ad; kopya değil). K2 5 → 3, K3 2 → 0 ve 2 → 0, K4 sızıntılarının
dördü de kapandı.

BEKÇİ İŞ BÖLÜMÜ (tekrar yok)
----------------------------
``tests/test_d28_termo_ucus_a1.py`` borç KAYDIDIR: nüfus mandalı (tavan
5 → 3 indirildi, gevşetilmedi), delege denetimi, 18 prob eşitliği ve ürün
yüzeyi ayakları oradadır. Bu dosya D30'a özgü İKİ ölçüyü sabitler:
nüfusun TAM sayısı ve kalan üç tanımın adlı gerekçesiyle DEVİR kaydı.
"""

import os
import sys

import pytest

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _KOK not in sys.path:
    sys.path.insert(0, _KOK)

from tests.test_d28_termo_ucus_a1 import (           # noqa: E402
    OHD2711_MERKEZE_BAGLANAN, OHD2711_OLCULEN_NUFUS, OHD2711_SAHA_DOSYALARI,
    _cevirici_bicimli,
)

#: ``sonra.json`` K2: onarımdan sonra sahada kalan BAĞIMSIZ tanımlar ve
#: her birinin merkeze bağlanMAma gerekçesi (borç değil, sözleşme farkı).
KALAN_TANIMLAR = {
    'hrma/analysis/nozzle_flow_1d.py': '_json_safe',
    'hrma/analysis/six_dof_trajectory.py': '_require_finite',
    'hrma/analysis/trajectory_analysis.py': '_finite_or_none',
}

#: ``once.json``/``sonra.json`` K3: ``_finite_or_none`` merkezî
#: ``finite_number`` ile AYNI sözleşmeyi taşır ama 18 probun **4'ünde**
#: ayrışır (``True`` / ``False`` / ``np.bool_(True)`` / ``np.bool_(False)``
#: → yerel sayı üretir, merkez ``None``). Bu GERÇEK borçtur; OH-D29-06'nın
#: adlı kapsamı dışındadır (kalem yalnız ``_positive_length`` / ``_num`` /
#: ``_mm_to_m`` der) ve D30 termo-ucus a1 rapor §5 ile devredilir.
#:
#: TEK YÖNLÜ mandal: ayrışma sayısı ARTAMAZ. Sıfıra inerse borç ödenmiş
#: demektir ve kayıt güncellenir (aşağıdaki ileti bunu söyler).
FINITE_OR_NONE_AYRISMA_TAVANI = 4


def _saha_nufusu():
    nufus = {}
    for bagil in OHD2711_SAHA_DOSYALARI:
        yol = os.path.join(_KOK, bagil)
        if os.path.exists(yol):
            bulunan = _cevirici_bicimli(yol)
            if bulunan:
                nufus[bagil] = bulunan
    return nufus


class TestOHD2906MerkeziKapiBorcuOdendi:
    """Borç ödendi; ödeme geri alınamaz ve kalan üç tanım ADLIDIR."""

    def test_nufus_TAM_olculen_sayida(self):
        """Mandal ``<=`` ile korur, bu düğüm TAM sayıyı sabitler.

        ``<=`` mandalı borcun büyümesini engeller ama ödenen borcun
        sessizce geri alınmasını göstermez (4 de 5'ten küçüktür). Burada
        ölçülen sayı ADIYLA durur: ``sonra.json`` K2 = 3.
        """
        nufus = _saha_nufusu()
        toplam = sum(len(v) for v in nufus.values())
        assert toplam == OHD2711_OLCULEN_NUFUS == 3, (
            f'bağımsız çevirici nüfusu {toplam}, ölçülen {3}: {nufus}')

    def test_kalan_uc_tanim_ADIYLA_kayitli(self):
        """Kalan tanımlar "bilinmeyen artık" değil, adlı kayıttır."""
        nufus = {d: tuple(a) for d, a in _saha_nufusu().items()}
        beklenen = {d: (ad,) for d, ad in KALAN_TANIMLAR.items()}
        assert nufus == beklenen, (
            'saha çevirici envanteri değişti; devir kaydı (rapor §5) '
            f'güncellenmeli: {nufus}')

    def test_bagli_iki_dosya_envanterde_YOK(self):
        """Ödenen borç geri alınamaz — satır içi tanıma dönüş kırmızıdır."""
        nufus = _saha_nufusu()
        assert [d for d in OHD2711_MERKEZE_BAGLANAN if d in nufus] == [], (
            f'merkeze bağlanan çevirici geri döndü: {nufus}')


class TestOHD2906KalanBorcGorunur:
    """``_finite_or_none`` borcu görünür kalır ve BÜYÜYEMEZ."""

    def test_finite_or_none_ayrismasi_ARTMIYOR(self):
        np = pytest.importorskip('numpy')
        from hrma.analysis import trajectory_analysis as ta
        from hrma.utils import input_guard

        problar = [None, '', 0, 0.0, -3.0, 2.5, '4.5', 'abc',
                   float('nan'), float('inf'), True, False,
                   np.bool_(True), np.bool_(False), np.float64(7.25),
                   np.int64(3), [1.0], {}]
        ayrisan = [p for p in problar
                   if repr(ta._finite_or_none(p))
                   != repr(input_guard.finite_number(p))]
        assert len(ayrisan) <= FINITE_OR_NONE_AYRISMA_TAVANI, (
            f'trajectory_analysis._finite_or_none merkezden {len(ayrisan)} '
            f'kararda ayrışıyor, ölçülen tavan '
            f'{FINITE_OR_NONE_AYRISMA_TAVANI}: {ayrisan}')
        if not ayrisan:
            pytest.fail(
                'borç ÖDENMİŞ görünüyor (_finite_or_none merkezle bit-aynı) '
                '— FINITE_OR_NONE_AYRISMA_TAVANI 0 yapılmalı ve devir '
                'kaydı (D30 termo-ucus a1 rapor §5) kapatılmalı.')


class TestOHD2906IceAktarmaZinciri:
    """Merkeze bağlanma motor paketini YARIM yüklemez."""

    def test_motor_paketi_TAM_yukleniyor(self):
        """Ölçülen tuzak: modül düzeyi ``hrma.utils`` içe aktarması.

        ``hrma.engines.__init__`` ``heat_transfer_analysis``ı içe aktarır.
        Bu modül modül DÜZEYİNDE ``from hrma.utils import input_guard``
        derse paketin ``__init__``i ``hrma.utils.injector_design`` →
        ``hrma.engines.*`` zincirini tetikler; ``hrma.engines.__init__``
        yarım yüklenmiş modülden ``HeatTransferAnalyzer``ı ister, alamaz
        ve *"Could not import some engine modules"* uyarısıyla EKSİK
        yüklenir — sessiz bir ürün arızası.

        ÖLÇÜLDÜ (``once.json``/``sonra.json`` K6): taban 0 uyarı; ilk
        onarım denemesi (modül düzeyi içe aktarma) 1 uyarı; kapıyı
        ``_positive_length`` gövdesine geciktiren son hâl yine 0.
        """
        import subprocess
        import sys as _sys
        kod = (
            "import warnings\n"
            "with warnings.catch_warnings(record=True) as w:\n"
            "    warnings.simplefilter('always')\n"
            "    import hrma.analysis.trajectory_analysis\n"
            "    import hrma.analysis.heat_transfer_analysis\n"
            "    import hrma.engines\n"
            "    print(len([x for x in w "
            "if 'engine modules' in str(x.message)]))\n")
        ortam = dict(os.environ, PYTHONPATH=_KOK,
                     PYTHONDONTWRITEBYTECODE='1', HRMA_HEADLESS='1')
        r = subprocess.run([_sys.executable, '-W', 'always', '-c', kod],
                           capture_output=True, text=True, cwd=_KOK,
                           env=ortam, timeout=300)
        assert r.returncode == 0, r.stderr[-1500:]
        son = (r.stdout.strip().splitlines() or [''])[-1]
        assert son == '0', (
            f'hrma.engines eksik yüklendi (uyarı sayısı {son!r}) — '
            'merkezî kapı içe aktarması dairesel zinciri tetikliyor; '
            'kapı çağrı anında (fonksiyon gövdesinde) istenmeli.')
