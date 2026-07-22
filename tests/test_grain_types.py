# -*- coding: utf-8 -*-
"""Katı grain tiplerinin ayrı ayrı GERÇEK hesaplandığının doğrulaması.

Denetim bulgusu (2026-07-19): calculate_burn_area yalnız 'bates', 'star' ve
'wagon_wheel' dallarını tanıyordu; geri kalan HER tip etiketsiz bir
`else: # end_burner` dalına düşüyordu. Arayüzdeki açılır listede 'finocyl' ve
'slotted' seçenekleri VARDI, ikisi de sessizce uç-yanmalı motor hesaplıyordu.

Ölçülen eski davranış (D_ch=100 mm, L=500 mm, D_core=30 mm):
    end_burner / finocyl / slotted / uydurma-tip  ->  A_b(w) = 0.007854 m²
    (dördü de web'den bağımsız AYNI sabit; hiçbir uyarı yok)

Bu dosya bunun geri gelmesini engeller:
  (a) finocyl / slotted / end_burner ÜÇÜ DE farklı yanma alanı eğrisi verir
  (b) her tip için kütle korunumu: ∫A_b dw = V_yakıt (%0.5 içinde)
  (c) kanatçık / yarık sayısı değişince eğri değişir (parametreler gerçekten
      hesaba giriyor, dekoratif değil)
  (d) tanınmayan tip sessizce kabul edilmez, ValueError verir
  (e) mevcut bates / star / wagon_wheel / end_burner eğrileri BİREBİR
      değişmedi (altın değerler denetim öncesi HEAD'den alınmıştır)
"""

import numpy as np
import pytest

pytest.importorskip('shapely')

from hrma.engines.solid_rocket_engine import (
    SolidRocketEngine, SUPPORTED_GRAIN_TYPES,
)


GEOM = dict(chamber_diameter=100, grain_length=500, core_diameter=30)


def _engine(grain_type, **overrides):
    return SolidRocketEngine(grain_type=grain_type,
                             overrides=overrides or None, **GEOM)


def _area_curve(engine, webs):
    return np.array([engine.calculate_burn_area(w) for w in webs])


def _max_web(engine):
    """Tükenmenin garanti olduğu web üst sınırı (m)."""
    if engine.grain_type == 'end_burner':
        return engine.L_grain          # eksenel yanma
    return engine.D_chamber / 2.0      # radyal yanma


def _burned_volume(engine, n=4001):
    """∫ A_b(w) dw — yanma alanı eğrisinin süpürdüğü hacim (m³)."""
    w = np.linspace(0.0, _max_web(engine), n)
    area = _area_curve(engine, w)
    integrate = getattr(np, 'trapezoid', None) or np.trapz
    return float(integrate(area, w))


# ---------------------------------------------------------------------------
# (e) REGRESYON: denetim öncesi HEAD'den alınan altın değerler.
# Bu tiplerin sayısal davranışı bu çalışmada DEĞİŞMEMELİDİR.
# ---------------------------------------------------------------------------
GOLDEN_WEBS = [0.0, 0.005, 0.010, 0.015, 0.020, 0.025, 0.030]
GOLDEN_AREAS = {
    'bates': [0.118595122673, 0.122522113490, 0.121736715327, 0.116238928183,
              0.106028752059, 0.091106186954, 0.071471232869],
    'star': [0.111538230743, 0.124238607063, 0.136938983382, 0.149639359702,
             0.162339736021, 0.045563952393, 0.000000000000],
    'wagon_wheel': [0.164926254795, 0.274877091325, 0.138514143401,
                    0.150206363193, 0.061900075800, 0.000000000000,
                    0.000000000000],
    'end_burner': [0.007853981634] * 7,
}


class TestNoSilentFallback:
    """(d) Tanınmayan grain tipi sessizce end_burner olmaz."""

    @pytest.mark.parametrize('bad', ['moon_burner', 'FINOCYL', 'anchor', '',
                                     'dogbone', 'c_slot'])
    def test_unknown_type_raises(self, bad):
        with pytest.raises(ValueError) as err:
            SolidRocketEngine(grain_type=bad, **GEOM)
        # Hata mesajı desteklenen tipleri SAYMALI (kullanıcı ne seçeceğini
        # bilmeli); yoksa hata da sessiz sayılır.
        msg = str(err.value)
        assert 'Unsupported grain type' in msg
        if bad:
            assert bad in msg          # reddedilen değer mesajda görünmeli
        for supported in SUPPORTED_GRAIN_TYPES:
            assert supported in msg

    def test_every_supported_type_is_computable(self):
        """Listelenen her tip gerçekten hesaplanabilmeli (ölü seçenek yok)."""
        for gt in SUPPORTED_GRAIN_TYPES:
            eng = _engine(gt)
            assert eng.calculate_burn_area(0.0) > 0.0, gt

    def test_end_burner_remains_explicitly_selectable(self):
        """end_burner bir KAÇAMAK dalı değil, açıkça seçilebilir bir tip."""
        assert 'end_burner' in SUPPORTED_GRAIN_TYPES
        eng = _engine('end_burner')
        beklenen = np.pi * (eng.D_chamber / 2) ** 2
        assert eng.calculate_burn_area(0.0) == pytest.approx(beklenen, rel=1e-9)


class TestTypesAreDistinct:
    """(a) Eskiden aynı olan eğriler artık birbirinden farklı."""

    def test_finocyl_slotted_end_burner_all_differ(self):
        webs = np.linspace(0.0, 0.030, 31)
        curves = {gt: _area_curve(_engine(gt), webs)
                  for gt in ('finocyl', 'slotted', 'end_burner')}
        for a, b in (('finocyl', 'slotted'), ('finocyl', 'end_burner'),
                     ('slotted', 'end_burner')):
            fark = np.max(np.abs(curves[a] - curves[b]))
            assert fark > 1e-3, (
                f"'{a}' ve '{b}' aynı yanma alanı eğrisini veriyor "
                f"(max fark {fark:.2e} m²) — sessiz fallback geri gelmiş "
                f"olabilir")

    def test_finocyl_and_slotted_are_not_constant(self):
        """Eski hata sabit π·r² eğrisiydi; gerçek modelde eğri web ile değişir."""
        webs = np.linspace(0.0, 0.025, 26)
        for gt in ('finocyl', 'slotted'):
            curve = _area_curve(_engine(gt), webs)
            assert curve.std() > 1e-3, f'{gt} eğrisi sabit görünüyor'
            # Uç-yanmalı sabitten en az bir mertebe büyük olmalı: bu tipler
            # port + yuva yüzeyleriyle yanar, tek dairesel yüzeyle değil.
            assert curve[0] > 5 * np.pi * (_engine(gt).D_chamber / 2) ** 2

    def test_no_type_reuses_the_end_burner_constant(self):
        """end_burner dışında hiçbir tip π·r² sabitine düşmemeli."""
        eng = _engine('end_burner')
        sabit = np.pi * (eng.D_chamber / 2) ** 2
        for gt in SUPPORTED_GRAIN_TYPES:
            if gt == 'end_burner':
                continue
            assert abs(_engine(gt).calculate_burn_area(0.0) - sabit) > 1e-4, gt


class TestMassConservation:
    """(b) ∫A_b dw yüklü yakıt hacmine eşit olmalı (%0.5 — BATES ölçütü)."""

    @pytest.mark.parametrize('grain_type', list(SUPPORTED_GRAIN_TYPES))
    def test_swept_volume_matches_propellant_volume(self, grain_type):
        eng = _engine(grain_type)
        swept = _burned_volume(eng)
        yuklu = eng._propellant_volume()
        assert yuklu > 0.0
        hata = abs(swept - yuklu) / yuklu
        assert hata < 0.005, (
            f'{grain_type}: ∫A_b dw = {swept:.6f} m³, V_yakıt = {yuklu:.6f} m³ '
            f'(sapma %{hata * 100:.3f}) — geometri modeli tutarsız')

    @pytest.mark.parametrize('grain_type,kw', [
        ('finocyl', {'fin_count': 3}),
        ('finocyl', {'fin_count': 8, 'fin_length': 30.0}),
        ('finocyl', {'finned_length_fraction': 0.8}),
        ('slotted', {'slot_count': 4}),
        ('slotted', {'slot_count': 12, 'slot_depth': 10.0}),
        ('slotted', {'slot_width': 8.0}),
    ])
    def test_conservation_holds_off_default(self, grain_type, kw):
        """Varsayılan dışı parametrelerde de korunum bozulmamalı."""
        eng = _engine(grain_type, **kw)
        swept = _burned_volume(eng)
        yuklu = eng._propellant_volume()
        assert abs(swept - yuklu) / yuklu < 0.005, f'{grain_type} {kw}'


class TestParametersDriveTheCurve:
    """(c) Kanatçık / yarık parametreleri eğriyi gerçekten değiştirmeli."""

    def test_fin_count_changes_curve(self):
        webs = np.linspace(0.0, 0.020, 21)
        c4 = _area_curve(_engine('finocyl', fin_count=4), webs)
        c8 = _area_curve(_engine('finocyl', fin_count=8), webs)
        assert np.max(np.abs(c4 - c8)) > 1e-3
        # Daha çok kanatçık -> daha çok başlangıç yanma yüzeyi
        assert c8[0] > c4[0]

    def test_slot_count_changes_curve(self):
        webs = np.linspace(0.0, 0.020, 21)
        c4 = _area_curve(_engine('slotted', slot_count=4), webs)
        c10 = _area_curve(_engine('slotted', slot_count=10), webs)
        assert np.max(np.abs(c4 - c10)) > 1e-3
        assert c10[0] > c4[0]

    def test_fin_depth_changes_curve(self):
        webs = np.linspace(0.0, 0.020, 21)
        sig = _area_curve(_engine('finocyl', fin_length=8.0), webs)
        derin = _area_curve(_engine('finocyl', fin_length=28.0), webs)
        assert np.max(np.abs(sig - derin)) > 1e-3

    def test_slot_depth_changes_curve(self):
        webs = np.linspace(0.0, 0.020, 21)
        sig = _area_curve(_engine('slotted', slot_depth=8.0), webs)
        derin = _area_curve(_engine('slotted', slot_depth=28.0), webs)
        assert np.max(np.abs(sig - derin)) > 1e-3

    def test_finned_fraction_changes_curve(self):
        """Kanatçıklı boy oranı finocyl'in profil karakterini belirler."""
        webs = np.linspace(0.0, 0.020, 21)
        az = _area_curve(_engine('finocyl', finned_length_fraction=0.2), webs)
        cok = _area_curve(_engine('finocyl', finned_length_fraction=0.8), webs)
        assert np.max(np.abs(az - cok)) > 1e-3

    def test_defaults_are_declared_not_silent(self):
        """Kullanıcı girdisi yoksa varsayılan BEYAN edilmeli (sessiz varsayım yok)."""
        rapor = _engine('finocyl')._analyze_grain_geometry()
        assert 'fin_count' in rapor['assumed_defaults']
        assert rapor['fin_count'] > 0
        rapor = _engine('slotted')._analyze_grain_geometry()
        assert 'slot_count' in rapor['assumed_defaults']
        # Kullanıcı verirse artık varsayılan sayılmamalı
        rapor = _engine('slotted', slot_count=9)._analyze_grain_geometry()
        assert 'slot_count' not in rapor['assumed_defaults']
        assert rapor['slot_count'] == 9


class TestGeometryIsPhysical:
    """Yeni tiplerin geometrisi fiziksel sınırların içinde kalmalı."""

    def test_burn_area_terminates(self):
        """Yanma alanı sonlu web'de sıfıra inmeli (sonsuz motor yok)."""
        for gt in ('finocyl', 'slotted'):
            eng = _engine(gt)
            assert eng.calculate_burn_area(_max_web(eng)) == pytest.approx(
                0.0, abs=1e-9), gt

    def test_excessive_depth_is_clipped_and_declared(self):
        """Kasa cidarını aşan yuva derinliği kırpılır ve BEYAN edilir."""
        rapor = _engine('slotted', slot_depth=195.0)._analyze_grain_geometry()
        assert 'slot_depth' in rapor['clipped_inputs']
        assert rapor['slot_depth_mm'] < 195.0

    def test_slotted_flow_area_uses_real_section(self):
        """Yarıklı kesitin akış alanı dairesel yaklaşıklıktan büyük olmalı."""
        eng = _engine('slotted')
        dairesel = np.pi * (eng.D_core / 2) ** 2
        assert eng._port_flow_area(0.0) > dairesel

    def test_finocyl_volume_uses_both_sections(self):
        """Kanatçıklı boy oranı yakıt hacmini değiştirmeli (iki kesitli model)."""
        az = _engine('finocyl', finned_length_fraction=0.2)._propellant_volume()
        cok = _engine('finocyl', finned_length_fraction=0.9)._propellant_volume()
        assert cok < az  # daha çok kanatçık -> daha çok boşaltılmış hacim


class TestExistingTypesUnchanged:
    """(e) Denetim öncesi tiplerin sayısal davranışı korunmalı."""

    @pytest.mark.parametrize('grain_type', sorted(GOLDEN_AREAS))
    def test_burn_area_matches_pre_audit_golden(self, grain_type):
        eng = _engine(grain_type)
        for web, altin in zip(GOLDEN_WEBS, GOLDEN_AREAS[grain_type]):
            hesap = eng.calculate_burn_area(web)
            assert hesap == pytest.approx(altin, rel=1e-9, abs=1e-12), (
                f'{grain_type} w={web * 1000:.0f} mm: {hesap:.12f} != '
                f'{altin:.12f} (denetim öncesi değer)')

    def test_star_overrides_unchanged(self):
        """Star parametre yolu da aynı sayıları vermeli."""
        eng = _engine('star', star_points=5, star_radius=20.0)
        # Denetim öncesi HEAD değerleri
        for web, altin in [(0.0, 0.122528788036), (0.010, 0.150298115290)]:
            assert eng.calculate_burn_area(web) == pytest.approx(
                altin, rel=1e-9)
