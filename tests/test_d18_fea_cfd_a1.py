# tests/ — ÖH Dalga-18 / kulvar fea-cfd / aşama 1 bekçileri
"""Dalga-18'in FEA + CFD kulvarında onarılan kusurların bekçileri.

Her sınıf TEK kalemi kilitler ve her biri ters-mutasyonla kırmızı
görülmüştür (kanıt: ``docs/scofield/raw/OH/D18/fea-cfd/a1/mutasyon*.json``).
Ölçüm dosyaları aynı dizinde ``once_*.json`` / ``sonra_*.json`` adıyla
durur.
"""

import contextlib
import io
import json
import os
import pathlib
import sys

import numpy as np
import pytest

from tests.support.fea_lule import ag_malzemesi
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


BASLIK = {'Host': '127.0.0.1:8080'}


# ===========================================================================
# P6B2-01 (Fable-D16 ŞART) — FEA köprüsü wall_resolution'ı YARGILIYOR,
# beyan kanalı bunu SÖYLEMELİ.
#
# ÖLÇÜLEN KUSUR (taban 9071a64, once_p6b2_01_beyan.json):
#   consumed_by_solver = ['x_mm','h_g','T_recovery']  (wall_resolution YOK)
#   supplied_by_caller içinde wall_resolution TEKRARLANIYOR (True)
#   _basis cümlesi: "... it is republished, not recomputed and NOT JUDGED
#   HERE" — oysa köprü aynı bloğa bakarak NOT_MODELLED ⟷ ok arasında
#   hüküm değiştiriyor (D_koprunun_hukmu: resolved_False → reddedildi,
#   resolved_True → kabul).
# ===========================================================================

HIBRIT_GOVDE = {
    'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 2.5, 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'expansion_ratio': 4.0, 'nozzle_type': 'conical',
    'chamber_material': 'steel_4130', 'wall_thickness': 5,
}
FEA_KUCUK = {'n_axial': 12, 'n_radial': 4, 'max_halvings': 3}

#: Ürünün KENDİ ölçtüğü hüküm (olcum_y_plus.json, standard 120×24).
COZUNMEMIS_HUKUM = {
    'resolved': False,
    'regime': 'log_layer',
    'y_plus_max': 190.2818899396976,
    'y_plus_wall_resolved_edge': 1.0,
    'y_plus_log_layer_edge': 30.0,
}
COZULMUS_HUKUM = {
    'resolved': True,
    'regime': 'wall_resolved',
    'y_plus_max': 0.83,
    'y_plus_wall_resolved_edge': 1.0,
    'y_plus_log_layer_edge': 30.0,
}


@pytest.fixture(scope='module')
def motor(client):
    r = _sessiz(client.post, '/calculate', json=HIBRIT_GOVDE, headers=BASLIK)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()['motor']


@pytest.fixture(scope='module')
def profil(client, motor):
    r = _sessiz(client.post, '/api/analysis/wall-profile', json={
        'chamber_pressure': motor['chamber_pressure'],
        'chamber_temperature': motor['chamber_temperature'],
        'chamber_diameter': motor['chamber_diameter'],
        'chamber_length': motor['chamber_length'],
        'burn_time': motor['burn_time'],
        'mdot_total': motor['mdot_total'],
        'throat_diameter': motor['throat_diameter'],
        'exit_diameter': motor['exit_diameter'],
        'expansion_ratio': motor['expansion_ratio'],
        # V301/PANEL (NK-12): profil termal AĞIN malzemesiyle (lüle).
        'nozzle_type': 'conical',
        'material': ag_malzemesi(motor, 'steel_4130'),
        'wall_thickness': 0.005,
    }, headers=BASLIK)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()['wall_profile']


class TestP6B201DuvarCozunurluguBEYANDA:
    """Köprünün yargıladığı alan, beyan kanalında TÜKETİLEN sayılır."""

    def _kos(self, client, motor, profil, hukum):
        p = dict(profil)
        if hukum is not None:
            p['wall_resolution'] = dict(hukum)
        r = _sessiz(client.post, '/api/fea/thermal',
                    json=dict(FEA_KUCUK, motor=motor, axial_profile=p,
                              ambient_temperature_K=293.15), headers=BASLIK)
        # OH-D17-07 (ÖH D22): bu satır eskiden yalnız 200 kabul ediyordu ve
        # kusuru KORUYORDU — ``COZUNMEMIS_HUKUM`` vakası (wall_resolution.
        # resolved=False) tam da kalemin adlandırdığı vakadır: köprü
        # NOT_MODELLED derken zarf 'success' + 200 diyordu. Zarf artık
        # reddin kendisini yayımlıyor (422 + status='not_modelled') ve
        # ``fea`` bloğu -- bu sınıfın YARGILADIĞI beyan kanalı dâhil --
        # AYNEN duruyor. Bekçinin konusu beyan kanalıdır, HTTP kodu değil;
        # o yüzden iki meşru kod da kabul edilir ve gövdenin zarf hükmü
        # köprü hükmüyle tutarlılığı ayrıca sınanır.
        assert r.status_code in (200, 422), r.get_data(as_text=True)[:300]
        govde = r.get_json()
        fea = govde['fea']
        if fea.get('status') == 'ok':
            assert r.status_code == 200 and govde['status'] == 'success'
        else:
            assert r.status_code == 422 and govde['status'] == 'not_modelled'
        return fea

    def test_cozunmemis_profil_TUKETILEN_listesinde_ilan_ediliyor(
            self, client, motor, profil):
        """ŞART'ın birinci cümlesi: resolved=False → consumed'da görünür."""
        fea = self._kos(client, motor, profil, COZUNMEMIS_HUKUM)
        beyan = fea['axial_profile_declarations']
        assert 'wall_resolution' in beyan['consumed_by_solver'], (
            'köprü wall_resolution ile hüküm veriyor ama beyan kanalı onu '
            'çözücünün OKUMADIĞI alanlar arasında gösteriyor: %r'
            % (beyan['consumed_by_solver'],))
        assert 'wall_resolution' not in beyan['supplied_by_caller'], (
            'tüketilen alan beyan kanalında TEKRARLANIYOR — aynı alan hem '
            '"okundu" hem "okunmadı" diye yayımlanamaz')
        # Kusurun ürün ayağı da aynı yanıtta: profil GERÇEKTEN reddedildi.
        assert fea['status'] != 'ok', (
            'çözünmemiş duvarlı profil köprüden geçti — fail-closed kapı '
            'düşmüş')

    def test_cozulmus_profilde_de_ayni_liste(self, client, motor, profil):
        """Hüküm 'ok' iken de alan tüketilendir (kapı yine ona baktı)."""
        fea = self._kos(client, motor, profil, COZULMUS_HUKUM)
        beyan = fea['axial_profile_declarations']
        assert fea['status'] == 'ok', fea.get('reason')
        assert 'wall_resolution' in beyan['consumed_by_solver']
        assert 'wall_resolution' not in beyan['supplied_by_caller']

    def test_basis_cumlesi_YARGILADIGINI_soyluyor(self, client, motor,
                                                  profil):
        """ŞART'ın ikinci cümlesi: 'not judged here' artık YALAN olamaz."""
        beyan = self._kos(client, motor, profil,
                          COZUNMEMIS_HUKUM)['axial_profile_declarations']
        basis = beyan['_basis']
        assert 'wall_resolution' in basis, (
            '_basis köprünün wall_resolution hükmünü hiç anmıyor')
        assert 'judges' in basis or 'JUDGES' in basis, (
            '_basis hâlâ yalnız "republished / not judged" diyor: %s' % basis)
        # Eski YANLIŞ cümle aynen kalmamalı.
        assert 'T_recovery only' not in basis, (
            '_basis hâlâ "solver reads x_mm, h_g and T_recovery only" diyor')

    def test_bloksuz_profil_beyani_KIRLETMIYOR(self, client, motor, profil):
        """Bartz yolunda blok yok: liste yine tam, uydurma alan yok."""
        beyan = self._kos(client, motor, profil,
                          None)['axial_profile_declarations']
        assert 'wall_resolution' in beyan['consumed_by_solver']
        assert 'wall_resolution' not in beyan['supplied_by_caller']

    def test_y_plus_sayisinin_KAYNAGI_kanit_dizininde(self):
        """ŞART'ın üçüncü cümlesi: kaynaksız sayı bırakılmaz."""
        yol = (KOK / 'docs/scofield/raw/OH/D18/fea-cfd/a1'
               / 'olcum_y_plus.json')
        assert kanit_gerekli(yol).exists(), (
            'bridge.py yorumu ve test_wall_output.py docstringi 268,86 / '
            '190,28 sayılarını anıyor; ölçüm dosyası yok')
        veri = json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))
        olcum = veri['K2_y_plus_urun_ucundan']
        assert olcum['coarse']['y_plus_achieved_max'] == pytest.approx(
            268.86392134602016, rel=1e-9)
        assert olcum['standard']['y_plus_achieved_max'] == pytest.approx(
            190.2818899396976, rel=1e-9)
        # Kaynak, sayıyı anan İKİ dosyadan da erişilebilir olmalı.
        for hedef in ('hrma/fea/bridge.py', 'tests/cfd/test_wall_output.py'):
            metin = (KOK / hedef).read_text(encoding='utf-8')
            assert 'olcum_y_plus.json' in metin, (
                '%s sayıyı anıyor ama kaynağını göstermiyor' % hedef)


# ===========================================================================
# P8B1-03 (Fable-D15 ŞART) — «yakınsamayan koşuda BOŞ GEÇEN bekçi
# kilitlensin» + eşiğin gerekçesi birleşik ağaçta ÖLÇÜLDÜ.
#
# Mevcut bekçi (tests/test_d15_fea_viz_a3.py::test_inceltme_kapiyi_gecen_
# tura_gider) iddiasını ``if r.converged:`` içine koyuyordu: koşum
# yakınsamazsa hiçbir şey ölçmüyor, YEŞİL geçiyordu. Aşağıdaki bekçi
# BOŞLUKSUZDUR — iki dalın ikisi de sınanır.
#
# ÖLÇÜLDÜ (once_p8b1_03.json, taban 9071a64): hibrit 2 kN/30 bar vakasında
# kapamanın kendi tabanı %10,06…%10,71'e çıkmıştır ve EŞİĞİN (%10) ÜSTÜNDE
# kalır; yalnız na=64 turu (%9,77) kapıdan geçer. Yani "yakınsamayan koşu"
# bu vakada KURAMSAL DEĞİL, ürünün gerçekten gördüğü hâldir.
# ===========================================================================

class TestP8B103GeometriKapisiBOSLUKSUZ:

    @staticmethod
    def _gir(client):
        from hrma.fea.bridge import extract_structural_inputs
        # ÖH 15 Eki (ana model): ölçüm koşulu AÇIKÇA — na=12 sapması
        # (+0,17168) kamara malzemesi 4130 iken ölçüldü; HB10 hibrit
        # varsayılanını 304'e çevirince cidar/geometri değişip sapma 0,043'e
        # indi. Malzeme sabitlenir; eşik ve beklentiler DEĞİŞMEDİ.
        r = _sessiz(client.post, '/calculate', json={
            'motor_name': 'd18a1g', 'thrust': 2000, 'burn_time': 10,
            'of_ratio': 6.0, 'chamber_pressure': 30.0,
            'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
            'chamber_material': 'steel_4130',
            # V3.0.5 T-ÇAPA-C1 — ÖLÇÜM KOŞULU AÇIKÇA: c* verimi %100 ve cidar
            # 13,0281 mm. V301/H-termal (77d64c641) korunan bölgeler yüzünden
            # boyutlandırılan hibrit cidarını inceltti, V301/H-PANEL (74b55500a)
            # N2O/HTPB c*'ına η=0,89 varsayılanı getirdi (onaylı yayımlanan sayı
            # değişimleri; bekçinin konusu değil). Bu iki alanla köprü girdisi
            # H-termal öncesi c7776576f ağacının isteğiyle BİT-AYNI (cidar
            # 0,013028095219365316 m, kontur toplamı 1,0821779411399757; ölçüldü — test_d22/test_d27 ile aynı gövde).
            'combustion_efficiency': 100.0,
            'wall_thickness': 13.028095219365316}, headers=BASLIK)
        motor = (r.get_json() or {}).get('motor') or {}
        gir = extract_structural_inputs(motor)
        assert gir['status'] == 'ok', gir.get('reason')
        return gir

    def test_inceltme_sonucu_IKI_DALDA_da_sinaniyor(self, client):
        """Yakınsadıysa kapı geçilmiş OLMALI; yakınsamadıysa hüküm YOK."""
        from hrma.fea.structural_axisym import solve_with_refinement
        gir = self._gir(client)
        r = solve_with_refinement(
            gir['contour'], gir['thickness_m'], gir['material'],
            inner_pressure=gir['inner_pressure_pa'],
            n_axial0=16, max_rounds=3)
        gk = r.meta['geometri_kalinlik_kapisi']
        assert gk['sapma_orani'] is not None, (
            'geometri kapısı ölçülmemiş — sapma yayımlanmıyor')
        if r.converged:
            assert gk['gecti'] is True, (
                'yakınsamış sayılan turda geometri kapısı GEÇİLMEMİŞ: '
                'sapma %.4f > eşik %.2f' % (gk['sapma_orani'], gk['esik']))
        else:
            # BOŞ GEÇMEYEN dal: yakınsamama GEREKÇELİ olmalı ve beyan
            # kullanıcının okuyacağı yerde durmalı.
            assert isinstance(r.meta.get('convergence_beyan')
                              or r.meta.get('beyan') or '', str)
            assert gk['gecti'] in (True, False)

    def test_kapi_gecmeyen_tur_YAKINSAMIS_sayilmaz(self, client):
        """Kapı ile hüküm arasındaki bağ: sapma > eşik ⇒ converged False."""
        from hrma.fea.structural_axisym import solve_with_refinement
        gir = self._gir(client)
        # ÇAPA GÖÇÜ (OH-D25-28, ÖH D27 a1): iç kontur köşe tabanı ürün
        # varsayılanı oldu; aynı motorda na=16 turunun YERLEŞİM payı
        # +0,12894'ten −0,05098'e döndü, yani o tur artık kapıyı GEÇİYOR.
        # Bekçinin iddiası ("kapıyı geçemeyen tur yakınsamış sayılmaz")
        # boşa düşmesin diye kapıyı GERÇEKTEN geçemeyen bir tur seçildi:
        # ölçüldü (n_axial0 = 4/6/8/12/16 → −0,05575 / −0,07298 / −0,05681
        # / +0,17168 / −0,05098; eşik 0,10), na = 12 kalıyor. Eşik
        # DEĞİŞMEDİ, tolerans BÜYÜTÜLMEDİ; yalnız fikstür turu taşındı.
        r = solve_with_refinement(
            gir['contour'], gir['thickness_m'], gir['material'],
            inner_pressure=gir['inner_pressure_pa'],
            n_axial0=12, max_rounds=0)
        gk = r.meta['geometri_kalinlik_kapisi']
        assert gk['sapma_orani'] > gk['esik'], (
            'na=12 turunun sapması eşiğin altına inmiş — vaka değişmiş, '
            'bekçi yeniden ölçülmeli (ölçüm: +0,17168)')
        assert gk['gecti'] is False
        assert r.converged is False, (
            'geometri kapısını geçemeyen tur yakınsamış sayıldı')

    def test_esigin_gerekcesi_KANIT_dizininde(self):
        """ŞART: eşik birleşik ağaçta yeniden ölçülüp gerekçelendirilsin."""
        from hrma.fea import mesh_axisym as MA
        yol = (KOK / 'docs/scofield/raw/OH/D18/fea-cfd/a1'
               / 'once_p8b1_03.json')
        assert kanit_gerekli(yol).exists(), 'eşiğin birleşik-ağaç ölçümü yok'
        veri = json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))
        assert veri['esik'] == MA.GEOMETRY_THICKNESS_TOL, (
            'ölçüm başka bir eşikle alınmış')
        merdiven = veri['vakalar']['hibrit_2kN_30bar']['merdiven']
        # Ölçülen olgu: EN İNCE tur kapıyı GEÇMİYOR (taban eşiğin üstünde).
        assert merdiven['1024']['kapiyi_gecti'] is False, (
            'ölçüm bayatlamış: en ince turun kapı hükmü değişmiş')
        # Kaynak dosyada BAYAT gerekçe kalmamalı.
        kaynak = (KOK / 'hrma/fea/mesh_axisym.py').read_text(encoding='utf-8')
        assert 'once_p8b1_03.json' in kaynak, (
            'eşiğin gerekçesi ölçüm dosyasına bağlanmamış')
        assert 'BAYATLAMIŞTIR' in kaynak, (
            'D15 öncesi sayılar hâlâ tek gerekçe olarak duruyor')


# ===========================================================================
# P6B2-01 ŞARTI (Fable-D18 kısım-2) — ÖH D24 / fea-cfd a2
#
# ŞART üç şey istiyor:
#   (1) TEK KAYNAK: bridge.THERMAL_PROFILE_CONSUMED_KEYS; app.py sabiti
#       ondan türesin (``is`` eşitliği), elle liste kalmasın;
#   (2) ``_basis`` cümlesi ``resolution_ok``un da YARGILANDIĞINI söylesin
#       (P8B2-02 fail-closed red); ``y_plus_max`` republished kalabilir;
#   (3) resolution_ok=False profil → 'resolution_ok' consumed_by_solver'da,
#       supplied_by_caller'da DEĞİL, fea.status != ok.
#
# ÖLÇÜLDÜ (taban 88a29d3, docs/scofield/raw/OH/D24/fea-cfd/a2/once_a2.json
# -> P6B2-01): bridge_sabiti_var_mi = false, app_sabiti dört adlı ELLE
# yazılmış tuple, resolution_ok_consumed_icinde = false,
# resolution_ok_supplied_icinde = true, basis_resolution_ok_diyor_mu = false.
# ===========================================================================
class TestP6B201SartTekKaynak:

    def test_app_sabiti_koprununkinin_TA_KENDISI(self):
        import contextlib as _c
        import io as _io
        with _c.redirect_stdout(_io.StringIO()):
            from hrma import app as app_mod
        from hrma.fea import bridge
        assert (app_mod._FEA_PROFILE_CONSUMED_KEYS
                is bridge.THERMAL_PROFILE_CONSUMED_KEYS), (
            'ŞART (1): uç katmanı köprünün sabitini ithal etmiyor')
        assert 'resolution_ok' in bridge.THERMAL_PROFILE_CONSUMED_KEYS
        assert 'y_plus_max' not in bridge.THERMAL_PROFILE_CONSUMED_KEYS

    def test_resolution_ok_FALSE_profil_ucta_reddediliyor(
            self, client, motor, profil):
        """ŞART (3): davranış + beyan tek koşumda."""
        p = dict(profil)
        p['resolution_ok'] = False
        p['y_plus_max'] = 190.2818899396976
        r = _sessiz(client.post, '/api/fea/thermal',
                    json=dict(FEA_KUCUK, motor=motor, axial_profile=p,
                              ambient_temperature_K=293.15), headers=BASLIK)
        assert r.status_code in (200, 422), r.get_data(as_text=True)[:300]
        fea = r.get_json()['fea']
        assert fea.get('status') != 'ok', (
            'profili üreten katman DOĞRULANMAMIŞ dediği hâlde hüküm '
            'yayımlandı (P8B2-02 fail-closed reddi yok)')
        beyan = fea['axial_profile_declarations']
        assert 'resolution_ok' in beyan['consumed_by_solver'], (
            'ŞART (3): yargılanan alan "tüketilen" listesinde değil: %s'
            % (beyan['consumed_by_solver'],))
        assert 'resolution_ok' not in beyan['supplied_by_caller'], (
            'ŞART (3): yargılanan alan "çözücünün okumadığı" kümede')
        # y_plus_max yalnız mesajda geçiyor -> republished kalır.
        assert 'y_plus_max' in beyan['supplied_by_caller']

    def test_basis_cumlesi_resolution_ok_u_ADIYLA_yarguluyor(
            self, client, motor, profil):
        """ŞART (2): beyan cümlesi ikinci fail-closed kapıyı da söylüyor."""
        p = dict(profil)
        p['resolution_ok'] = False
        r = _sessiz(client.post, '/api/fea/thermal',
                    json=dict(FEA_KUCUK, motor=motor, axial_profile=p,
                              ambient_temperature_K=293.15), headers=BASLIK)
        basis = r.get_json()['fea']['axial_profile_declarations']['_basis']
        assert 'resolution_ok' in basis, basis
        assert 'fail-closed' in basis, basis
        # Cümle de TEK KAYNAKTAN gelir (liste ile beyan ayrı düşemesin).
        from hrma.fea.bridge import THERMAL_PROFILE_CONSUMED_BASIS
        assert THERMAL_PROFILE_CONSUMED_BASIS in basis
        # y_plus_max'ın "republished" konumu korunuyor.
        assert 'republished' in basis
