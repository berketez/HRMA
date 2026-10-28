"""v3.0.1 (V301/H-termal) — hibrit kamara cidarının yakıt bloğu koruması.

Berke onaylı ÖNEMLİ fizik değişikliği (26 Eki). Isı modülü kamara cidarını
bütünüyle sıcak gaza açık sayıyordu; ölçüldü (örnek hibrit 3 kN, ss_304,
``docs/scofield/raw/OH/V301/hibrit-termal/once.json``): denge cidarı
3313 K ⟷ erime 1673 K, bundan türeyen yorulma CRITICAL ve emniyet UNSAFE.
Kamara artık üç bölgedir (``hybrid_rocket_engine._chamber_wall_zones_block``).

Bekçiler (brif "Kanıt ve test"):
  (a) yakıt bloğu altındaki bölgede kararlı adyabatik sıcaklık yapı
      zincirine GİRMEZ (ters mutasyonla kırmızı: RAPOR.md);
  (b) astar boyutlandırması yoksa açık bölgede kritik hüküm KALIR;
  (c) kalıntı et 0 beyanı / kalıntı et > 0 notu;
  (d) katı ve sıvı yollar bölge kodunu hiç çağırmaz (md5 kanıtı RAPOR.md).
"""

import contextlib
import io
import types
import warnings

import pytest

from hrma.engines import hybrid_rocket_engine as H
from tests.test_example_projects import (ENDPOINTS, HEADERS,
                                         calculate_payload, load_example_doc)

def _post(client, ek=None):
    # Örnek hibrit (3 kN N2O/HTPB, examples/) — alanlar örnek belgesinden
    # okunur, burada sayı yazılmaz.
    alanlar = dict(load_example_doc('hybrid')['inputs']['fields'])
    yuk = calculate_payload('hybrid', dict(alanlar, **(ek or {})))
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        r = client.post(ENDPOINTS['hybrid'], json=yuk, headers=HEADERS)
    assert r.status_code == 200, r.get_json()
    return r.get_json()['motor']


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def motor(client):
    return _post(client)


def _kritik_kodlar(motor):
    return {w.get('code') for w in motor.get('design_warnings') or []
            if isinstance(w, dict) and w.get('severity') == 'critical'}


# --- (a) yakıt bloğu altında adyabatik sıcaklık yapı zincirine girmez ------
class TestBlokAltiYapiZinciri:
    def test_bolgeler_ve_boylar_yayimlaniyor(self, motor):
        z = motor['chamber_wall_zones']
        adlar = [b['zone'] for b in z['zones']]
        assert adlar == [H.CHAMBER_ZONE_GRAIN, H.CHAMBER_ZONE_PRE,
                         H.CHAMBER_ZONE_POST]
        boy = {b['zone']: b['length_m'] for b in z['zones']}
        # Bölge boyları motorun kendi geometri alanlarıdır (tek kaynak).
        assert boy[H.CHAMBER_ZONE_GRAIN] == pytest.approx(
            motor['grain_length'], rel=1e-12)
        assert boy[H.CHAMBER_ZONE_PRE] == pytest.approx(
            motor['pre_chamber_length'], rel=1e-12)
        assert boy[H.CHAMBER_ZONE_POST] == pytest.approx(
            motor['post_chamber_length'], rel=1e-12)

    def test_blok_alti_korunur_beyanli(self, motor):
        g = motor['chamber_wall_zones']['zones'][0]
        assert g['verdict'] == H.ZONE_VERDICT_PROTECTED
        assert g['declaration'] == H.GRAIN_PROTECTION_DECLARATION
        assert 'MissingProperty' in g['declaration']
        assert 'primary source not verified' in g['source']

    def test_yapi_zinciri_adyabatik_sicakligi_kullanmaz(self, motor):
        ht = motor['heat_transfer_analysis']
        T_ciplak = ht['wall_analysis']['max_temperature']
        T0 = ht['design_parameters']['ambient_temperature']
        ta = motor['structural_analysis']['thermal_analysis']
        z = motor['chamber_wall_zones']
        # Çıplak cidar kontrolü SAYI olarak kalır ve erimenin üstündedir...
        assert T_ciplak > 3000.0
        # ...ama yapısal zincir onu GÖRMEZ: kasa sıcaklığı beyanlı ortamdır.
        assert z['all_zones_protected'] is True
        assert z['structural_casing_temperature_K'] == T0
        assert ta['wall_temperature_inner_K'] == T0
        assert ta['wall_temperature_outer_K'] == T0
        assert ta['wall_temperature_source'] == \
            H.CASING_TEMPERATURE_SOURCE_ZONES
        fa = motor['structural_analysis']['fatigue_analysis']
        assert fa['fatigue_limit'] == fa['fatigue_limit_room_MPa']
        assert fa['fatigue_status'] != 'CRITICAL'

    def test_ciplak_cidar_kritikleri_bolgeye_devredildi(self, motor):
        assert not (_kritik_kodlar(motor) & set(H.BARE_WALL_CRITICAL_CODES))
        # Sayı ve kayıt SİLİNMEDİ: info + superseded_by künyesiyle duruyor.
        gs = motor['heat_transfer_analysis']['gas_side_analysis']
        devredilen = [w for w in gs['warnings']
                      if w.get('code') == 'warn.thermal.wall_exceeds_melting']
        assert devredilen and all(
            w['severity'] == 'info'
            and w['superseded_by'] == 'chamber_wall_zones'
            and w['bare_wall_severity'] == 'critical' for w in devredilen)

    def test_acik_bolgeler_astar_gerekir_uyarisi(self, motor):
        zl = {b['zone']: b for b in motor['chamber_wall_zones']['zones']}
        astar = motor['thermal_protection']['chamber_liner']['thickness']
        for ad in (H.CHAMBER_ZONE_PRE, H.CHAMBER_ZONE_POST):
            assert zl[ad]['verdict'] == H.ZONE_VERDICT_LINER_REQUIRED
            assert zl[ad]['severity'] == 'warning'
            assert zl[ad]['liner_thickness_mm'] == astar
        kayit = [w for w in motor['design_warnings']
                 if w.get('code') == 'warn.hybrid.chamber_liner_required']
        assert len(kayit) == 1 and kayit[0]['severity'] == 'warning'
        assert kayit[0]['params']['liner_mm'] == round(astar, 2)

    def test_yapisal_varsayim_gorunur(self, motor):
        kodlar = {w.get('code') for w in motor['design_warnings']}
        assert 'warn.hybrid.structural_casing_temperature_declared' in kodlar
        assert 'warn.hybrid.chamber_grain_protected' in kodlar


# --- (b) astar boyutlandırması yoksa kritik hüküm kalır --------------------
def _sahte_motor(D_ch=0.1, D_son=0.08, L_grain=0.5, L_pre=0.05,
                 L_post=0.03):
    return types.SimpleNamespace(
        D_ch=D_ch, D_port_final=D_son, port_count=1, L_grain=L_grain,
        L_pre_chamber=L_pre, L_post_chamber=L_post, t_burn_effective=10.0,
        t_b=10.0)


def _sahte_isi(kritik=True):
    kayit = {'code': 'warn.thermal.wall_exceeds_melting',
             'severity': 'critical', 'params': {'T_wall': 3313}}
    return {'gas_side_analysis': {'warnings': [kayit] if kritik else [],
                                  'adiabatic_wall_temperature': 3321.0},
            'wall_analysis': {'max_temperature': 3313.0, 'warnings': []},
            'safety_analysis': {'warnings': [kayit] if kritik else []},
            'design_parameters': {'ambient_temperature': 293.15}}


ASTAR_TAMAM = {'thickness': 2.39, 'thickness_status': 'sized',
               'model_valid': True, 'material': 'Silica phenolic'}


class TestAstarYoksaKritikKalir:
    @pytest.mark.parametrize('astar', [
        None,
        {'thickness': None, 'thickness_status': 'NOT_MODELLED',
         'model_valid': False, 'validity_note': 'MODEL OUT OF ENVELOPE'},
        dict(ASTAR_TAMAM, model_valid=False),
    ])
    def test_acik_bolge_kritik_ve_yapi_ciplak_sicaklikta(self, astar):
        blok = H.HybridRocketEngine._chamber_wall_zones_block(
            _sahte_motor(), _sahte_isi(), astar)
        zl = {b['zone']: b for b in blok['zones']}
        assert zl[H.CHAMBER_ZONE_GRAIN]['verdict'] == H.ZONE_VERDICT_PROTECTED
        for ad in (H.CHAMBER_ZONE_PRE, H.CHAMBER_ZONE_POST):
            assert zl[ad]['verdict'] == H.ZONE_VERDICT_BARE_WALL_CRITICAL
            assert zl[ad]['severity'] == 'critical'
        assert blok['all_zones_protected'] is False
        assert blok['structural_casing_temperature_K'] == 3313.0

    def test_kritik_kayitlar_degismeden_kalir(self):
        isi = _sahte_isi()
        motor = types.SimpleNamespace(design_warnings=[])
        blok = H.HybridRocketEngine._chamber_wall_zones_block(
            _sahte_motor(), isi, None)
        H.HybridRocketEngine._apply_chamber_zone_verdicts(motor, blok, isi)
        assert isi['gas_side_analysis']['warnings'][0]['severity'] == \
            'critical'
        kodlar = {w['code'] for w in motor.design_warnings}
        assert 'warn.hybrid.chamber_liner_required' not in kodlar
        assert 'warn.hybrid.structural_casing_temperature_declared' \
            not in kodlar

    def test_uctan_uca_astar_kosmazsa_eski_kritik_hukum(self, client):
        from tests.support.hibrit_termal import astar_boyutlandirmasi_kosmaz
        with astar_boyutlandirmasi_kosmaz():
            m = _post(client)
        assert 'warn.thermal.wall_exceeds_melting' in _kritik_kodlar(m)
        ta = m['structural_analysis']['thermal_analysis']
        assert ta['wall_temperature_source'] == 'heat_transfer_module'
        assert ta['wall_temperature_inner_K'] == \
            m['heat_transfer_analysis']['wall_analysis']['inner_temperature']

    def test_yakit_blogu_kosulu_yoksa_koruma_yok(self):
        blok = H.HybridRocketEngine._chamber_wall_zones_block(
            _sahte_motor(L_grain=0.0), _sahte_isi(), ASTAR_TAMAM)
        assert blok['zones'][0]['verdict'] == H.ZONE_VERDICT_NOT_PROTECTED
        assert blok['all_zones_protected'] is False


# --- (c) kalıntı et beyanı -------------------------------------------------
class TestKalintiEt:
    def test_kalinti_et_sifir_adli_not(self, motor):
        g = motor['chamber_wall_zones']['zones'][0]
        assert g['final_web_mm'] == 0.0
        assert [n['code'] for n in g['notes']] == [
            'warn.hybrid.zone_residual_web_zero']
        kodlar = {w.get('code') for w in motor['design_warnings']}
        assert 'warn.hybrid.zone_residual_web_zero' in kodlar

    def test_kalinti_et_pozitif_not_mm(self):
        blok = H.HybridRocketEngine._chamber_wall_zones_block(
            _sahte_motor(D_ch=0.086, D_son=0.08), _sahte_isi(), ASTAR_TAMAM)
        notlar = blok['zones'][0]['notes']
        assert notlar[0]['code'] == 'warn.hybrid.zone_residual_web'
        assert notlar[0]['params']['web_mm'] == pytest.approx(3.0)


# --- (d) katı ve sıvı yollar bölge kodunu çağırmaz -------------------------
def test_kati_ve_sivi_bolge_kodunu_cagirmaz(client, monkeypatch):
    def patla(*a, **k):
        raise AssertionError('hibrit bölge kodu katı/sıvı yolunda çağrıldı')
    monkeypatch.setattr(H.HybridRocketEngine, '_chamber_wall_zones_block',
                        patla)
    monkeypatch.setattr(H.HybridRocketEngine, '_apply_chamber_zone_verdicts',
                        patla)
    for tur in ('solid', 'liquid'):
        alanlar = load_example_doc(tur)['inputs']['fields']
        with contextlib.redirect_stdout(io.StringIO()), \
                warnings.catch_warnings():
            warnings.simplefilter('ignore')
            r = client.post(ENDPOINTS[tur],
                            json=calculate_payload(tur, alanlar),
                            headers=HEADERS)
        assert r.status_code == 200, tur
        assert 'chamber_wall_zones' not in str(r.get_json())[:2_000_000]


# --- i18n: yeni kodlar ve kart anahtarları iki dilde -----------------------
def test_yeni_metinler_iki_dilde():
    from pathlib import Path
    kaynak = (Path(__file__).resolve().parents[1]
              / 'hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
    for anahtar in ('warn.hybrid.chamber_grain_protected',
                    'warn.hybrid.zone_residual_web_zero',
                    'warn.hybrid.zone_residual_web',
                    'warn.hybrid.chamber_liner_required',
                    'warn.hybrid.structural_casing_temperature_declared',
                    'app.zones.title', 'app.zones.vProtected',
                    'app.zones.vLinerRequired', 'app.zones.vBareCritical',
                    'app.zones.structuralDeclared', 'app.zones.declaration'):
        assert kaynak.count(f"'{anahtar}':") == 2, anahtar
