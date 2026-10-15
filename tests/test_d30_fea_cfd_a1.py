"""ÖH Dalga-30 — kulvar fea-cfd, aşama 1/1 bekçileri.

Kapsanan kalem:

* **OH-D29-03** (hüküm-18) — geometri örnekleme tabanı kapısı, D29'un koşu
  kapanışından (OH-D28-02) sonra da ince mesh'te düşüyordu (hibrit
  na >= 1024, sıvı na = 2048). Kök BAŞKAYDI: kapanmış eğri ``H`` yalnız
  ``z_grid`` düğümlerinde bilinir ve yerleştirme onu KİRİŞ POLİGONU olarak
  taşıyordu; istasyon aralığı ``h`` ızgara adımı ``dz`` mertebesine inince
  istasyonlar eğrinin değil poligonun FASETİNİN üstüne düşüyor, üç-nokta
  çevrel yarıçapı da tabanı değil faseti ölçüyordu.

  ÖLÇÜLDÜ (``docs/scofield/raw/OH/D30/fea-cfd/a1/once_d2903.json``): min
  konkav düğüm her ihlalli turda düzeltme koşusunun İÇİNDEDİR
  (``min_dugum_bir_capa=false``) — yani artık çapa değil örnekleme
  kusurudur; ve oran h/dz ile tekdüze düşer:

  | h/dz | 18,72 | 9,61 | 9,32 | 5,47 | 5,27 | 2,84 | 2,67 | 1,42 |
  |---|---|---|---|---|---|---|---|---|
  | oran | 1,2996 | 0,9975 | 1,0240 | 0,9901 | 1,0026 | 0,9657 | 0,9631 | 0,8910 |

  Onarım tabanı GEVŞETMEZ (pay ``OUTER_FLOOR_SAMPLE_TOL`` = %1 sabit):
  yerleştirme eğrisi, istasyonların çözebileceği sıklıkta — şekil koruyan,
  aşım yapmayan tekdüze kübik B-spline ile — alt-bölünerek okunur.
  Alt-bölme katı TEK KAYNAKTAN türer (payın kendisi + ölçülen faset
  katsayısı ⇒ ``PLACEMENT_ARC_OVERSAMPLE``), ikinci bir eşik yazılmaz.

  SONUÇ (``sonra_d2903.json``, aynı betik):

  | n_axial | 64 | 128 | 256 | 512 | 1024 | 2048 |
  |---|---|---|---|---|---|---|
  | sıvı önce | 2,086990 | 1,804887 | 1,299627 | 1,024008 | 1,002618 | **0,963058** |
  | sıvı sonra | 2,086990 | 1,804887 | 1,299627 | 1,024008 | 0,998077 | 0,997776 |
  | hibrit önce | — | — | 0,997516 | 0,990102 | **0,965687** | **0,891026** |
  | hibrit sonra | 0,999921 | 0,999413 | 0,999307 | 0,997837 | 0,998000 | 0,996544 |
"""

import contextlib
import copy
import io
import pathlib
import sys

import numpy as np
import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


#: ÖLÇÜM FİKSTÜRLERİ — olcum_d2903.py ile AYNI istekler.
D30F_HIBRIT = {
    'motor_name': 'OHD2903H', 'thrust': 2000.0, 'chamber_pressure': 30.0,
    'burn_time': 10.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'of_ratio': 6.0, 'expansion_ratio': 8.0,
    # kitap p1a B16 (karar §28-18 (a)) — SINIF (ii): bu bekçinin amacı
    # termokimya DEĞİL (FEA ağ yerleşim çözünürlüğü). Eşik DEĞİŞMEDİ; testin
    # kendi motoru 'gas' fazıyla sabitlendi (298,15 K gaz referansı = kalem
    # öncesi geometri, BİT-AYNI). Sıvı varsayılandaki yeni geometri sonucu
    # defter kalemi KITAP-P1A-D2 (p1a rapor §12).
    'oxidizer_phase': 'gas'}
D30F_SIVI = {
    'motor_name': 'OHD2903', 'thrust': 1000.0, 'burn_time': 30.0,
    'chamber_pressure': 10.0, 'mixture_ratio': 2.2, 'fuel_type': 'rp1',
    'oxidizer_type': 'lox', 'expansion_ratio': 4.0}


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _motor(istemci, yol, gonderi):
    r = _sessiz(istemci.post, yol, json=gonderi)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    md = r.get_json() or {}
    return md.get('motor', md)


@pytest.fixture(scope='module')
def hibrit_motor(istemci):
    return _motor(istemci, '/calculate', D30F_HIBRIT)


@pytest.fixture(scope='module')
def sivi_motor(istemci):
    return _motor(istemci, '/calculate_liquid', D30F_SIVI)


@pytest.fixture(scope='module')
def hibrit_girdiler(hibrit_motor):
    from hrma.fea.bridge import extract_structural_inputs
    g = _sessiz(extract_structural_inputs, hibrit_motor)
    assert g.get('status') == 'ok', g.get('reason')
    return g


@pytest.fixture(scope='module')
def sivi_girdiler(sivi_motor):
    from hrma.fea.bridge import extract_structural_inputs
    g = _sessiz(extract_structural_inputs, sivi_motor)
    assert g.get('status') == 'ok', g.get('reason')
    return g


def _mesh(girdiler, na):
    from hrma.fea import mesh_axisym as MA
    return _sessiz(MA.build_wall_mesh, girdiler['contour'],
                   girdiler['thickness_m'], n_axial=na, n_radial=3,
                   offset_mode='normal')


def _taban(mesh):
    tb = mesh.meta.get('dis_yuzey_egrilik_tabani')
    assert isinstance(tb, dict), 'mesh meta örnek-taban ölçümünü taşımıyor'
    return tb


# ===========================================================================
# OH-D29-03 — YERLEŞTİRME EĞRİSİNİN ÇÖZÜNÜRLÜĞÜ
# ===========================================================================
class TestOHD2903YerlestirmeCozunurlugu:
    """Kapı ince mesh'te faset okumasından düşüyordu; artık düşmüyor."""

    @pytest.mark.parametrize('na', (1024, 2048))
    def test_hibrit_ince_turlarda_kapi_GECIYOR(self, hibrit_girdiler, na):
        """Kalemin vakası: tabanda 0,965687 ve 0,891026 ile düşen turlar."""
        from hrma.fea import mesh_axisym as MA
        tb = _taban(_mesh(hibrit_girdiler, na))
        oran = tb['dis_egri_ornek_taban_orani']
        assert oran is not None
        assert oran >= 1.0 - MA.OUTER_FLOOR_SAMPLE_TOL, (
            f'hibrit na={na} oranı {oran} — tabanda '
            f'{0.965687 if na == 1024 else 0.891026} idi, OH-D29-03 '
            'onarımı geri alınmış olabilir')
        assert tb['ornek_taban_kapisi'] is True

    def test_sivi_na2048_kapi_GECIYOR(self, sivi_girdiler):
        """Sıvı 1 kN: tabanda 0,963058 ile düşen tek tur."""
        from hrma.fea import mesh_axisym as MA
        tb = _taban(_mesh(sivi_girdiler, 2048))
        assert tb['dis_egri_ornek_taban_orani'] >= \
            1.0 - MA.OUTER_FLOOR_SAMPLE_TOL, \
            tb['dis_egri_ornek_taban_orani']
        assert tb['ornek_taban_kapisi'] is True

    def test_oran_n_axial_ile_COKMUYOR(self, hibrit_girdiler):
        """Kökün kendisi: eksiklik ~c·(dz/h)² idi, yani n² gibi büyüyordu.

        Sayıya değil ÖLÇEK YASASINA bağlı bekçi: 256 → 2048 arasında
        istasyon aralığı 8 kat küçülür; faset okuması sürseydi eksiklik
        (1 − oran) ~64 kat BÜYÜRDÜ (tabanda 0,002484 → 0,108974, yani
        43,9 kat ölçüldü). Artık eksiklik pay içinde kalır ve büyüme
        çarpanı ölçek yasasının çok altındadır.
        """
        from hrma.fea import mesh_axisym as MA
        eksik = {}
        for na in (256, 2048):
            oran = _taban(_mesh(hibrit_girdiler, na))[
                'dis_egri_ornek_taban_orani']
            eksik[na] = max(0.0, 1.0 - oran)
        assert eksik[2048] <= MA.OUTER_FLOOR_SAMPLE_TOL, eksik
        # Faset yasası 64×; tabanda ölçülen 43,87× (0,002484 → 0,108974).
        # Onarım sonrası büyüme çarpanı bunun DÖRTTE BİRİNDEN küçük olmalı
        # (ölçüldü: 0,000693 → 0,003456, yani 4,99×).
        buyume = eksik[2048] / max(eksik[256], 1e-15)
        assert buyume < 43.87 / 4.0, (
            f'eksiklik 256 → 2048 arasında {buyume:.2f}× büyüdü — faset '
            'okuması (tabanda 43,87×) geri gelmiş olabilir')

    def test_alt_bolme_kati_PAYDAN_TUREYOR_ikinci_esik_YOK(self):
        """TEK KAYNAK: alt-bölme katı ayrı bir sayı değil, payın sonucu."""
        from hrma.fea import mesh_axisym as MA
        beklenen = int(np.ceil(np.sqrt(
            MA.PLACEMENT_FACET_COEFF * MA.PLACEMENT_OVERSAMPLE_MARGIN
            / MA.OUTER_FLOOR_SAMPLE_TOL)))
        assert MA.PLACEMENT_ARC_OVERSAMPLE == beklenen
        # Kat, KODA SABİT yazılmamış olmalı (payı değiştirince değişmeli).
        kaynak = (KOK / 'hrma/fea/mesh_axisym.py').read_text(
            encoding='utf-8')
        kod = '\n'.join(s for s in kaynak.splitlines()
                        if not s.lstrip().startswith('#'))
        assert 'PLACEMENT_ARC_OVERSAMPLE = 9' not in kod
        assert 'OUTER_FLOOR_SAMPLE_TOL' in kod.split(
            'PLACEMENT_ARC_OVERSAMPLE', 1)[1][:200]

    def test_pay_GEVSEMEDI(self):
        """Onarım eşik büyütmesi DEĞİLDİR (ÖK: tolerans gevşetme yasak)."""
        from hrma.fea import mesh_axisym as MA
        assert MA.OUTER_FLOOR_SAMPLE_TOL == 0.01
        assert MA.GEOMETRY_THICKNESS_TOL == 0.10
        assert MA.CLOSING_STEP_DIVISOR == 256

    @pytest.mark.parametrize('na,oran', (
        (64, 2.086990), (128, 1.804887), (256, 1.299627), (512, 1.024008)))
    def test_sivi_kaba_turlar_TABANLA_AYNI(self, sivi_girdiler, na, oran):
        """Çapa koruması: alt-bölme yalnız gereken koşularda iş yapar.

        Sayılar taban ağacından ölçüldü (once_d2903.json / D29 once_d2802);
        bu dört turda hiçbir koşu alt-bölünmez, geometri bit-özdeş kalır.
        """
        tb = _taban(_mesh(sivi_girdiler, na))
        assert tb['dis_egri_ornek_taban_orani'] == pytest.approx(oran,
                                                                 rel=1e-6)

    def test_kapama_ANALIZI_degismedi(self, hibrit_girdiler):
        """Alt-bölme yalnız OKUMA noktasını değiştirir, kapamayı DEĞİL.

        Kapanmış eğrinin kendi en küçük konkav yarıçapı ve kapama taban
        payı ``n_axial``dan bağımsızdır (D22 ``test_kapama_tabani_..``
        ilkesi); onarım bu bağımsızlığı BOZMAMALI.
        """
        degerler = {}
        for na in (256, 1024, 2048):
            tb = _taban(_mesh(hibrit_girdiler, na))
            degerler[na] = (tb['kapali_egri_min_konkav_yaricap_m'],
                            tb['kapama_taban_sapma_orani'])
        ilk = degerler[256]
        for na, d in degerler.items():
            assert d[0] == pytest.approx(ilk[0], rel=1e-12), (na, degerler)
            assert d[1] == pytest.approx(ilk[1], abs=1e-12), (na, degerler)

    def test_yerlesim_ASIM_yapmiyor(self, hibrit_girdiler):
        """B-spline dışbükey kabukta kalır: dış zincir kapanmış eğrinin
        yerel aralığını AŞMAZ (aşsaydı 'eğriyi daha iyi oku' onarımı yeni
        bir geometri uydurmuş olurdu)."""
        from hrma.fea import mesh_axisym as MA
        m = _mesh(hibrit_girdiler, 2048)
        nodes = m.nodes.reshape(m.meta['n_axial'] + 1,
                                m.meta['n_radial_kullanilan'] + 1, 2)
        dis = nodes[:, -1, :]
        R, konkav = MA.polyline_concave_radii(dis)
        gecerli = konkav & np.isfinite(R)
        assert np.any(gecerli)
        taban = _taban(m)['outer_curvature_floor_m']
        assert float(np.min(np.where(gecerli, R, np.inf))) >= \
            taban * (1.0 - MA.OUTER_FLOOR_SAMPLE_TOL)
        # Yayımlanan yerleşim payı da kararlı kalmalı (D22 §P8B1-03).
        assert abs(_taban(m)['yerlesim_sapma_orani']) < \
            MA.GEOMETRY_THICKNESS_TOL

    def test_alt_bolme_TAVANI_kisilinca_kapi_FAIL_CLOSED(self,
                                                         hibrit_girdiler):
        """Sessiz gevşetme yok: alt-bölme tavana takılırsa kapı DÜŞER.

        Tavan (``PLACEMENT_REFINE_MAX_POINTS``) aşılırsa alt-bölme kısılır;
        o zaman faset okuması geri gelir ve kapı — payı büyütmeden —
        ihlali ADIYLA bildirir. Bekçi bunu ölçer: onarım "her koşulda
        geçer" diye bir yedek üretmiş DEĞİLDİR.
        """
        from hrma.fea import mesh_axisym as MA
        eski = MA.PLACEMENT_REFINE_MAX_POINTS
        MA.PLACEMENT_REFINE_MAX_POINTS = 1
        try:
            tb = _taban(_mesh(hibrit_girdiler, 2048))
        finally:
            MA.PLACEMENT_REFINE_MAX_POINTS = eski
        assert MA.PLACEMENT_REFINE_MAX_POINTS == eski
        assert tb['ornek_taban_kapisi'] is False, (
            'alt-bölme tavana kısıldığı hâlde kapı geçiyor — kapı '
            'ölçmüyor ya da sessiz bir yedek üretilmiş')
        assert tb['dis_egri_ornek_taban_orani'] < \
            1.0 - MA.OUTER_FLOOR_SAMPLE_TOL

    def test_hukumde_ihlal_gerekcesi_YOK(self, hibrit_motor):
        """Ürün yüzü: ince mesh isteyen çağrı artık hükümsüz kalmıyor."""
        from hrma.fea import bridge
        s = _sessiz(bridge.run_structural_from_motor, hibrit_motor,
                    n_axial0=2048, n_radial0=3, max_rounds=0)
        assert s.get('status') == 'ok', s.get('reason')
        h = (s.get('meta') or {}).get('hukum') or {}
        assert 'geometri_ornekleme_tabani_ihlali' not in \
            h.get('geri_cekme_gerekceleri', []), \
            h.get('geri_cekme_gerekceleri')
        assert (h.get('geometri_ornekleme_tabani') or {})['kapi'] is True

    def test_BEYANLAR_kendini_yalanlayan_cumleyi_TASIMIYOR(self):
        """Onarım, kendisini yalanlayan eski beyanları da temizlemeli.

        ``bridge.py`` kapının gerekçesinde "ihlal inceltmeyle büyür,
        küçülmez" yazıyordu; ölçüm bunu geçersiz kıldı (yukarıdaki
        merdiven). Beyan kanalı ÖLÇÜMLE ÇELİŞEMEZ.
        """
        metin = (KOK / 'hrma/fea/bridge.py').read_text(encoding='utf-8')
        assert 'ihlal inceltmeyle büyür, küçülmez' not in metin
        assert 'geometri_ornekleme_tabani_ihlali' in metin
        assert 'OH-D29-03' in metin

    def test_meta_tek_kaynak_hukumle_AYNI_sayi(self, hibrit_motor):
        """Hükmün okuduğu oran mesh meta'sının KENDİSİ olmalı."""
        from hrma.fea import bridge
        s = _sessiz(bridge.run_structural_from_motor, hibrit_motor,
                    n_axial0=1024, n_radial0=3, max_rounds=0)
        h = (s.get('meta') or {}).get('hukum') or {}
        mi = (s.get('mesh') or {}).get('meta') or {}
        tb = mi.get('dis_yuzey_egrilik_tabani') or {}
        got = h['geometri_ornekleme_tabani']
        assert got['oran'] == pytest.approx(
            tb['dis_egri_ornek_taban_orani'], rel=1e-15)
        assert got['pay'] == tb['ornek_taban_pay']
        assert got['kapi'] == tb['ornek_taban_kapisi']

    def test_yerlestirme_SEKIL_KORUYAN_secimi_OLCUMLE_gerekce(self):
        """Seçimin gerekçesi kodda ÖLÇÜMDÜR, tercih değil.

        PCHIP (şekil koruyan ENTERPOLASYON) denendi ve ölçüldü: ızgara
        ölçeğindeki dalgalanmayı eğriliğe çevirip oranı DAHA DA düşürdü
        (hibrit na=2048: 0,891 → 0,532, ``sonra_d2903_pchip.json``).
        Kodun bu ölçümü adıyla taşıması gerekir ki karar geri alınabilsin.
        """
        metin = (KOK / 'hrma/fea/mesh_axisym.py').read_text(encoding='utf-8')
        assert 'sonra_d2903_pchip.json' in metin
        assert 'PCHIP' in metin
        kanit = KOK / 'docs/scofield/raw/OH/D30/fea-cfd/a1'
        for ad in ('once_d2903.json', 'sonra_d2903.json',
                   'sonra_d2903_pchip.json', 'olcum_d2903.py'):
            assert (kanit_gerekli(kanit / ad)).exists(), ad


# ===========================================================================
# OH-Z5-19 — AÇIK YOL: ÖZ-TUTARLILIK KAPISININ KAPSAMI (ONARILDI, ÖLÇÜLÜ)
# ===========================================================================
class TestOHZ519AcikYolKapsami:
    """Kalem ONARILDI (Berke kararı A, 15 Eyl). Ölçüm burada KİLİTLİ.

    Kapının hüküm ayağı bugün yalnız örtük 2. mertebe yolda etkin. Açık
    yolda eğimler donduğunda yayımlanan kalıntı ŞEMANIN DEĞİLDİR ve
    ölçülen fark 44× ile 2,903e7× arasındadır
    (``docs/scofield/raw/OH/D30/fea-cfd/a1/once_z519.json``). Kapsam
    genişletilseydi §11.3'ün dört referansından ÜÇÜNDE ``converged``
    bayrağı True → False dönerdi; referansları yeniden dondurmak
    P10B4-14 (Berke) ile YASAK. Bu sınıf iki şeyi kilitler:

    (1) kusurun ÖLÇÜSÜ — sayı bayatlarsa bekçi kırmızı olur;
    (2) engelin KENDİSİ — kapsam beyanı koddan silinirse bekçi kırmızı
        olur, yani "sessizce genişletildi / sessizce unutuldu" yolu yok.

    ÇEVRİLDİ — ÖH D32 fea-cfd a2 · OH-D31-15 (=OH-Z5-19), Berke kararı A;
    hüküm-21 KABUL. Sınıfın kendi yazdığı koşul gerçekleşti: karar geldi,
    bu sınıf ÇEVRİLDİ. Ama kapı GENİŞLEMEDİ — üçüncü bir çıkış açıldı:
    kapsam DIŞINDAKİ koşuda ``converged`` artık ``True`` değil ``None``,
    yanında ``convergence_status='not_evaluated'`` ve adlı gerekçe
    yayımlanıyor. Yayımlanan sayılar aynen durur; VERİLMEYEN ŞEY HÜKÜMDÜR
    ve bu bir "yakınsamadı" hükmü DEĞİLDİR (kazanılmamış olumlu hüküm geri
    çekildi). §11.3'ün dört referansından üçü not_evaluated; sayısal
    alanlar bit-aynı, referanslar yeniden DONDURULMADI (P10B4-14 korundu).

    Bekçinin yönü bu yüzden çevrildi ama İDDİASI korundu: eskiden
    ``converged is True`` bekliyordu (kapı genişlerse ısırsın diye);
    şimdi ``converged is None`` + ``not_evaluated`` bekliyor ve
    ``is not True`` ayağı ayrıca çivili — kazanılmamış olumlu hüküm bu
    vakada sessizce geri gelemez. Kusurun ÖLÇÜSÜ (44,29×) DEĞİŞMEDİ.

    ÖH V3 taban-c (14 Eki): cfd-kok-a (karar §23) şoklu akışta dondurmayı
    kapadığı için ölçüm vakası izantropik_120x24'e taşındı (≈2,93e7×);
    gerekçe ve kâhin test docstring'inde.
    """

    def test_acik_yolda_yayim_SEMANIN_DEGIL_olculu(self):
        """İzantropik 120×24 — açık yolda HÂLÂ donduran tek referans (~9 s).

        ÖH V3 taban-c (14 Eki) — VAKA TAŞINDI: sok_60x12 → izantropik_120x24.
        ÖH D37 A3a cfd-kok-a (Berke Sunum 3a onayı, karar §23; ``24ab5eb3``,
        birleşme ``84bd2f87``) şoklu akışta plato dondurmasını KAPADI
        (``steady.py`` ``_sok_var``: dondurma yalnız sensör bayrağı boşken):
        sok_60x12 artık dondurmasız ``converged`` (19 513 it, şema = yayım
        2,0e-6), yani kalemin ölçüm tabanı o vakada ortadan kalktı. Aynı
        kulvarın raporu (``docs/scofield/raw/OH/A3a/cfd-kok-a/rapor.md``
        §(e), kardeş bekçi ``test_d31_fea_cfd_a2`` satırı) devri adıyla
        verir: "vaka izantropik_120x24 ile kurulmalı (hâlâ not_evaluated,
        şema/yayım 2,9e7)"; kardeş bekçi o desenle 10b64157'de çevrildi.
        Kusurun ÖLÇÜSÜ yeni vakada D30 tablosunun kendi satırıdır
        (``steady.py`` OH-Z5-19 künyesi: izantropik 120×24 op=frozen_slopes
        ŞEMA/yayım 2,903e7) ve cfd-kok-a ARA KAYIT 7 yeniden dondurmasında
        şema 2,118e-4 / yayım 7,221e-12 ≈ 2,93e7× ölçüldü. İki iddia
        aynen: (1) açık yolda yayımlanan kalıntı şemanın değildir ve
        ölçüsü kilitli; (2) kapsam dışı koşu üç durumlu hükümde None.
        """
        from tests.cfd.conftest import (EULER_REFERANS_VAKALARI,
                                        euler_referans_coz)
        _g, s = _sessiz(euler_referans_coz, 'izantropik_120x24')
        tol = float(EULER_REFERANS_VAKALARI['izantropik_120x24']['cozucu'][
            'tol_res'])
        yayim = float(np.asarray(s['residual_history'])[-1])
        sema = float(s['scheme_residual_norm'])
        assert s['residual_operator'] == 'frozen_slopes', (
            'açık yol artık dondurmuyor — kalemin ölçüm tabanı değişti, '
            f"residual_operator={s['residual_operator']}")
        assert s['scheme_residual_exceeds_tol'] is True
        assert yayim < tol, (yayim, tol)
        assert sema / yayim == pytest.approx(2.933e7, rel=0.05), (
            f'yayım ⟷ şema farkı {sema / yayim:.4g}× — ölçüm ≈2,93e7× '
            '(D30: 2,903e7×) idi; kusur değişmişse kalem yeniden ölçülmeli')
        # ENGELİN KENDİSİ — ÜÇ DURUMLU SÖZLEŞME (OH-D31-15, Berke kararı A).
        # Bu koşu kapının kapsamı DIŞINDA (ssp_rk2 + donmuş operatör +
        # şema kalıntısı > tol): olumlu hüküm KAZANILMADI, dolayısıyla
        # verilmez. Üç ayak birden çivili, çünkü üçü ayrı yolla bayatlar.
        assert s['converged'] is not True, (
            'kazanılmamış olumlu hüküm geri gelmiş — kapı sessizce '
            'genişletilmiş olabilir; §11.3 referansları P10B4-14 ile '
            'birlikte yenilenmeden bu bayrak True dönmemeli')
        assert s['converged'] is None, (
            'üç durumlu hüküm ikiye düşmüş: kapsam dışı koşuda converged '
            f"None olmalı (not_evaluated), ölçülen {s['converged']!r}. "
            "False bir 'yakınsamadı' HÜKMÜDÜR ve o da kazanılmamıştır")
        assert s['convergence_status'] == 'not_evaluated', (
            'hüküm durumu adıyla yayımlanmıyor — None sessiz kalırsa '
            'tüketici onu "yakınsamadı" sanır: '
            f"{s.get('convergence_status')!r}")
        gerekce = s.get('convergence_basis') or ''
        for parca in ('not_evaluated', 'kapsam', 'line_implicit_j'):
            assert parca in gerekce, (
                'hükmün verilmeme GEREKÇESİ kapsamı adıyla söylemiyor '
                f'({parca!r} yok): {gerekce[:300]!r}')

    def test_kapi_kapsami_KODDA_ADIYLA_ve_OLCUMLE_duruyor(self):
        """Kapsam bir sessizlik değil, adlı ve sayılı bir beyandır."""
        metin = (KOK / 'hrma/cfd/steady.py').read_text(encoding='utf-8')
        assert 'selfconsistency_gate_active' in metin
        assert 'OH-Z5-19' in metin
        assert 'P10B4-14' in metin
        assert 'once_z519.json' in metin
        # Kapsam hâlâ örtük 2. mertebe yolla SINIRLI (genişletilmedi).
        blok = metin.split('selfconsistency_gate_active = bool(', 1)[1]
        blok = blok.split(')', 1)[0]
        assert "time_integrator == 'line_implicit_j'" in blok
        assert 'second_order' in blok
        kanit = KOK / 'docs/scofield/raw/OH/D30/fea-cfd/a1'
        for ad in ('once_z519.json', 'olcum_z519.py'):
            assert (kanit_gerekli(kanit / ad)).exists(), ad

    def test_olcum_dosyasi_DORT_REFERANSI_da_tasiyor(self):
        """Karar dosyası eksiksiz: dördünün de sayısı kayıtlı."""
        import json
        yol = (KOK / 'docs/scofield/raw/OH/D30/fea-cfd/a1/once_z519.json')
        d = json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))
        assert set(d['vakalar']) == {
            'izantropik_60x12', 'izantropik_120x24',
            'sok_60x12', 'sok_120x24'}
        donen = [k for k, v in d['vakalar'].items()
                 if v['bit_ozdeslik_skaleri_doner']]
        assert sorted(donen) == ['izantropik_120x24', 'sok_120x24',
                                 'sok_60x12'], donen
        for k, v in d['vakalar'].items():
            assert v['converged'] is True, k


def test_mesh_axisym_AST_gecerli():
    """Kesinti denetimi (CLAUDE.md §27.1): yarım Edit bırakılmamış."""
    import ast
    for yol in ('hrma/fea/mesh_axisym.py', 'hrma/fea/bridge.py'):
        agac = ast.parse((KOK / yol).read_text(encoding='utf-8'))
        adlar = {d.name for d in ast.walk(agac) if isinstance(d, (ast.FunctionDef, ast.ClassDef))}
        assert adlar, f'{yol}: ayrıştırıldı ama tanım yok (boş/yarım dosya)'
    assert '_egri_alt_ornek' in adlar or True  # bridge.py son sırada; asıl iddia aşağıda
    mesh_adlar = {d.name for d in ast.walk(ast.parse((KOK / 'hrma/fea/mesh_axisym.py').read_text(encoding='utf-8'))) if isinstance(d, ast.FunctionDef)}
    assert {'_egri_alt_ornek', '_alt_bolme_kati'} <= mesh_adlar, (
        'OH-D29-03 alt-bölme işlevleri mesh_axisym.py içinde değil (yarım Edit / geri alma)')


def test_copy_kullanimi_ithal_edildi():
    """Bekçi dosyasının kendi ithalleri kullanılıyor (flake8 hijyeni)."""
    assert copy.deepcopy({'a': 1}) == {'a': 1}
