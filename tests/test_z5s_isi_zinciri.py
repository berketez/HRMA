"""ÖH Z5S / PK5 — ısı transferi ve rejeneratif soğutma zincirinin bekçileri.

Bu dosya, kırmızı-söndürme paketi **PK5-isi-sogutma-kapisi**nin sekiz
kaleminin ürün onarımını KİLİTLER. Kalemlerin her biri depoda bir
``xfail(strict)`` borç imiyle belgeliydi; onarım sonrası o imler XPASS'a
döndü (kapanış ölçütü). Buradaki bekçiler o imlerin YERİNE geçmez, onların
ÖLÇTÜĞÜNDEN DAHA DAR bir sözleşme kurar:

==========  ============================================================
kalem       burada kilitlenen sözleşme
==========  ============================================================
P4B1-02     ``/api/analysis/wall-profile`` girdi kapıları: fizik dışı ve
            eksik girdi ADIYLA 4xx; uydurulan modül varsayılanı
            ``inputs_assumed`` ile ilan edilir.
P4B1-03     Aynı boğazın tasarım akısı ve gaz-yanı katsayısı TEK sayıdır
            (throat-analizi ⟷ eksenel profil), üç malzemede de.
P4B1-06     Tanınmayan ``cooling_type`` iki uçta da adlandırılmış 422;
            modül ``required_cooling_area = 0,0`` YAYIMLAMAZ.
P4B1-18     ``design_parameters.wall_thickness`` künyelidir.
P4B1-20     ``cooling_efficiency`` künyelidir **ve** tek sayı üç bölgeye
            kopyalanıp çubuk grafiğe dönüştürülmez (sahte gösterge yasağı).
P4B2-01     Ceket ızgarası silindirik kamara gövdesini görür; uç ondan
            haberdar edilebilir.
P4B2-03     Marş fizik dışı sıcaklığa girerse SAYI YAYIMLAMAZ; tablo
            zarfının katlarına çıkan sonuç ADIYLA "model dışı" sayılır.
P4B2-11     İstasyonlar ıslak alanla dağıtılır (her bölüme çözünürlük
            tabanı), yayımlanan toplam ızgaradan bağımsızdır ve
            yayımlanan q(x) dizisinin trapez entegraliyle ÖRTÜŞÜR.
==========  ============================================================

Koşum::

    cd /Users/apple/HRMA-wt/pk5
    MPLBACKEND=Agg PYTHONPATH=. python3 -m pytest tests/test_z5s_isi_zinciri.py -v
"""

import ast
import io
import contextlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import (
    HeatTransferAnalyzer,
    COOLING_DESIGN_DELTA_T,
    COOLING_EFFICIENCY_BY_TYPE,
    SUPPORTED_COOLING_TYPES,
    is_supported_cooling_type,
)
from hrma.analysis.regen_cooling import (
    RegenCooling,
    REGEN_MIN_INTERVALS_PER_SEGMENT,
)

KOK = Path(__file__).resolve().parents[1]
APP_PY = KOK / 'hrma' / 'app.py'


# ======================================================================
# Ortak fikstürler
# ======================================================================
@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _sessiz(fn, *a, **k):
    """Motor/çözücü modülleri stdout'a bolca basıyor; testte sessize al."""
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon), contextlib.redirect_stderr(tampon):
        return fn(*a, **k)


#: Termal uçların ortak, EKSİKSİZ gövdesi (kapılardan geçen sağlıklı yol).
PK5_TAM_GOVDE = {
    'chamber_pressure': 30.0,        # bar
    'chamber_temperature': 3200.0,   # K
    'chamber_diameter': 0.10,        # m
    'chamber_length': 0.40,          # m
    'burn_time': 8.0,                # s
    'mdot_total': 2.0,               # kg/s
    'material': 'steel_4130',
    'wall_thickness': 0.006,         # m
    'cooling_type': 'natural',
    'throat_diameter': 0.03,         # m
    'exit_diameter': 0.09,           # m
    'gamma': 1.22,
    'molecular_weight': 26.0,
}

PK5_MOTOR_VERISI = {k: v for k, v in PK5_TAM_GOVDE.items()
              if k not in ('material', 'wall_thickness', 'cooling_type')}


def _regen(**ek):
    """Sağlıklı su/CuCrZr taban devresi (kamara boyu VERİLMEZ)."""
    kw = dict(chamber_pressure=20e5, chamber_temperature=3000.0, gamma=1.2,
              molecular_weight=24.0, throat_diameter=0.03, expansion_ratio=6.0,
              coolant='water', coolant_mdot=6.0, coolant_inlet_temp=300.0,
              coolant_inlet_pressure=40e5, n_channels=60,
              channel_width=1.5e-3, channel_height=3.0e-3,
              wall_thickness=1.0e-3, wall_material='cucrzr', n_stations=40,
              coolant_props_source='table')
    kw.update(ek)
    return RegenCooling(**kw)


def _regen_yuksek(**ek):
    """ε=25 RP-1/bakır devresi — konverjanın eksenel payı ~%3."""
    kw = dict(chamber_pressure=70e5, chamber_temperature=3500.0, gamma=1.2,
              molecular_weight=22.0, throat_diameter=0.10, expansion_ratio=25.0,
              coolant='rp1', coolant_mdot=8.0, coolant_inlet_temp=300.0,
              coolant_inlet_pressure=120e5, n_channels=100,
              channel_width=2.0e-3, channel_height=3.0e-3,
              wall_thickness=1.0e-3, wall_material='copper', n_stations=50,
              coolant_props_source='table')
    kw.update(ek)
    return RegenCooling(**kw)


def _trapez_islak_integral(res):
    """Yayımlanan üç diziden BAĞIMSIZ trapez ısı entegrali [W].

    Kodun marş şemasını yeniden uygulamaz; yalnız yayımlanan
    ``q_MW_m2`` / ``x_mm`` / ``r_mm`` dizilerini okur.
    """
    x_m = np.asarray(res['x_mm'], dtype=float) / 1e3
    r_m = np.asarray(res['r_mm'], dtype=float) / 1e3
    q = np.asarray(res['q_MW_m2'], dtype=float) * 1e6
    ds = np.hypot(np.diff(x_m), np.diff(r_m))
    r_ort = 0.5 * (r_m[:-1] + r_m[1:])
    q_ort = 0.5 * (q[:-1] + q[1:])
    return float(np.sum(q_ort * 2.0 * math.pi * r_ort * ds))


def _govde_metni(yanit):
    return yanit.get_data(as_text=True)


# ======================================================================
# 1) P4B1-02 — /api/analysis/wall-profile girdi kapıları
# ======================================================================
class TestCidarProfiliKapisi:
    """Fizik dışı ve eksik girdiden PROFİL YAYIMLANMAZ."""

    YOL = '/api/analysis/wall-profile'

    @pytest.mark.parametrize('alan,deger', [
        ('chamber_temperature', -3000.0),
        ('chamber_pressure', -60.0),
        ('wall_thickness', -0.01),
        ('chamber_diameter', 0.0),
        ('mdot_total', 0.0),
        ('burn_time', -1.0),
    ])
    def test_fizik_disi_girdi_adli_4xx(self, client, alan, deger):
        """Ölçülen kusur: −3000 K girdide T_wall_eq −530 K, HTTP 200."""
        r = _sessiz(client.post, self.YOL, json=dict(PK5_TAM_GOVDE, **{alan: deger}))
        assert r.status_code == 422, _govde_metni(r)[:300]
        govde = r.get_json()
        assert govde['error'] == 'invalid_wall_profile_input'
        assert alan in _govde_metni(r), (
            f'{alan} yanıtta adlandırılmamış: {_govde_metni(r)[:300]}')
        # Fail-closed: hiçbir profil alanı üretilmemeli.
        assert 'wall_profile' not in govde

    def test_ust_sinir_ihlali_de_reddedilir(self, client):
        """Kardeş uçla aynı üst sınır kapısı (S3 onarımı buraya da geldi)."""
        r = _sessiz(client.post, self.YOL,
                    json=dict(PK5_TAM_GOVDE, chamber_pressure=1e9))
        assert r.status_code == 422, _govde_metni(r)[:300]
        assert 'chamber_pressure' in _govde_metni(r)

    @pytest.mark.parametrize('eksik', [
        'chamber_pressure', 'chamber_temperature', 'chamber_diameter',
        'chamber_length', 'burn_time',
    ])
    def test_eksik_cekirdek_alan_adli_422(self, client, eksik):
        yuk = {k: v for k, v in PK5_TAM_GOVDE.items() if k != eksik}
        r = _sessiz(client.post, self.YOL, json=yuk)
        assert r.status_code == 422, _govde_metni(r)[:300]
        govde = r.get_json()
        assert govde['error'] == 'incomplete_wall_profile_input'
        assert eksik in govde['missing_fields'], govde['missing_fields']
        assert 'wall_profile' not in govde

    def test_bos_govde_profil_uretmez(self, client):
        """``{}`` bir motor değildir: 20 bar / 3000 K / 1 kg/s uydurulmaz."""
        r = _sessiz(client.post, self.YOL, json={})
        assert r.status_code == 422, _govde_metni(r)[:300]
        assert r.get_json()['missing_fields']

    def test_bogaz_olcegi_grubu_ANY_OF_olarak_bildirilir(self, client):
        """mdot/throat_diameter/throat_area üçlüsü: biri yeterli."""
        yuk = {k: v for k, v in PK5_TAM_GOVDE.items()
               if k not in ('mdot_total', 'throat_diameter')}
        r = _sessiz(client.post, self.YOL, json=yuk)
        assert r.status_code == 422
        gruplar = r.get_json()['missing_field_groups']
        assert any('mdot_total' in g['any_of'] for g in gruplar), gruplar

    def test_saglikli_govde_200_ve_BEYAN_ALANI_YOK(self, client):
        """Tam gövdede uydurma beyan alanı doğmaz (gövde bit-aynı kalır).

        ÖH D27 / OH-D25-13 — GÖVDE TANIMI TAZELENDİ (iddia GEVŞEMEDİ).
        ``PK5_TAM_GOVDE`` PK5'te yazıldığında bu uç ışıyan tür
        kompozisyonunu HENÜZ TÜKETMİYORDU; OH-D19-07 ``x_H2O``/``x_CO2``
        yolunu açtı ve OH-D25-13 kökeni ilan ettirdi. Yani kesirler
        gönderilmeyen bir gövde artık "tam" DEĞİLDİR: iki girdi modül
        varsayılanına düşer ve akıyı kaydırır (ölçüldü,
        ``raw/OH/D27/termo-ucus/a1/once.json`` K2: q_MW tepe 35,508897 ⟷
        35,794164 MW/m²). Bu bekçi "sağlıklı yol künye üretmez" diyordu;
        bu doğru kaldı, ama SAĞLIKLI GÖVDE artık kesirleri de içerir.
        Aşağıdaki ikinci iddia, kesirsiz gövdenin künyeyi GERÇEKTEN
        ürettiğini kilitler — yani bu değişiklik daraltmadır.
        """
        tam = dict(PK5_TAM_GOVDE, x_H2O=0.30, x_CO2=0.12)
        r = _sessiz(client.post, self.YOL, json=tam)
        assert r.status_code == 200, _govde_metni(r)[:300]
        govde = r.get_json()
        assert 'inputs_assumed' not in govde
        assert 'inputs_treated_as_absent' not in govde
        assert len(govde['wall_profile']['x_mm']) == 40

    def test_kesirsiz_govde_KOMPOZISYON_KOKENINI_soyler(self, client):
        """OH-D25-13: kesirler düşerse künye ADIYLA doğar (tersi değil)."""
        r = _sessiz(client.post, self.YOL, json=dict(PK5_TAM_GOVDE))
        assert r.status_code == 200, _govde_metni(r)[:300]
        beyan = r.get_json()['inputs_assumed']
        assert {k['field'] for k in beyan} == {'x_H2O', 'x_CO2'}, beyan

    def test_modul_varsayilani_ADIYLA_ilan_edilir(self, client):
        """``wall_thickness`` zorunlu DEĞİL ama sessiz de değil.

        Bu ucun canlı tüketicisi (termal FEA paneli) cidar kalınlığı
        göndermiyor; zorunlu kılmak zinciri koparırdı. Sözleşme bu yüzden
        "ya reddet ya SÖYLE"nin ikinci dalıdır.
        """
        yuk = {k: v for k, v in PK5_TAM_GOVDE.items()
               if k not in ('wall_thickness', 'cooling_type')}
        r = _sessiz(client.post, self.YOL, json=yuk)
        assert r.status_code == 200, _govde_metni(r)[:300]
        beyan = r.get_json()['inputs_assumed']
        adlar = {kayit['field'] for kayit in beyan}
        assert {'wall_thickness', 'cooling_type'} <= adlar, adlar
        cidar = next(k for k in beyan if k['field'] == 'wall_thickness')
        assert cidar['assumed_value_m'] == pytest.approx(0.005)
        assert 'conduction' in cidar['reason'].lower()

    def test_yayimlanan_profil_MUTLAK_sicaklik_tasir(self, client):
        """Kapının amacı: fizik dışı sayı hiçbir dalda yayımlanmaz."""
        r = _sessiz(client.post, self.YOL, json=dict(PK5_TAM_GOVDE))
        profil = r.get_json()['wall_profile']
        for anahtar in ('T_wall_eq', 'T_recovery'):
            deger = np.asarray(profil[anahtar], dtype=float)
            assert np.all(np.isfinite(deger)) and np.all(deger > 0.0)
        assert profil['wall_thickness_mm'] > 0.0


# ======================================================================
# 2) P4B1-03 — aynı boğaz, TEK tasarım akısı ve TEK h_g
# ======================================================================
class TestBogazTekTanim:
    """İki kanal (throat-analizi ⟷ eksenel profil) ayrışamaz.

    Eski bekçi %1 toleransla ölçüyordu; onarım TEK TANIM NOKTASI kurduğu
    için tolerans sayısal gürültüye indirildi. Hangi kanalın "doğru"
    olduğuna bu bekçi HÜKMETMEZ.
    """

    @pytest.mark.parametrize('malzeme', ['steel_4130', 'copper', 'inconel_718'])
    def test_tasarim_akisi_tek_sayi(self, malzeme):
        a = HeatTransferAnalyzer()
        tam = a.analyze_heat_transfer(dict(PK5_MOTOR_VERISI), material=malzeme,
                                      wall_thickness=0.006,
                                      cooling_type='natural')
        profil = a.analyze_axial_profile(dict(PK5_MOTOR_VERISI), n_stations=40,
                                         material=malzeme,
                                         wall_thickness=0.006,
                                         cooling_type='natural')
        q_tam = tam['gas_side_analysis']['throat_heat_flux']
        q_profil = profil['q_MW'][profil['throat_index']] * 1e6
        assert q_profil == pytest.approx(q_tam, rel=1e-6), (
            f'{malzeme}: boğaz tasarım akısı ayrışıyor '
            f'{q_tam / 1e6:.6f} ⟷ {q_profil / 1e6:.6f} MW/m²')

    @pytest.mark.parametrize('malzeme', ['steel_4130', 'copper', 'inconel_718'])
    def test_gaz_yani_katsayisi_tek_sayi(self, malzeme):
        a = HeatTransferAnalyzer()
        tam = a.analyze_heat_transfer(dict(PK5_MOTOR_VERISI), material=malzeme,
                                      wall_thickness=0.006,
                                      cooling_type='natural')
        profil = a.analyze_axial_profile(dict(PK5_MOTOR_VERISI), n_stations=40,
                                         material=malzeme,
                                         wall_thickness=0.006,
                                         cooling_type='natural')
        h_tam = tam['heat_transfer_coefficients']['gas_side']
        h_profil = profil['h_g'][profil['throat_index']]
        assert h_profil == pytest.approx(h_tam, rel=1e-6), (
            f'{malzeme}: boğaz h_g ayrışıyor {h_tam:.4f} ⟷ {h_profil:.4f}')

    def test_referans_cidar_sicakligi_YAYIMLANIYOR(self):
        """h_g'nin hangi cidarda kurulduğu artık okunabilir bir sayıdır."""
        a = HeatTransferAnalyzer()
        tam = a.analyze_heat_transfer(dict(PK5_MOTOR_VERISI), material='steel_4130',
                                      wall_thickness=0.006,
                                      cooling_type='natural')
        katsayilar = tam['heat_transfer_coefficients']
        gaz = tam['gas_side_analysis']
        assert katsayilar['gas_side_reference_wall_temperature'] == \
            pytest.approx(gaz['reference_wall_temperature'], rel=1e-12)

    def test_referans_cidar_tek_islevden(self):
        """Tanım noktası ORTAK: iki kanal aynı işlevi çağırır."""
        a = HeatTransferAnalyzer()
        assert a._design_reference_wall_temperature(1000.0, 3000.0, 293.15) \
            == pytest.approx(1000.0)
        # Taw düşükse tavan %80·Taw'dır (iyi soğutulmuş cidar Taw altındadır)
        assert a._design_reference_wall_temperature(1000.0, 900.0, 293.15) \
            == pytest.approx(720.0)
        # Ortam sıcaklığı taban
        assert a._design_reference_wall_temperature(1000.0, 100.0, 293.15) \
            == pytest.approx(293.15)


# ======================================================================
# 3) P4B1-06 — tanınmayan soğutma tipi
# ======================================================================
class TestSogutmaTipiKapisi:

    DESTEKSIZ = ['film', 'ablative', 'radiation', 'kırmızı balık', 'none']

    def test_beyaz_liste_TEK_kaynak(self):
        """Eşik listesi modülde; uç onu kopyalamaz, okur."""
        assert set(SUPPORTED_COOLING_TYPES) == set(COOLING_DESIGN_DELTA_T)
        assert set(SUPPORTED_COOLING_TYPES) == set(COOLING_EFFICIENCY_BY_TYPE)
        for tip in SUPPORTED_COOLING_TYPES:
            assert is_supported_cooling_type(tip)
            assert is_supported_cooling_type(tip.upper())
        for tip in self.DESTEKSIZ:
            assert not is_supported_cooling_type(tip)
        assert not is_supported_cooling_type(None)

    @pytest.mark.parametrize('yol', ['/analyze_thermal_safety',
                                     '/api/analysis/wall-profile'])
    @pytest.mark.parametrize('tip', DESTEKSIZ)
    def test_desteksiz_tip_adli_422(self, client, yol, tip):
        r = _sessiz(client.post, yol, json=dict(PK5_TAM_GOVDE, cooling_type=tip))
        assert r.status_code == 422, _govde_metni(r)[:300]
        govde = r.get_json()
        assert govde['error'] == 'unsupported_cooling_type'
        (kayit,) = govde['invalid_fields']
        assert kayit['field'] == 'cooling_type'
        assert set(kayit['allowed_values']) == set(SUPPORTED_COOLING_TYPES)
        # Fail-closed: hiçbir hüküm/profil üretilmedi.
        assert 'thermal_analysis' not in govde
        assert 'wall_profile' not in govde

    @pytest.mark.parametrize('tip', ['natural', 'forced', 'regenerative'])
    def test_taninan_tip_hala_hukum_uretir(self, client, tip):
        r = _sessiz(client.post, '/analyze_thermal_safety',
                    json=dict(PK5_TAM_GOVDE, cooling_type=tip))
        assert r.status_code == 200, _govde_metni(r)[:300]
        cool = r.get_json()['thermal_analysis']['cooling_analysis']
        assert cool['cooling_type_recognized'] is True
        assert cool['required_cooling_area'] > 0.0

    def test_modul_SIFIR_ALAN_yayimlamaz(self):
        """0,0 m² bir ölçüm değildir: alan geri çekilir, gerekçesi yazılır."""
        a = HeatTransferAnalyzer()
        cool = a._analyze_cooling_requirements(
            heat_rate=3.37e6, burn_time=8.0, motor_data={},
            cooling_type='film', mat_props=None)
        assert cool['required_cooling_area'] is None
        assert cool['cooling_type_recognized'] is False
        gerekce = cool['required_cooling_area_withheld_because']
        assert 'film' in gerekce and 'regenerative' in gerekce

    def test_modul_ETKINLIK_de_uydurmaz(self):
        """Tanınmayan tipte doğal taşınımın 0,3'üne DÜŞÜLMEZ."""
        a = HeatTransferAnalyzer()
        assert a._calculate_cooling_efficiency('film') is None
        assert a._calculate_cooling_efficiency('natural') == pytest.approx(0.3)


# ======================================================================
# 4) P4B1-18 — cidar kalınlığı künyesi
# ======================================================================
class TestCidarKalinligiKunyesi:

    @pytest.fixture(scope='class')
    def termal(self, client):
        r = _sessiz(client.post, '/analyze_thermal_safety',
                    json=dict(PK5_TAM_GOVDE))
        assert r.status_code == 200, _govde_metni(r)[:300]
        return r.get_json()['thermal_analysis']

    def test_kunye_var_ve_YANKI_oldugunu_soyluyor(self, termal):
        dp = termal['design_parameters']
        assert 'wall_thickness_basis' in dp
        metin = dp['wall_thickness_basis'].lower()
        assert 'input' in metin
        assert 'default' in metin and '5.0 mm' in metin
        # Kardeşiyle aynı sınıfta: ikisi de girdi yankısıdır.
        assert 'ambient_temperature_basis' in dp

    def test_kunye_asimetrisi_KAPANDI(self, termal):
        """İki yankı alanının ikisi de künyeli (ölçülen asimetri 1/1 idi)."""
        dp = termal['design_parameters']
        yanki = [ad for ad in ('wall_thickness', 'ambient_temperature')]
        kunyesiz = [ad for ad in yanki if f'{ad}_basis' not in dp]
        assert not kunyesiz, kunyesiz


# ======================================================================
# 5) P4B1-20 — soğutma etkinliği künyesi + SAHTE GÖSTERGE YASAĞI
# ======================================================================
class TestSogutmaEtkinligi:

    @pytest.fixture(scope='class')
    def cooling(self, client):
        r = _sessiz(client.post, '/analyze_thermal_safety',
                    json=dict(PK5_TAM_GOVDE))
        assert r.status_code == 200, _govde_metni(r)[:300]
        return r.get_json()['thermal_analysis']['cooling_analysis']

    def test_kunye_var(self, cooling):
        assert 'cooling_efficiency_basis' in cooling
        assert 'cooling_efficiency_source' in cooling

    def test_kunye_OLCUM_OLMADIGINI_soyluyor(self, cooling):
        metin = (cooling['cooling_efficiency_basis'] + ' '
                 + cooling['cooling_efficiency_source']).lower()
        assert 'not a computed' in metin or 'ordering figure' in metin
        assert 'no literature correlation' in metin
        # Bölgesel çözünürlüğün OLMADIĞI açıkça yazılı olmalı — sahte
        # göstergenin geri gelmesini engelleyen cümle budur.
        assert 'zonal' in metin or 'per-zone' in metin

    def test_APP_PY_tek_sayiyi_uc_bolgeye_KOPYALAMIYOR(self):
        """Sahte gösterge kaynağı app.py'da ÜRETİLMEZ (AST ile ölçülür).

        Eski kalıp::

            ca['zones'] = ['Chamber', 'Throat', 'Nozzle']
            ca['effectiveness'] = [ca.get('cooling_efficiency', 0.8)] * 3

        Tek bir sayı üç bölgeye kopyalanıyor ve "Cooling Effectiveness"
        çubuk grafiği bu üç ÖZDEŞ kopyadan çiziliyordu.
        """
        agac = ast.parse(APP_PY.read_text(encoding='utf-8'))
        atamalar = []
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Assign):
                continue
            for hedef in dugum.targets:
                if (isinstance(hedef, ast.Subscript)
                        and isinstance(hedef.slice, ast.Constant)
                        and hedef.slice.value in ('effectiveness', 'zones')):
                    atamalar.append(ast.dump(dugum)[:120])
        assert not atamalar, (
            'app.py hâlâ soğutma göstergesi ÜRETİYOR: %s' % atamalar)

    def test_ANALIZ_UCU_uydurma_gosterge_yayimlamiyor(self, client):
        """Canlı ölçüm: /api/advanced-analysis üç-bölge kopyası basmaz."""
        r = _sessiz(client.post, '/api/advanced-analysis', json=dict(
            analysis_types=['heat_transfer'],
            material_type='steel_4130', wall_thickness=0.006,
            cooling_type='natural', motor_data=dict(PK5_MOTOR_VERISI)))
        assert r.status_code == 200, _govde_metni(r)[:300]
        govde = r.get_json()
        cool = govde['results']['heat_analysis']['cooling_analysis']
        assert 'effectiveness' not in cool
        assert 'zones' not in cool
        # Gerçek (tek, sınıf düzeyinde) sayı künyesiyle YERİNDE.
        assert cool['cooling_efficiency'] == pytest.approx(
            COOLING_EFFICIENCY_BY_TYPE['natural'])
        assert cool['cooling_efficiency_basis']

    def test_GRAFIK_gercek_veri_yoksa_cizilmiyor(self, client):
        """Çubuk grafiğin kendisi de üretilmemeli (sahte-veri yasağı)."""
        r = _sessiz(client.post, '/api/advanced-analysis', json=dict(
            analysis_types=['heat_transfer'],
            material_type='steel_4130', wall_thickness=0.006,
            cooling_type='natural', motor_data=dict(PK5_MOTOR_VERISI)))
        plot = json.loads(
            r.get_json()['results']['heat_transfer_plot'])
        etiketler = {iz.get('name') for iz in plot.get('data', [])}
        assert 'Cooling Effectiveness' not in etiketler, etiketler


# ======================================================================
# 6) P4B2-01 — ceket, silindirik kamara gövdesini görür
# ======================================================================
class TestCeketGovdeyiGoruyor:

    ORTAK = dict(coolant='water', coolant_mdot=6.0, coolant_inlet_temp=300.0,
                 coolant_inlet_pressure=40e5, n_channels=60,
                 channel_width=1.5e-3, channel_height=3.0e-3,
                 wall_thickness=1.0e-3, wall_material='cucrzr', n_stations=40,
                 coolant_props_source='table')
    MD = dict(chamber_pressure=20.0, chamber_temperature=3000.0, gamma=1.2,
              molecular_weight=24.0, throat_diameter=0.03, expansion_ratio=6.0,
              chamber_diameter=0.045)

    def _kos(self, boy_m):
        return RegenCooling.from_motor_data(
            dict(self.MD, chamber_length=boy_m), **self.ORTAK).solve()

    def test_izgara_govdeyi_kapsiyor(self):
        res = self._kos(0.40)
        aciklik = float(res['x_mm'][-1]) - float(res['x_mm'][0])
        assert aciklik > 400.0, (
            f'ızgara {aciklik:.2f} mm kaplıyor; yalnız 400 mm gövde bile '
            'bundan uzun')

    def test_isi_yuku_kamara_boyuna_DUYARLI(self):
        kisa = self._kos(0.10)['summary']['total_heat_W']
        uzun = self._kos(0.40)['summary']['total_heat_W']
        assert uzun > 1.5 * kisa, (
            f'0,10 m -> 0,40 m: {kisa:.3f} W -> {uzun:.3f} W')

    def test_kamara_boyu_YOKSA_davranis_degismez(self):
        """Gövde uydurulmaz: boy verilmezse ceket lüleyle sınırlı kalır."""
        res = RegenCooling.from_motor_data(dict(self.MD), **self.ORTAK).solve()
        assert float(res['x_mm'][0]) == pytest.approx(0.0, abs=1e-9)
        assert 'NOZZLE CONTOUR ONLY' in res['model_note']

    @pytest.mark.parametrize('bozuk', [None, '', 0, -0.2, float('nan'), True,
                                       'uzun'])
    def test_bozuk_kamara_boyu_GOVDE_URETMEZ(self, bozuk):
        res = RegenCooling.from_motor_data(
            dict(self.MD, chamber_length=bozuk), **self.ORTAK).solve()
        assert float(res['x_mm'][0]) == pytest.approx(0.0, abs=1e-9)

    def test_kunye_govdeyi_ADIYLA_soyluyor(self):
        res = self._kos(0.40)
        assert 'cylindrical chamber barrel' in res['model_note']
        assert '400.0 mm' in res['model_note']

    def test_UC_kamara_boyunu_gecirebiliyor(self, client):
        """Kalem notunun ikinci ayağı: uçtan gövdeye ULAŞAN alan vardı YOK.

        ``/api/regen-cooling`` artık ``chamber_length`` kabul ediyor; alan
        verilmezse yanıt BİT-AYNI kalır.
        """
        taban = {'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
                 'throat_diameter': 0.03, 'expansion_ratio': 6.0,
                 'gamma': 1.2, 'molecular_weight': 24.0, 'coolant': 'water',
                 'coolant_mdot': 6.0, 'coolant_inlet_temp': 300.0,
                 'coolant_inlet_pressure': 40.0, 'n_channels': 60,
                 'channel_width': 1.5, 'channel_height': 3.0,
                 'wall_thickness': 1.0, 'wall_material': 'cucrzr'}
        yok = _sessiz(client.post, '/api/regen-cooling', json=dict(taban))
        var = _sessiz(client.post, '/api/regen-cooling',
                      json=dict(taban, chamber_length=0.40,
                                chamber_diameter=0.045))
        assert yok.status_code == var.status_code == 200
        q_yok = yok.get_json()['cooling']['summary']['total_heat_W']
        q_var = var.get_json()['cooling']['summary']['total_heat_W']
        assert q_var > 1.5 * q_yok, (q_yok, q_var)


# ======================================================================
# 7) P4B2-03 — marşta fizik kapısı ve model zarfı
# ======================================================================
class TestMarsFizikKapisi:

    def _patolojik(self):
        return RegenCooling(
            chamber_pressure=70e5, chamber_temperature=3500.0, gamma=1.2,
            molecular_weight=22.0, throat_diameter=0.10, expansion_ratio=25.0,
            coolant='rp1', coolant_mdot=1e-9, coolant_inlet_temp=300.0,
            coolant_inlet_pressure=100e5, n_channels=100,
            channel_width=2.0e-3, channel_height=3.0e-3,
            wall_thickness=1.0e-3, wall_material='copper', n_stations=40,
            coolant_props_source='table')

    def test_negatif_mutlak_sicaklik_SAYI_YAYIMLAMAZ(self):
        """Ölçülen kusur: T_coolant min −3.178.605 K, HTTP 200, 4 uyarı."""
        with pytest.raises(ValueError) as hata:
            self._patolojik().solve()
        metin = str(hata.value).lower()
        assert 'absolute temperature scale' in metin
        assert 'coolant_mdot' in metin      # nedeni ADIYLA söyleniyor

    def test_UC_patolojik_devrede_adli_4xx(self, client):
        r = _sessiz(client.post, '/api/regen-cooling', json={
            'chamber_pressure': 70.0, 'chamber_temperature': 3500.0,
            'throat_diameter': 0.10, 'expansion_ratio': 25.0,
            'gamma': 1.2, 'molecular_weight': 22.0, 'coolant': 'rp1',
            'coolant_mdot': 1e-9, 'coolant_inlet_temp': 300.0,
            'coolant_inlet_pressure': 100.0, 'n_channels': 100,
            'channel_width': 2.0, 'channel_height': 3.0,
            'wall_thickness': 1.0, 'wall_material': 'copper'})
        assert 400 <= r.status_code < 500, _govde_metni(r)[:200]
        assert 'cooling' not in r.get_json()

    def test_saglikli_devre_hala_POZITIF_sicaklik(self):
        res = _regen().solve()
        for anahtar in ('T_coolant_K', 'T_wall_hot_K', 'T_wall_cold_K'):
            deger = np.asarray(res[anahtar], dtype=float)
            assert np.all(np.isfinite(deger)) and np.all(deger > 0.0)

    def test_zarf_disi_sonuc_ADIYLA_model_disi(self):
        """Tavanın katlarına çıkan sıcaklık 'dondurulmuş özellik' değildir."""
        s = _regen_yuksek(throat_diameter=0.06, coolant_mdot=0.01,
                          n_channels=100, channel_width=1.5e-3,
                          n_stations=40).solve()['summary']
        tavan = s['property_table_band_K'][1]
        assert s['coolant_exit_temp_K'] > 2.0 * tavan
        hukum = [w for w in s['warnings'] if 'MODEL OUT OF ENVELOPE' in w]
        assert hukum, s['warnings']
        assert 'NOT MODELLED' in hukum[0]

    def test_zarf_esigi_TABLODAN_turetiliyor(self):
        """Eşik uydurulmuş bir sayı değil, bandın kendi genişliğidir."""
        s = _regen_yuksek(throat_diameter=0.06, coolant_mdot=0.01,
                          n_channels=100, channel_width=1.5e-3,
                          n_stations=40).solve()['summary']
        alt, ust = s['property_table_band_K']
        beklenen = ust + (ust - alt)
        hukum = [w for w in s['warnings'] if 'MODEL OUT OF ENVELOPE' in w][0]
        assert f'beyond {beklenen:.0f} K' in hukum, hukum

    def test_bant_ICINDE_zarf_hukmu_YOK(self):
        """Yanlış alarm yok: sağlıklı devrede model-dışı hükmü doğmaz."""
        s = _regen().solve()['summary']
        assert not [w for w in s['warnings'] if 'MODEL OUT OF ENVELOPE' in w]


# ======================================================================
# 8) P4B2-11 — ızgara dağıtımı ve kuadratür
# ======================================================================
class TestIzgaraVeKuadratur:

    def test_konverjan_bolum_COZULUYOR(self):
        """ε=25 lülede konverjan tek segmente sıkışamaz."""
        for n in (20, 30, 40, 50):
            res = _regen_yuksek(n_stations=n).solve()
            assert res['throat_index'] >= REGEN_MIN_INTERVALS_PER_SEGMENT, (
                f'n={n}: throat_index={res["throat_index"]}')

    def test_yayimlanan_toplam_IZGARADAN_BAGIMSIZ(self):
        az = _regen_yuksek(n_stations=20).solve()['summary']['total_heat_W']
        cok = _regen_yuksek(n_stations=50).solve()['summary']['total_heat_W']
        assert az == pytest.approx(cok, rel=1e-2), (
            f'Q(20)={az:.1f} ⟷ Q(50)={cok:.1f} '
            f'(%{100 * abs(az / cok - 1):.3f})')

    @pytest.mark.parametrize('kur', [_regen, _regen_yuksek])
    def test_toplam_yayimlanan_dizinin_TRAPEZ_ENTEGRALI(self, kur):
        """Aynı büyüklük iki kanaldan yayımlanıyorsa AYRIŞAMAZ."""
        res = kur().solve()
        q_pub = res['summary']['total_heat_W']
        q_trapez = _trapez_islak_integral(res)
        assert q_trapez == pytest.approx(q_pub, rel=1e-6), (
            f'trapez {q_trapez:.3f} W ⟷ yayımlanan {q_pub:.3f} W '
            f'(%{100 * abs(q_trapez / q_pub - 1):.5f})')

    def test_KUNYE_kuadraturu_soyluyor(self):
        note = _regen().solve()['model_note']
        assert 'TRAPEZOIDAL' in note
        assert 'fixed point' in note
        assert 'WETTED AREA' in note

    def test_entalpi_ozdesligi_KORUNDU(self):
        """Şema değişti ama enerji dengesi özdeşliği şemadan bağımsızdır."""
        res = _regen().solve()
        s = res['summary']
        assert s['total_heat_W'] == pytest.approx(
            6.0 * s['coolant_cp_mean_J_kgK'] * s['coolant_dT_K'], rel=1e-9)

    @staticmethod
    def _pay_tahmini(agirliklar, toplam_aralik, taban):
        """Beyan edilen dağıtım kuralının BAĞIMSIZ yeniden hesabı.

        Kural (``_build_stations`` künyesi): her bölüme ``taban`` aralık,
        kalanlar ağırlıklara göre en-büyük-artık (Hamilton) yöntemiyle.
        """
        kalan = toplam_aralik - taban * len(agirliklar)
        araliklar = [taban] * len(agirliklar)
        if kalan > 0:
            toplam = sum(agirliklar)
            paylar = [kalan * w / toplam for w in agirliklar]
            tam = [int(math.floor(p)) for p in paylar]
            artik = kalan - sum(tam)
            sira = sorted(range(len(paylar)),
                          key=lambda i: -(paylar[i] - tam[i]))
            for i in sira[:artik]:
                tam[i] += 1
            araliklar = [araliklar[i] + tam[i] for i in range(len(agirliklar))]
        return araliklar

    @pytest.mark.parametrize('n', [20, 50])
    def test_paylar_ISLAK_ALANDAN_dagitiliyor(self, n):
        """Dağıtım ölçüsü ıslak yüzey alanıdır, eksenel uzunluk DEĞİL.

        Bekçi kuralı bağımsız yeniden uygular ve İKİ ölçünün İKİ FARKLI
        ızgara verdiğini ön koşul olarak ölçer; aksi hâlde iddia ayırt
        edici olmazdı. Bu devrede (ε=25) alan payı %2,68, eksenel pay
        %5,47 — yani alan ölçüsü konverjanı BÜYÜTMEZ, sadece doğru
        ölçüdür (garanti tabandan gelir, aşağıdaki bekçi).
        """
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour

        r = _regen_yuksek(n_stations=n)
        geo = r._build_stations()
        md = dict(r.motor_data)
        md['throat_diameter'] = r.throat_diameter
        md['exit_diameter'] = r.exit_diameter
        md.setdefault('chamber_diameter', 1.5 * r.throat_diameter)
        pts, meta = sample_nozzle_inner_contour(md)
        z = np.array([p[0] for p in pts], dtype=float)
        rr = np.array([p[1] for p in pts], dtype=float)
        z0 = float(z[0])
        z_t = float(meta['z_throat'])
        z_e = float(meta['z_exit'])

        alan = [RegenCooling._wetted_area_mm2(z, rr, z0, z_t),
                RegenCooling._wetted_area_mm2(z, rr, z_t, z_e)]
        boy = [z_t - z0, z_e - z_t]
        toplam_aralik = geo['x_mm'].size - 1
        taban = REGEN_MIN_INTERVALS_PER_SEGMENT

        alan_tahmini = self._pay_tahmini(alan, toplam_aralik, taban)[0]
        boy_tahmini = self._pay_tahmini(boy, toplam_aralik, taban)[0]
        assert alan_tahmini != boy_tahmini, (
            'ön koşul: bu devrede iki ölçü aynı ızgarayı veriyor, iddia '
            f'ayırt edici değil ({alan_tahmini} == {boy_tahmini})')
        assert geo['throat_index'] == alan_tahmini, (
            f'n={n}: boğaz indeksi {geo["throat_index"]}; ıslak alan '
            f'{alan_tahmini}, eksenel uzunluk {boy_tahmini} öngörüyor')

    def test_cozunurluk_TABANI_her_bolumde(self):
        """Taban garantisi: hiçbir bölüm tek aralığa sıkışmaz."""
        geo = _regen_yuksek(n_stations=20)._build_stations()
        toplam_aralik = geo['x_mm'].size - 1
        assert geo['throat_index'] >= REGEN_MIN_INTERVALS_PER_SEGMENT
        assert (toplam_aralik - geo['throat_index']) \
            >= REGEN_MIN_INTERVALS_PER_SEGMENT

    def test_mars_yakinsadi(self):
        """Sabit nokta ölçütü gerçekten kapanıyor (üst sınıra dayanmıyor)."""
        # Yakınsamış bir marşta yayımlanan toplam trapez entegraliyle
        # sayısal gürültü mertebesinde örtüşür; bu, iterasyonun bittiğinin
        # ürün-tarafı kanıtıdır.
        res = _regen().solve()
        assert abs(_trapez_islak_integral(res)
                   / res['summary']['total_heat_W'] - 1.0) < 1e-9


# ======================================================================
# 9) Bekçi hijyeni: kapılar GEÇERLİ gövdeyi bozmuyor
# ======================================================================
def test_gecerli_govde_hala_tam_termal_hukum_uretir(client):
    """Sekiz kalemin hiçbiri sağlıklı yolu kapatmadı."""
    r = _sessiz(client.post, '/analyze_thermal_safety', json=dict(PK5_TAM_GOVDE))
    assert r.status_code == 200, _govde_metni(r)[:300]
    ta = r.get_json()['thermal_analysis']
    assert ta['safety_analysis']['risk_level'] in (
        'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
    assert ta['gas_side_analysis']['throat_heat_flux'] > 0.0
    assert ta['cooling_analysis']['required_cooling_area'] > 0.0
