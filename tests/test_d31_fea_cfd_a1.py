"""ÖH Dalga-31 — kulvar fea-cfd, aşama 1/2 bekçileri.

Kapsanan kalemler
-----------------

* **P8B1-03** «ŞART (Fable TOPLU fea-cfd-01)» — kapama tabanı payı
  EMNİYETSİZ yöndeydi (kalın cidar ⇒ düşük gerilme ⇒ ŞİŞMİŞ emniyet
  katsayısı) ama yalnız ``solve_with_refinement``in BEYAN CÜMLESİNDE
  geçiyor, hiçbir hüküm kapısına bağlanmıyordu. ÖLÇÜLDÜ
  (``docs/scofield/raw/OH/D31/fea-cfd/a1/once_fea.json``, taban 9d70e9ed):

  | n_axial | 16 | 64 | 256 | 1024 |
  |---|---|---|---|---|
  | hibrit kapama tabanı | 0,1398076 | 0,1398076 | 0,1398076 | 0,1398076 |
  | katı kapama tabanı | 0,0027355 | 0,0027355 | 0,0027355 | 0,0027355 |

  Yani pay n_axial'dan gerçekten BAĞIMSIZ (dört turda da aynı) ve hibrit
  varsayılanında eşiğin (%10) üstünde — buna rağmen köprü HÜKÜM VERİYORDU
  (``verildi=True``, min SF 35,7206, ``hukum`` sözlüğünde kapama tabanı
  alanı bile YOKTU).

  ONARIM: pay bir HÜKÜM kapısına bağlandı (``kapama_taban_payi_asildi``).
  Eşik TÜRETİLDİ, yeni sabit YAZILMADI: yerleşim payını zaten yargılayan
  ``mesh_axisym.GEOMETRY_THICKNESS_TOL`` (0,10, gevşetilmedi). Türetim —
  ince cidar limitinde σ_θ = p·r/t ⇒ SF ∝ t ⇒ τ payı SF'yi tam (1+τ)
  katına çıkarır, payın KAYNAĞINDAN bağımsız; sembolik doğrulama
  ``turetim_p8b103.py`` / ``turetim_p8b103.json`` (membran tam, Lamé ince
  limitinde aynı, çarpım özdeşliği bağıl fark 0,0).

  SONUÇ (``sonra_fea.json``): hibrit ``verildi=False``,
  gerekçe ``['kapama_taban_payi_asildi']``, SF sayısı DEĞİŞMEDİ
  (35,7206 — sayı silinmez, hüküm geri çekilir); katı etkilenmedi
  (pay 0,0027; kendi gerekçesi ``kisit_yeri_duyarliligi_yuksek``).

* **OH-FT-01** — P8B2-13'ün devredilen borcu ADSIZDI ve hiç açılmamıştı.
  ÖLÇÜLDÜ (``once_fea.json`` C bölümü): ``git grep thin_wall_violated
  hrma/`` = 0 satır; köprünün dönüşünde ``warnings`` anahtarı YOK; iki
  örnek motorda da ``thin_wall_holds=False`` (hibrit t/r = 1,5880; katı
  t/r = 0,1819; sınır 0,10). ONARIM: ``WARN_THIN_WALL_VIOLATED`` kodu +
  köprü ``warnings`` kanalı + uç yüzeyi + panel rozeti + EN/TR sözlük
  kaydı. SONRA: iki motorda da ``warn.fea.thin_wall_violated`` çıkıyor.

* **OH-FT-03** — D22 kanıt betiği katı motoru SESSİZCE düşürüyordu:
  ``/calculate_solid`` motor sözlüğünü ÜST DÜZEYDE yayımlıyor, betik ise
  ``yanit['motor']`` arıyordu (ölçüldü: ``motor`` anahtarı yanıtta YOK,
  ``/calculate`` yanıtında VAR). Bekçi uç sözleşmesini kilitler.
"""

import contextlib
import copy
import io
import pathlib
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


#: ÖLÇÜM FİKSTÜRLERİ — olcum_fea.py ile AYNI istekler.
D31F_HIBRIT = {
    'thrust': 2000, 'burn_time': 10, 'of_ratio': 6.0,
    'chamber_pressure': 30.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    # V3.0.5 T-ÇAPA-C1 — ÖLÇÜM KOŞULU AÇIKÇA: c* verimi %100 ve cidar
    # 14,1913 mm. V301/H-termal (77d64c641, 26 Eki) korunan bölgeler yüzünden
    # boyutlandırılan hibrit cidarını inceltti, V301/H-PANEL (74b55500a)
    # N2O/HTPB c*'ına kaynaklı η=0,89 varsayılanı getirdi; ikisi de onaylı
    # yayımlanan sayı değişimidir, bekçinin konusu DEĞİL (FEA hüküm
    # mekanizması). Bu iki alanla köprü girdisi (cidar 0,01419125260707569 m, kontur toplamı
    # 1,0821779411399757) H-termal öncesi c7776576f ağacının varsayılan isteğiyle BİT-AYNI
    # (ölçüldü).
    'combustion_efficiency': 100.0, 'wall_thickness': 14.19125260707569}
D31F_KATI = {
    'motor_name': 'D31-KATI', 'propellant_type': 'apcp', 'grain_type': 'bates',
    'chamber_pressure': 40.0, 'thrust': 5000.0, 'burn_time': 3.0,
    'chamber_diameter': 100.0, 'grain_length': 500.0, 'core_diameter': 30.0,
    'expansion_ratio': 8.0}


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def hibrit_yanit(istemci):
    r = _sessiz(istemci.post, '/calculate', json=D31F_HIBRIT)
    assert r.status_code == 200, r.status_code
    return r.get_json()


@pytest.fixture(scope='module')
def kati_yanit(istemci):
    r = _sessiz(istemci.post, '/calculate_solid', json=D31F_KATI)
    assert r.status_code == 200, r.status_code
    return r.get_json()


@pytest.fixture(scope='module')
def hibrit_motor(hibrit_yanit):
    return hibrit_yanit['motor']


@pytest.fixture(scope='module')
def hibrit_girdiler(hibrit_motor):
    from hrma.fea.bridge import extract_structural_inputs
    g = _sessiz(extract_structural_inputs, hibrit_motor)
    assert g.get('status') == 'ok', g.get('reason')
    return g


@pytest.fixture(scope='module')
def hibrit_kosum(hibrit_motor):
    """Ucuz koşum: tek tur, kapı ölçümleri n_axial'dan bağımsız."""
    from hrma.fea import bridge
    return _sessiz(bridge.run_structural_from_motor, hibrit_motor,
                   n_axial0=64, n_radial0=3, max_rounds=0)


def _hukum(sonuc):
    assert sonuc.get('status') == 'ok', sonuc.get('reason')
    h = (sonuc.get('meta') or {}).get('hukum')
    assert isinstance(h, dict), 'köprü hüküm sözleşmesi taşımıyor'
    return h


# ===========================================================================
# P8B1-03 — kapama tabanı payı HÜKÜM kapısına bağlı (Fable ŞART)
# ===========================================================================
class TestP8B103KapamaTabaniHukumKapisi:

    def test_pay_n_axial_BAGIMSIZ_ve_hibritte_esigin_USTUNDE(
            self, hibrit_girdiler):
        """ŞARTın dayandığı ölçüm: pay tur-bağımsız ve emniyetsiz yönde.

        Bu, kapının NEDEN yakınsama ölçütüne değil HÜKME bağlandığının
        kanıtıdır: inceltmeyle geçilemeyen bir ölçüt inceltmenin kabul
        ölçütü olamaz.
        """
        from hrma.fea import mesh_axisym as MA
        paylar = []
        for na in (16, 64, 256):
            m = _sessiz(MA.build_wall_mesh, hibrit_girdiler['contour'],
                        hibrit_girdiler['thickness_m'], n_axial=na,
                        n_radial=3, offset_mode='normal')
            tb = m.meta['dis_yuzey_egrilik_tabani']
            paylar.append(float(tb['kapama_taban_sapma_orani']))
        assert max(paylar) - min(paylar) < 1e-12, (
            f'kapama tabanı payı n_axial ile değişti: {paylar} — '
            'ölçüm (once_fea.json) dört turda da 0,13980761 idi')
        assert paylar[0] > MA.GEOMETRY_THICKNESS_TOL, (
            f'hibrit payı {paylar[0]} eşiğin altına düştü — ŞARTın dayandığı '
            'ölçüm kaymış; kapıyı sınayan aşağıdaki bekçi anlamsızlaşır')

    def test_esik_TEK_KAYNAK_ve_GEVSETILMEDI(self):
        """Eşik türetimlidir: yeni sabit yok, 0,10 gevşetilmedi."""
        from hrma.fea import bridge
        from hrma.fea import mesh_axisym as MA
        assert MA.GEOMETRY_THICKNESS_TOL == 0.10, 'eşik gevşetilmiş'
        assert bridge.GEOMETRY_THICKNESS_TOL is MA.GEOMETRY_THICKNESS_TOL, (
            'köprü eşiği kendi kopyasından okuyor — tek kaynak kırıldı')

    def test_pay_esigi_asinca_HUKUM_ADLI_gerekce_ile_geri_cekilir(
            self, hibrit_kosum):
        """Kapının kendisi: ürün akışında ihlal VAR ve hüküm geri çekiliyor."""
        h = _hukum(hibrit_kosum)
        kt = h.get('kapama_tabani')
        assert isinstance(kt, dict), (
            'hüküm sözlüğünde kapama_tabani alanı YOK — pay hâlâ yalnız '
            'beyan cümlesinde (P8B1-03 ŞART ödenmemiş)')
        assert kt['kapi'] is False
        assert kt['pay'] > kt['esik']
        assert 'kapama_taban_payi_asildi' in h['geri_cekme_gerekceleri'], (
            'pay eşiği aşıyor ama hüküm geri çekilmiyor — kapı bağlı değil: '
            f"{h['geri_cekme_gerekceleri']}")
        assert h['verildi'] is False
        # Sayı SİLİNMEZ: çözücünün gerçek çıktısı yanında durur.
        assert hibrit_kosum['min_safety_factor'] is not None
        # Pay emniyetsiz yönü ADIYLA taşır: SF şişme çarpanı yayımlanır.
        assert kt['sf_sisme_carpani'] == pytest.approx(1.0 + kt['pay'])

    def test_pay_esigin_ALTINDA_kalinca_bu_gerekce_KONMAZ(self, hibrit_motor):
        """Kapı YALNIZ emniyetsiz yönü keser (ters yön: pay küçültülür).

        Mesh meta'sına eşiğin ALTINDA bir pay enjekte edilir; gerekçe
        listesinden ``kapama_taban_payi_asildi`` düşmelidir. Böylece bekçi
        "her koşumda kırmızı" bir sabit redde dönüşmez.
        """
        from hrma.fea import bridge
        gercek_solve = bridge.solve_with_refinement

        def _sarmal(*aa, **kk):
            ref = gercek_solve(*aa, **kk)
            ref.mesh.meta = copy.deepcopy(ref.mesh.meta)
            tb = ref.mesh.meta['dis_yuzey_egrilik_tabani']
            tb['kapama_taban_sapma_orani'] = 0.01
            return ref

        bridge.solve_with_refinement = _sarmal
        try:
            s = _sessiz(bridge.run_structural_from_motor, hibrit_motor,
                        n_axial0=64, n_radial0=3, max_rounds=0)
        finally:
            bridge.solve_with_refinement = gercek_solve
        h = _hukum(s)
        assert h['kapama_tabani']['kapi'] is True
        assert 'kapama_taban_payi_asildi' not in h['geri_cekme_gerekceleri']

    def test_pay_OLCULEMEZSE_kapi_hukmu_dusurmez(self, hibrit_motor):
        """Alan yoksa (eski mesh / radyal kip) kapı uygulanmaz: None."""
        from hrma.fea import bridge
        gercek_solve = bridge.solve_with_refinement

        def _sarmal(*aa, **kk):
            ref = gercek_solve(*aa, **kk)
            ref.mesh.meta = copy.deepcopy(ref.mesh.meta)
            ref.mesh.meta['dis_yuzey_egrilik_tabani'].pop(
                'kapama_taban_sapma_orani', None)
            return ref

        bridge.solve_with_refinement = _sarmal
        try:
            s = _sessiz(bridge.run_structural_from_motor, hibrit_motor,
                        n_axial0=64, n_radial0=3, max_rounds=0)
        finally:
            bridge.solve_with_refinement = gercek_solve
        h = _hukum(s)
        assert h['kapama_tabani']['kapi'] is None
        assert 'kapama_taban_payi_asildi' not in h['geri_cekme_gerekceleri']


# ===========================================================================
# OH-FT-01 — ince cidar öncülü ihlali KULLANICIYA çıkar
# ===========================================================================
class TestOHFT01InceCidarUyarisi:

    def test_kod_tek_yerde_URETILIR_ve_sozlukte_KAYITLI(self):
        from hrma.fea import bridge
        assert bridge.WARN_THIN_WALL_VIOLATED == 'warn.fea.thin_wall_violated'
        sozluk = (KOK / 'hrma' / 'static' / 'js'
                  / 'i18n_common.js').read_text(encoding='utf-8')
        assert sozluk.count("'warn.fea.thin_wall_violated':") == 2, (
            'sözlükte EN + TR kaydı olmalı; eksik kayıt kullanıcıya HAM '
            'anahtar gösterir')

    def test_oncul_kirilinca_UYARI_kaydi_uretilir(self, hibrit_kosum):
        tw = (hibrit_kosum.get('meta') or {}).get('thin_wall') or {}
        assert tw.get('thin_wall_holds') is False, (
            'hibrit varsayılanında öncül artık tutuyor — bekçinin dayandığı '
            f"ölçüm kaymış (t/r = {tw.get('max_t_over_r')})")
        uyarilar = hibrit_kosum.get('warnings')
        assert isinstance(uyarilar, list), (
            'köprü warnings kanalı YOK — OH-FT-01 borcu ödenmemiş')
        kodlar = [u.get('code') for u in uyarilar]
        assert 'warn.fea.thin_wall_violated' in kodlar, kodlar
        kayit = next(u for u in uyarilar
                     if u['code'] == 'warn.fea.thin_wall_violated')
        # Parametreler ÖLÇÜLEN sayılardır, uydurma yok.
        assert kayit['params']['t_over_r'] == pytest.approx(
            tw['max_t_over_r'], rel=1e-3)
        assert kayit['params']['limit'] == tw['limit']

    def test_oncul_TUTUYORSA_uyari_BASILMAZ(self, hibrit_motor):
        """Ters yön: ihlal yoksa uyarı da yok (sabit alarm değil)."""
        from hrma.fea import bridge
        gercek = bridge.thin_wall_report

        def _sahte(*a, **kw):
            r = dict(gercek(*a, **kw))
            r['max_t_over_r'] = 0.01
            r['thin_wall_holds'] = True
            return r

        bridge.thin_wall_report = _sahte
        try:
            s = _sessiz(bridge.run_structural_from_motor, hibrit_motor,
                        n_axial0=64, n_radial0=3, max_rounds=0)
        finally:
            bridge.thin_wall_report = gercek
        kodlar = [u.get('code') for u in (s.get('warnings') or [])]
        assert 'warn.fea.thin_wall_violated' not in kodlar

    def test_uc_yuzeyi_uyarilari_TASIYOR(self, istemci, hibrit_yanit):
        r = _sessiz(istemci.post, '/api/fea/structural',
                    json={'motor': hibrit_yanit, 'max_rounds': 0,
                          'n_axial0': 64, 'n_radial0': 3})
        assert r.status_code == 200, r.status_code
        fea = r.get_json()['fea']
        assert fea.get('status') == 'ok', fea.get('reason')
        assert 'warnings' in fea, (
            'uç yüzeyi warnings alanı taşımıyor — uyarı panele hiç ulaşmaz')
        kodlar = [u.get('code') for u in (fea.get('warnings') or [])]
        assert 'warn.fea.thin_wall_violated' in kodlar, kodlar

    def test_panel_ok_dalinda_uyarilari_OKUYOR(self):
        """Panel kanalı: view-model alanı + rozet basımı kodda DURUYOR."""
        js = (KOK / 'hrma' / 'static' / 'js'
              / 'fea_panel.js').read_text(encoding='utf-8')
        # TABANDA bu satır ZATEN vardı — ama YALNIZ tane (planar grain)
        # görünüm modelinde (fea_panel.js:2275). Yapısal dal onu hiç
        # taşımıyordu; bu yüzden sayım iki olmalı ve yapısalın kendi
        # bloğunda (mesh_info'dan hemen önce) durmalı.
        assert js.count('warnings: Array.isArray(fea.warnings)') == 2, (
            'panel yapısal dalda fea.warnings okumuyor (tabanda yalnız tane '
            'dalında vardı)')
        assert ('warnings: Array.isArray(fea.warnings) ? fea.warnings : [],\n'
                '            mesh_info: {') in js, (
            'yapısal görünüm modelinde uyarı alanı yok')
        assert 'vm.warnings.forEach' in js, (
            'panel uyarı rozetini basmıyor')
        # Çevirici TEK: kardeş tane dalının çeviricisi kullanılır.
        assert js.count('function grainWarningText') == 1


# ===========================================================================
# OH-FT-03 — /calculate_solid motor sözlüğünü ÜST DÜZEYDE yayımlar
# ===========================================================================
class TestOHFT03KatiYanitSozlesmesi:

    def test_kati_yanit_motor_anahtari_TASIMAZ(self, kati_yanit, hibrit_yanit):
        """D22 betiğinin katıyı düşürme kusurunun KÖKÜ.

        Bu bir uç sözleşmesi ölçümüdür: iki uç AYNI biçimi kullanmıyor.
        Kanıt betiği bu yüzden ikisini de kabul etmek zorundadır.
        """
        assert 'motor' in hibrit_yanit, (
            '/calculate artık motor anahtarı taşımıyor — kanıt betikleri '
            'yeniden ölçülmeli')
        assert 'motor' not in kati_yanit, (
            '/calculate_solid artık motor anahtarı taşıyor — OH-FT-03 '
            'onarımındaki iki-yollu okuma gereksizleşti, betik sadeleşsin')
        # Motor sözlüğü üst düzeydedir ve köprünün aradığı alanları taşır.
        assert 'chamber_pressure' in kati_yanit

    def test_duzeltilmis_betik_iki_motoru_da_OLCUYOR(self):
        """Kanıt betiği artık katıyı sessizce düşürmüyor."""
        import json
        yol = (KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D31' / 'fea-cfd'
               / 'a1' / 'sonra_fea.json')
        d = json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))
        assert set(d['A_kapama_tabani']) >= {'hibrit', 'kati'}, (
            'kanıt dosyası hâlâ tek motor taşıyor (OH-FT-03)')
        assert d['OH_FT_03']['eski_betik_kati_dusurur_mu'] is True


# ===========================================================================
# P10B4-14 — bit-özdeşlik referansları KİRLİ ağaçtan dondurulmuştu
# ===========================================================================
class TestP10B414ReferansKunyesi:
    """ÖLÇÜLDÜ (once_cfd.json K1, taban 9d70e9ed): sevk edilen DÖRT Euler
    referansının DÖRDÜ de ``git_calisma_agaci_kirli = true`` (commit
    a8e03547); hiçbirinde ``git_durumu_olculebildi`` /
    ``git_kirli_izin_gerekcesi`` alanı yoktu ve bekçi kirliliği HİÇ
    denetlemiyordu (dosyada ``kirli``/``dirty`` dizesi geçmiyordu).

    KARAR ÖNCESİ ÖLÇÜM (Berke karar dosyası §5, seçenek (a)): temiz
    ağaçta yeniden koşum dördünde de BİT-ÖZDEŞ çıktı — maks mutlak fark
    0,0; iterasyon sayıları eşit (8874 / 9011 / 26896 / 21870). Yani
    künyeyi tazelemek hiçbir yayımlanan sayıyı değiştirmez; yeniden
    dondurma PROVENANS işlemidir. Arşiv taban ağacıyla dizi kıyası:
    ``referans_taban_kiyasi.json`` (5 dosya, tüm diziler bit-özdeş).
    """

    def _referanslar(self):
        import numpy as np
        d = KOK / 'data' / 'cfd_referans'
        for yol in sorted(d.glob('*.npz')):
            import json
            with np.load(yol) as z:
                yield yol.name, json.loads(str(z['meta_json']))

    def test_sevk_edilen_referanslar_TEMIZ_agactan(self):
        for ad, meta in self._referanslar():
            assert meta.get('git_durumu_olculebildi') is True, (
                f'{ad}: künyede git_durumu_olculebildi yok/False — kapı '
                'kurulmadan dondurulmuş (P10B4-14)')
            kirli = meta.get('git_calisma_agaci_kirli')
            assert kirli is False or (
                kirli is True and meta.get('git_kirli_izin_gerekcesi',
                                           '').strip()), (
                f'{ad}: kirli ağaçtan dondurulmuş ve gerekçe yok')

    def test_bekci_kirliligi_DENETLIYOR(self):
        """Kapının geçmişe uygulanması: bekçi kirliliği okuyor mu?"""
        js = (KOK / 'tests' / 'cfd'
              / 'test_euler_bit_ozdesligi.py').read_text(encoding='utf-8')
        assert 'git_calisma_agaci_kirli' in js, (
            'bit-özdeşlik bekçisi künye kirliliğini denetlemiyor — '
            '"kapı var, geçmiş denetlenmiyor" hâli (P10B4-14)')
        assert 'git_durumu_olculebildi' in js
        assert 'git_kirli_izin_gerekcesi' in js

    def test_yeniden_dondurma_URUN_SAYISINI_degistirmedi(self):
        """Provenans işlemi: diziler taban ağacıyla BİT-ÖZDEŞ."""
        import json
        yol = (KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D31' / 'fea-cfd'
               / 'a1' / 'referans_taban_kiyasi.json')
        d = json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))
        assert len(d) == 5, d.keys()
        for ad, kayit in d.items():
            assert kayit['anahtar_farki'] == [], (ad, kayit['anahtar_farki'])
            for dizi, s in kayit['diziler'].items():
                assert s['bit_ozdes'] is True, (ad, dizi, s)
                assert s['maks_fark'] == 0.0, (ad, dizi, s)


# ===========================================================================
# P6B1-10 — kayma duvarı p* pozitiflik kapısı
# ===========================================================================
class TestP6B110DuvarYildizBasinci:
    """ÖLÇÜLDÜ (once_cfd.json K2): dört dondurulmuş referansta en negatif
    duvar M_n = −0,013563 (sok_60x12); eşik −1/γ = −0,833333, uzaklık
    61-124 kat; negatif p* yüzü YOK. Kapı bugünkü ürün akışında
    ateşlemez — ama sessiz emmeyi yakalayacak kanal artık vardır.
    """

    def test_olcum_ANALITIK_degerle_birebir(self):
        """p* = p·(1 + γ·M_n) — D23 ölçümündeki analitik çapa."""
        import numpy as np
        g = 1.2
        p = 1.0e5
        M_n = -1.25 / g
        beklenen = p * (1.0 + g * M_n)     # = -0,25·p = -2,5e4 Pa
        assert beklenen == pytest.approx(-2.5e4, rel=1e-12)
        # Aynı bağıntı fonksiyonun içinde: sentetik tek hücreli duvar.
        from hrma.cfd.euler_core import prim_to_cons_axisym, wall_star_pressure

        class _Grid:
            pass

        rho = g * p / (1.0 * 1.0)          # a = 1 olacak biçimde
        U = prim_to_cons_axisym(
            np.array([[rho]]), np.array([[M_n]]), np.array([[0.0]]),
            np.array([[p]]), g)
        geom = {'wall_n_hat': np.array([[1.0, 0.0]])}
        # Dönüş (M_n, akustik p*, İŞLETİLEN p*, özet) — ÖH D37 A3a cfd-kok-a
        # (F-05; Berke Sunum 3a onayı 24 Eyl): işletilen biçim artık TRRS.
        _, p_star, p_star_2r, ozet = wall_star_pressure(U, _Grid(), g,
                                                        geom=geom)
        # Akustik çapa aynen ölçülür (kıyas sütunu): D23 kusurunun sayısı.
        assert float(p_star[0]) == pytest.approx(beklenen, rel=1e-12)
        assert ozet['akustik_pozitif_mi'] is False
        assert ozet['akustik_negatif_yuz_sayisi'] == 1
        # İŞLETİLEN iki-genişleme aynı durumda POZİTİF → kusur KAPANDI.
        assert float(p_star_2r[0]) > 0.0
        assert ozet['operator'] == 'trrs'
        assert ozet['pozitif_mi'] is True
        assert ozet['negatif_p_star_yuz_sayisi'] == 0

    def test_dondurulmus_referanslarda_kapi_GECIYOR(self):
        """Kapı gerçek ürün alanlarında ateşlemiyor (sabit ret değil)."""
        import json
        yol = (KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D31' / 'fea-cfd'
               / 'a1' / 'sonra_cfd.json')
        d = json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))
        k2 = d['K2_P6B1_10']
        olculen = {k: v for k, v in k2.items() if isinstance(v, dict)
                   and 'min_M_n' in v}
        assert len(olculen) == 4, sorted(olculen)
        for ad, v in olculen.items():
            assert v['negatif_p_yildiz_yuz_sayisi'] == 0, (ad, v)
            assert v['min_M_n'] > v['esik_M_n'], (ad, v)
            assert v['iki_genisleme_hep_pozitif_mi'] is True, ad

    def test_kapi_HUKME_bagli_ve_negatifte_geri_ceker(self):
        """Kapının kendisi: p* ≤ 0 ise converged fail-closed False."""
        import numpy as np

        from hrma.cfd import steady as ST
        from tests.cfd.conftest import EULER_REFERANS_VAKALARI, lule_gridi

        # GERÇEK vaka ayarları: koşum YAKINSIYOR (ölçüldü: 8874 iter,
        # ~5 s). Bütçesi kısılmış bir koşumda hüküm zaten verilmezdi ve
        # kapının sökülmesi ölçülemezdi (ters mutasyon bunu yakaladı).
        vaka = EULER_REFERANS_VAKALARI['izantropik_60x12']
        cozucu = dict(vaka['cozucu'])
        grid = _sessiz(lule_gridi, vaka['ni'], vaka['nj'])
        temiz = _sessiz(ST.solve_steady_axisym, grid, **cozucu)
        assert temiz['converged'] is True, temiz['convergence_basis']
        ws = temiz['wall_star_pressure']
        assert ws['kapi'] is True, ws
        assert ws['hukmu_geri_cekti_mi'] is False
        assert ws['min_M_n'] > ws['esik_M_n']

        gercek = ST.wall_star_pressure

        def _negatif(*a, **kw):
            M_n, p_star, p_2r, ozet = gercek(*a, **kw)
            ozet = dict(ozet)
            ozet['pozitif_mi'] = False
            ozet['negatif_p_star_yuz_sayisi'] = 1
            ozet['min_p_star_Pa'] = -1.0
            return M_n, np.minimum(p_star, -1.0), p_2r, ozet

        ST.wall_star_pressure = _negatif
        try:
            kirli = _sessiz(ST.solve_steady_axisym, grid, **cozucu)
        finally:
            ST.wall_star_pressure = gercek
        assert kirli['converged'] is False
        assert kirli['convergence_status'] == 'wall_star_pressure_nonpositive'
        assert kirli['wall_star_pressure']['hukmu_geri_cekti_mi'] is True
        # Sayılar SİLİNMEZ: alanlar ve kalıntı geçmişi aynen döner.
        assert kirli['iterations'] == temiz['iterations']
        assert np.array_equal(
            np.asarray(kirli['fields']['pressure_Pa']),
            np.asarray(temiz['fields']['pressure_Pa']))
