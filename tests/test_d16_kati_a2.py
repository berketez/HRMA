# -*- coding: utf-8 -*-
"""ÖH Dalga-16 · katı motor · aşama 2 — iki onarımın bekçisi.

Her sınıf TEK bir kalemi tutar ve kalemin ONARIMDAN ÖNCEKİ davranışını
reddeder; onarım geçici olarak geri alındığında (ters mutasyon) kırmızıya
döner. Ölçüm dosyaları: ``docs/scofield/raw/OH/D16/kati/a2/once.json`` ve
``sonra.json``; üreten betik aynı dizindeki ``olcum.py``, ters-mutasyon
kanıtı ``mutasyon.py`` / ``mutasyon.txt``.

Kapsanan kalemler:
  P2B3-06  Boğaz boyutlandırma beyanının referans-vaka yüzdeleri, kodun
           KENDİ ölçümüyle çaprazlanır. ÖLÇÜLDÜ (once.json): metin BATES için
           '+32%' diyordu, aynı vakanın yeniden ölçümü +%0,60 verdi (53 kat);
           star '+65%' ⟷ 70,64 ve wagon wheel '+121%' ⟷ 112,42 de bayattı.
           BATES varsayılan grain tipidir.
  P2B3-08  ``heat_release_rate_mw`` çözülmüş eğrinin bir anına karşılık
           gelir. ÖLÇÜLDÜ (once.json): yayımlanan sayı eğrinin t=0, TEPE ve
           ortalama değerlerinin HİÇBİRİNE eşit değildi (wagon_wheel 14,41 MW
           ⟷ tepe 24,89 MW, tepenin %57,9'u) ve yanında hangi çalışma
           noktası olduğunu söyleyen alan yoktu.
"""

import re
import warnings

import numpy as np
import pytest

from hrma.app import app as flask_app
from hrma.engines.solid_rocket_engine import (
    SOLID_THROAT_SIZING_REFERENCE,
    SOLID_THROAT_SIZING_REFERENCE_TOLERANCE,
    SolidRocketEngine,
)
from hrma.utils.numeric_compat import trapezoid

TIPLER = ('bates', 'slotted', 'star', 'finocyl', 'wagon_wheel')

UC_TABAN = dict(motor_name='D16-KATI-A2', propellant_type='apcp',
                grain_type='bates', chamber_pressure=40.0, thrust=5000.0,
                burn_time=3.0, chamber_diameter=100.0, grain_length=500.0,
                core_diameter=30.0, expansion_ratio=8.0)


def _sessiz(fn, *a, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **kw)


def _referans_motor(grain_type):
    """``SOLID_THROAT_SIZING_REFERENCE``in TARİF ETTİĞİ motor.

    Geometri sabit sayı olarak burada YAZILMAZ; kaydın kendisinden kurulur,
    böylece referans vaka değişirse bekçi otomatik olarak yeni vakayı ölçer.
    """
    r = SOLID_THROAT_SIZING_REFERENCE
    return _sessiz(SolidRocketEngine,
                   grain_type=grain_type,
                   propellant_type=r['propellant_type'],
                   chamber_diameter=r['chamber_diameter_mm'],
                   grain_length=r['grain_length_mm'],
                   core_diameter=r['core_diameter_mm'],
                   chamber_pressure=r['chamber_pressure_bar'])


def _eski_olcut_bogaz_alani(m):
    """v2.6.27 ÖNCESİ ölçüt: A_t = rho_p·Ab(0)·r(Pc)·c*/(Pc·1e5).

    Erozif akı sabit noktası ``_design_throat_detail_uncached`` ile AYNI
    biçimde kurulur; tek fark web = 0'a sabitlenmesidir.
    """
    A_burn = float(m.calculate_burn_area(0.0))
    if A_burn <= 0:
        return None
    A_port = float(m._port_flow_area(0.0))
    port_ratio = (m.D_core / m.D_chamber) if m.D_chamber > 0 else 1.0
    kayit = getattr(m, 'mass_flux', 0.0)
    try:
        m.mass_flux = 0.0
        r = m.burn_rate(m.P_c, m.temp_ref, port_ratio)
        for _ in range(25):
            mdot = m.rho_p * A_burn * r
            m.mass_flux = mdot / A_port if A_port > 0 else 0.0
            r_yeni = m.burn_rate(m.P_c, m.temp_ref, port_ratio)
            if abs(r_yeni - r) < 1e-12:
                r = r_yeni
                break
            r = r_yeni
        mdot = m.rho_p * A_burn * r
        return float(mdot * m.c_star / (m.P_c * 1e5))
    finally:
        m.mass_flux = kayit


@pytest.fixture(scope='module')
def eski_olcut_artislari():
    """Referans vakanın ESKİ ölçütle yeniden ölçülen tepe basıncı artışı [%]."""
    olculen = {}
    for tip in TIPLER:
        m = _referans_motor(tip)
        A_eski = _eski_olcut_bogaz_alani(m)
        assert A_eski and A_eski > 0, f'{tip}: eski ölçüt alanı çözülemedi'
        m.pin_throat_area(A_eski)
        egri = _sessiz(m.calculate_thrust_curve)
        p = np.asarray(egri['pressure'], dtype=float)
        assert p.size, f'{tip}: basınç eğrisi boş'
        olculen[tip] = 100.0 * (float(np.nanmax(p)) / float(m.P_c) - 1.0)
    return olculen


@pytest.fixture(scope='module')
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def _kati_yanit(client, **kw):
    yuk = dict(UC_TABAN)
    yuk.update(kw)
    r = client.post('/calculate_solid', json=yuk)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def kati_yanit(client):
    return _kati_yanit(client)


# ---------------------------------------------------------------------------
# P2B3-06 — boğaz boyutlandırma beyanı ⟷ kodun kendi ölçümü
# ---------------------------------------------------------------------------
class TestBogazBoyutlandirmaBeyaniOlcumeUyar:
    """ÖLÇÜLDÜ (once.json P2B3-06): ``throat_sizing.basis_text``
    '+32% for BATES, +65% star, +87% finocyl, +121% wagon wheel' diyordu.
    Aynı referans vakanın eski ölçütle yeniden çözümü +0,60 / +70,64 /
    +87,24 / +112,42 verdi — BATES'te 53 kat sapma. Beyan üç yerde birden
    (metin, docstring tablosu) elle yazılıyordu; artık TEK KAYNAK
    ``SOLID_THROAT_SIZING_REFERENCE``tır ve bu bekçi onu ölçümle çaprazlar.
    """

    def test_kayitli_yuzdeler_yeniden_olcumle_ayni(self, eski_olcut_artislari):
        mutlak, bagil = SOLID_THROAT_SIZING_REFERENCE_TOLERANCE
        kayitli = SOLID_THROAT_SIZING_REFERENCE['peak_over_design_percent']
        assert set(kayitli) == set(TIPLER), (
            'referans kayıt grain tiplerini eksik/fazla listeliyor')
        for tip, beklenen in sorted(kayitli.items()):
            olculen = eski_olcut_artislari[tip]
            tol = max(mutlak, bagil * abs(beklenen))
            assert abs(olculen - beklenen) <= tol, (
                f'{tip}: kayıtlı referans %{beklenen} ama yeniden ölçüm '
                f'%{olculen:.4f} (tolerans {tol:.4f} puan) — beyan bayatladı')

    def test_bates_beyani_yuzde_otuz_iki_degil(self, eski_olcut_artislari):
        """Kalemin ta kendisi: BATES nötr yanar, aşım yüzde altıda birdir."""
        kayitli = SOLID_THROAT_SIZING_REFERENCE[
            'peak_over_design_percent']['bates']
        assert kayitli < 2.0, (
            f'BATES referans aşımı %{kayitli} — ölçülen '
            f'%{eski_olcut_artislari["bates"]:.4f} ile bağdaşmıyor')
        assert eski_olcut_artislari['bates'] < 2.0

    def test_beyan_metni_kayittan_kurulur(self, kati_yanit):
        """Metindeki her yüzde, yapısal kayıttaki sayının ta kendisidir."""
        ts = kati_yanit['throat_sizing']
        metin = ts['basis_text']
        ref = ts['reference_case']['old_criterion_peak_over_design_percent']
        assert '+32%' not in metin, 'bayat BATES yüzdesi metinde duruyor'
        for tip, deger in ref.items():
            etiket = 'BATES' if tip == 'bates' else tip.replace('_', ' ')
            kalip = r'\+' + re.escape(f'{deger:.1f}') + r'%\s+' + etiket
            assert re.search(kalip, metin), (
                f'{tip}: metin yapısal kayıtla ({deger}) aynı sayıyı taşımıyor')

    def test_yapisal_referans_vaka_yayimlanir(self, kati_yanit):
        """Beyan ⟷ ölçüm çaprazı MAKİNECE kurulabilsin diye."""
        rc = kati_yanit['throat_sizing'].get('reference_case')
        assert rc is not None, 'reference_case yayımlanmıyor'
        r = SOLID_THROAT_SIZING_REFERENCE
        assert rc['chamber_diameter_mm'] == r['chamber_diameter_mm']
        assert rc['core_diameter_mm'] == r['core_diameter_mm']
        assert rc['grain_length_mm'] == r['grain_length_mm']
        assert rc['chamber_pressure_bar'] == r['chamber_pressure_bar']
        assert (rc['old_criterion_peak_over_design_percent']
                == r['peak_over_design_percent'])
        assert rc.get('basis'), 'referans vakanın ne olduğu söylenmiyor'

    def test_referans_vaka_kullanicinin_motoruyla_karistirilmaz(
            self, kati_yanit):
        """Referans sayılar kullanıcının motorunun tepesi DEĞİLDİR."""
        ts = kati_yanit['throat_sizing']
        assert ts.get('peak_over_design') is not None
        assert ts['peak_over_design'] == pytest.approx(1.0, abs=0.05), (
            'maks-Kn ölçütünde kullanıcının kendi tepesi tasarım basıncıdır')

    def test_docstring_referans_sayilari_ikinci_kez_yazmiyor(self):
        """TEK KAYNAK: sayılar ``_design_throat_area`` docstring'inde
        yeniden yazılmaz (iki kopya bayatladığı için kalem açılmıştı)."""
        d = SolidRocketEngine._design_throat_area.__doc__ or ''
        assert 'SOLID_THROAT_SIZING_REFERENCE' in d, (
            'docstring tek kaynağa işaret etmiyor')
        for bayat in ('+%65', '+%87', '+%121', '+%32'):
            assert bayat not in d, f'docstring bayat sayıyı taşıyor: {bayat}'


# ---------------------------------------------------------------------------
# P2B3-08 — ısı açığa çıkma gücü çözülmüş eğrinin BİR anına karşılık gelir
# ---------------------------------------------------------------------------
def _egri_gucleri(tip):
    """(yayımlanan blok, eğriden hesaplanan t0/tepe/ortalama) [MW]."""
    r = SOLID_THROAT_SIZING_REFERENCE
    ortak = dict(propellant_type=r['propellant_type'],
                 chamber_diameter=r['chamber_diameter_mm'],
                 grain_length=r['grain_length_mm'],
                 core_diameter=r['core_diameter_mm'],
                 chamber_pressure=r['chamber_pressure_bar'])
    m = _sessiz(SolidRocketEngine, grain_type=tip, **ortak)
    sonuc = _sessiz(m.calculate_performance)
    ct = sonuc['thermal_analysis']['combustion_thermal']

    m2 = _sessiz(SolidRocketEngine, grain_type=tip, **ortak)
    egri = _sessiz(m2.calculate_thrust_curve)
    t = np.asarray(egri['time'], dtype=float)
    guc = (np.asarray(egri['mass_flow'], dtype=float)
           * float(ct['reaction_enthalpy_mj_kg']))          # MW
    ortalama = (float(trapezoid(guc, t) / (t[-1] - t[0]))
                if t.size > 1 and t[-1] > t[0] else float(np.mean(guc)))
    return ct, {
        't0': float(guc[0]),
        'tepe': float(np.nanmax(guc)),
        'ortalama': ortalama,
        'tepe_zamani': float(t[int(np.argmax(guc))]),
    }


@pytest.fixture(scope='module')
def isi_gucleri():
    return {tip: _egri_gucleri(tip) for tip in TIPLER}


class TestIsiAcigaCikmaGucuEgridenOkunur:
    """ÖLÇÜLDÜ (once.json P2B3-08): ``heat_release_rate_mw`` =
    rho_p·A_burn(w=0)·r(Pc_tasarım)·q — biri t=0 anının yüzeyi, öteki tasarım
    basıncının yanma hızı. v2.6.27/A1-1'den beri tasarım noktası w=0 DEĞİL,
    yani sayı çözülmüş eğrinin hiçbir anına eşit değildi: bates 10,36 ⟷ tepe
    11,20; star 9,75 ⟷ 14,31; wagon_wheel 14,41 ⟷ 24,89 (tepenin %57,9'u).
    Yanında hangi çalışma noktası olduğunu söyleyen alan da yoktu."""

    @pytest.mark.parametrize('tip', TIPLER)
    def test_yayimlanan_deger_egrinin_tepesidir(self, isi_gucleri, tip):
        ct, egri = isi_gucleri[tip]
        yayim = ct['heat_release_rate_mw']
        assert yayim is not None, f'{tip}: güç yayımlanmıyor'
        assert yayim == pytest.approx(egri['tepe'], rel=1e-9), (
            f'{tip}: yayımlanan {yayim:.4f} MW ⟷ eğri tepesi '
            f'{egri["tepe"]:.4f} MW')

    @pytest.mark.parametrize('tip', TIPLER)
    def test_calisma_noktasi_beyan_edilir(self, isi_gucleri, tip):
        ct, _ = isi_gucleri[tip]
        assert ct.get('heat_release_rate_status') == 'solved'
        nokta = ct.get('heat_release_rate_operating_point') or ''
        assert 'peak' in nokta.lower(), (
            f'{tip}: hangi çalışma noktası olduğu söylenmiyor')
        temel = ct.get('heat_release_rate_basis') or ''
        assert 'mdot_gen' in temel and 'q_reaction' in temel

    @pytest.mark.parametrize('tip', TIPLER)
    def test_t0_ve_ortalama_adiyla_yayimlanir(self, isi_gucleri, tip):
        ct, egri = isi_gucleri[tip]
        assert ct['heat_release_rate_initial_mw'] == pytest.approx(
            egri['t0'], rel=1e-9)
        assert ct['heat_release_rate_average_mw'] == pytest.approx(
            egri['ortalama'], rel=1e-9)
        assert ct['heat_release_rate_peak_time_s'] == pytest.approx(
            egri['tepe_zamani'], rel=1e-9)

    def test_ilerleyici_tanecikte_tepe_t0_dan_belirgin_buyuk(self,
                                                            isi_gucleri):
        """Kusurun BÜYÜKLÜĞÜNÜ tutan nöbet: eski formül t=0 yüzeyini
        kullandığı için ilerleyici taneciklerde tepeyi ıskalıyordu."""
        for tip in ('star', 'finocyl', 'wagon_wheel'):
            ct, egri = isi_gucleri[tip]
            assert egri['tepe'] > 1.3 * egri['t0'], (
                f'{tip}: ilerleyici tanecikte tepe t=0 gücünden belirgin '
                f'büyük olmalı')
            assert ct['heat_release_rate_mw'] > 1.2 * ct[
                'heat_release_rate_initial_mw']

    @pytest.mark.parametrize('tip', TIPLER)
    def test_eski_iki_anli_carpim_yayimlanmiyor(self, isi_gucleri, tip):
        """Eski değer: rho_p·Ab(0)·r(Pc_tasarım)·q. Yayımlanan sayı ona
        eşit OLMAMALIDIR (bates dışında tepeden belirgin ayrışır)."""
        r = SOLID_THROAT_SIZING_REFERENCE
        m = _sessiz(SolidRocketEngine, grain_type=tip,
                    propellant_type=r['propellant_type'],
                    chamber_diameter=r['chamber_diameter_mm'],
                    grain_length=r['grain_length_mm'],
                    core_diameter=r['core_diameter_mm'],
                    chamber_pressure=r['chamber_pressure_bar'])
        ct, _ = isi_gucleri[tip]
        ab0 = float(m.calculate_burn_area(0.0))
        eski = (m.rho_p * ab0 * m.burn_rate(m.P_c)
                * float(ct['reaction_enthalpy_mj_kg']))     # MW
        assert ct['heat_release_rate_mw'] != pytest.approx(eski, rel=1e-6), (
            f'{tip}: eski iki-anlı çarpım hâlâ yayımlanıyor ({eski:.4f} MW)')

    def test_egri_yoksa_sayi_uydurulmaz(self):
        """FAIL-CLOSED: çözülmüş eğri yoksa güç alanı YAYIMLANMAZ."""
        r = SOLID_THROAT_SIZING_REFERENCE
        m = _sessiz(SolidRocketEngine, grain_type='bates',
                    propellant_type=r['propellant_type'],
                    chamber_diameter=r['chamber_diameter_mm'],
                    grain_length=r['grain_length_mm'],
                    core_diameter=r['core_diameter_mm'],
                    chamber_pressure=r['chamber_pressure_bar'])
        ct = _sessiz(m._calculate_thermal_analysis)['combustion_thermal']
        assert ct['heat_release_rate_mw'] is None
        assert ct['heat_release_rate_initial_mw'] is None
        assert ct['heat_release_rate_average_mw'] is None
        assert ct['heat_release_rate_status'] == 'not_solved'
        assert ct['heat_release_rate_operating_point'] is None
        assert 'Not published' in (ct['heat_release_rate_basis'] or '')

    def test_bozuk_egri_sessizce_sayiya_donmez(self):
        """Seri eksik/uyumsuzsa da sayı uydurulmaz."""
        for bozuk in ({'time': [], 'mass_flow': []},
                      {'time': [0.0, 1.0], 'mass_flow': [1.0]},
                      {'time': [0.0, 1.0],
                       'mass_flow': [float('nan'), 1.0]},
                      {'time': [0.0, 1.0], 'mass_flow': [0.0, 0.0]}):
            assert SolidRocketEngine._heat_release_power(bozuk, 5.9e6) is None

    def test_uc_yaniti_gucu_ve_kunyesini_tasir(self, kati_yanit):
        ct = kati_yanit['thermal_analysis']['combustion_thermal']
        assert ct['heat_release_rate_status'] == 'solved'
        assert ct['heat_release_rate_mw'] > 0
        assert (ct['heat_release_rate_mw']
                >= ct['heat_release_rate_average_mw'])
        assert (ct['heat_release_rate_mw']
                >= ct['heat_release_rate_initial_mw'])
