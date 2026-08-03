"""Hibrit A10 beyan taraması + L/D narinlik uyarısı + T60 boy alanları bekçileri.

Üç kalemi kilitler (v2.6.27, docs/YOL_HARITASI_2.7_VE_SONRASI.md Kulvar A):

1. A10 — NOT_MODELLED beyan taraması: sıvı motor 50+ beyan taşırken hibrit
   4 beyanla geziyordu; kullanıcı hibritte sessiz varsayımlarla
   karşılaşıyordu. Artık hibrit sonucu, sıvı/katının beyan ettiği ve hibritte
   de geçerli olan modellenmemiş fizik kalemlerini AÇIKÇA beyan eder.
   Bekçi iki yönlü çalışır: beyanlar var MI ve beyanlar YALAN MI
   (beyan edilen hesabın modellenmiş bir karşılığı sonuçta belirirse beyan
   çürümüştür — sıvı motorda min_throttle beyanı böyle çürümüştü).

2. L/D uyarısı — TEŞHİS KANITI: varsayılan girdiler (1000 N, 10 s, O/F 2,5,
   Pc 20 bar, tek port, G_ox 350) kamara L/D ≈ 19,7'lik bir boru üretiyor ve
   HİÇBİR uyarı çıkmıyordu. Aynı görev port_count=4 ile L/D ≈ 8,6'ya iniyor.
   Uyarı eşiği TEK yerde (GRAIN_LD_WARN_THRESHOLD) tanımlıdır ve uyarı
   parametresi olarak aynen yayımlanır.

3. T60 kalıntısı — total_motor_length kapak HARİÇTİ, 3B etiket kapak DAHİL
   ölçüyordu; aynı ad iki tanım taşıyordu. Artık iki büyüklük de açık adla
   ve beyanla yayımlanır; kapak boyu yapısal kapak analizinin GERÇEK
   değeridir, yapısal sonuç yoksa UYDURULMAZ.
"""

import json
import re
import warnings

import pytest

from hrma.engines.hybrid_rocket_engine import (
    GRAIN_LD_WARN_THRESHOLD,
    HybridRocketEngine,
)

LD_UYARI_KODU = 'hybrid.grain_slenderness_high'


def _kos(**degisiklik):
    """Tasarım noktası koşulmuş hibrit motor + sonuç sözlüğü."""
    ayarlar = dict(thrust=1000, burn_time=10, of_ratio=2.5,
                   chamber_pressure=20.0, track_performance=False)
    ayarlar.update(degisiklik)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = HybridRocketEngine(**ayarlar)
        sonuc = motor.calculate()
    return motor, sonuc


@pytest.fixture(scope='module')
def boru_motor():
    """Teşhisteki koşu: varsayılan girdiler, kamara L/D ≈ 19,7."""
    return _kos()


@pytest.fixture(scope='module')
def kompakt_motor():
    """Aynı görev, port_count=4: kamara L/D ≈ 8,6 — eşiğin altında."""
    return _kos(port_count=4)


# ---------------------------------------------------------------------------
# A10 — NOT_MODELLED beyanları
# ---------------------------------------------------------------------------

# Sıvı/katı motorun beyan ettiği (ya da bağladığı) ve hibritte de geçerli
# olan, hibrit çözücüde YOKLUĞU kod okunarak doğrulanmış kalemler.
BEKLENEN_BEYANLAR = {
    'feed_system',
    'ignition_startup_transient',
    'shutdown_transient',
    'combustion_stability_acoustics',
    'thermal_protection_liner',
    'oxidizer_tank_structure_slosh',
    'throttle_response_restart',
}

# Beyanın modellenmiş KARŞILIĞI sayılacak anahtarlar: bunlardan biri sonuçta
# belirirse ilgili beyan çürümüştür ve kaldırılmalıdır (yanlış beyan
# beyansızlıktan kötüdür).
CELISKI_ANAHTARLARI = {
    'feed_system': {'feed_system', 'feed_lines', 'valve_count',
                    'sensor_count', 'check_valve_count'},
    'ignition_startup_transient': {'ignition_delay', 'startup_sequence',
                                   'startup_time', 'igniter_design'},
    'shutdown_transient': {'shutdown_time', 'shutdown_sequence'},
    'combustion_stability_acoustics': {'acoustic_analysis', 'acoustic_modes',
                                       'instability_frequency'},
    'thermal_protection_liner': {'liner_thickness', 'ablative_thickness',
                                 'insulation_thickness'},
    'oxidizer_tank_structure_slosh': {'slosh_frequency', 'slosh_analysis',
                                      'tank_wall_thickness',
                                      'tank_structural_mass'},
    'throttle_response_restart': {'throttle_response', 'min_throttle_pct',
                                  'restart_capability'},
}


def _tum_anahtarlar(dugum, depo=None):
    """Sonuç ağacındaki TÜM sözlük anahtarlarını düzleştirir."""
    if depo is None:
        depo = set()
    if isinstance(dugum, dict):
        for anahtar, deger in dugum.items():
            depo.add(anahtar)
            _tum_anahtarlar(deger, depo)
    elif isinstance(dugum, (list, tuple)):
        for eleman in dugum:
            _tum_anahtarlar(eleman, depo)
    return depo


def test_not_modelled_blogu_yayimlaniyor(boru_motor):
    _, sonuc = boru_motor
    assert 'not_modelled' in sonuc, 'A10 beyan bloğu sonuç şemasında yok'
    beyanlar = sonuc['not_modelled']
    eksik = BEKLENEN_BEYANLAR - set(beyanlar)
    assert not eksik, f'Eksik NOT_MODELLED beyanı: {sorted(eksik)}'
    for ad, metin in beyanlar.items():
        assert isinstance(metin, str) and metin.startswith('NOT_MODELLED'), (
            f'{ad} beyanı NOT_MODELLED etiketiyle başlamalı')
        # Beyan metni kalemin kendisini adıyla anmalı ("havada" cümle yasak):
        # anahtarın en az bir sözcüğü metinde geçmeli.
        sozcukler = [p for p in ad.split('_') if len(p) > 3]
        assert any(s in metin.lower() for s in sozcukler), (
            f'{ad} beyanı kendi alanını adıyla anmıyor')
    assert sonuc.get('not_modelled_basis'), 'Blok gerekçe beyanı yok'


def test_beyanlar_yalan_degil(boru_motor):
    """Beyan edilen hesabın modellenmiş karşılığı sonuçta YOK olmalı."""
    _, sonuc = boru_motor
    anahtarlar = _tum_anahtarlar({k: v for k, v in sonuc.items()
                                  if k != 'not_modelled'})
    for beyan, yasakli in CELISKI_ANAHTARLARI.items():
        cakisan = anahtarlar & yasakli
        assert not cakisan, (
            f'"{beyan}" NOT_MODELLED beyanlı ama sonuçta modellenmiş '
            f'karşılığı var: {sorted(cakisan)} — ya model eklendi ve beyan '
            f'çürüdü (beyanı kaldırın) ya da alan adı çakışıyor')


def test_beyan_sayisi_eski_dorttten_fazla(boru_motor):
    """A10'un ölçütü: hibrit artık 4 beyanla gezmiyor."""
    _, sonuc = boru_motor
    assert len(sonuc['not_modelled']) >= len(BEKLENEN_BEYANLAR)


# ---------------------------------------------------------------------------
# L/D narinlik uyarısı
# ---------------------------------------------------------------------------

def _ld_kayitlari(sonuc):
    return [k for k in sonuc['design_warnings']
            if k.get('code') == LD_UYARI_KODU]


def test_ld_uyarisi_boru_motorda_cikiyor(boru_motor):
    motor, sonuc = boru_motor
    kayitlar = _ld_kayitlari(sonuc)
    assert len(kayitlar) == 1, (
        'Varsayılan girdiler L/D ≈ 19,7 boru üretir; tek bir narinlik '
        'uyarısı beklenir (teşhis: hiç uyarı çıkmıyordu)')
    kayit = kayitlar[0]
    assert kayit['severity'] == 'warning'
    # Eşik TEK kaynaktan yayımlanır (kopya eşik yasak)
    assert kayit['params']['threshold'] == GRAIN_LD_WARN_THRESHOLD
    # Değerler çözücünün KENDİ geometrisinden gelir, uydurulmaz
    assert kayit['params']['grain_ld'] == pytest.approx(
        motor.L_grain / motor.D_ch, abs=0.05)
    assert kayit['params']['chamber_ld'] == pytest.approx(
        motor.L / motor.D_ch, abs=0.05)
    # Koşul doğru davranışı sınar: bu motor gerçekten eşiğin üstünde
    assert kayit['params']['chamber_ld'] > GRAIN_LD_WARN_THRESHOLD


def test_ld_uyarisi_metni_iki_dilli_ve_oneri_iceriyor(boru_motor):
    _, sonuc = boru_motor
    metin = _ld_kayitlari(sonuc)[0]['fallback']
    # İngilizce yarı + öneri
    assert 'Increase the port count' in metin
    assert 'port diameter' in metin
    # Türkçe yarı + öneri; Türkçe karakterler ASCII'ye kaçmamış
    assert 'port sayısını artırın' in metin
    assert 'port çapını büyütün' in metin
    assert 'aşıyor' in metin


def test_ld_uyarisi_yer_tutuculari_parametrelerle_eslesiyor(boru_motor):
    """Ekranda ham {x} kalmasın: fallback'teki her yer tutucu params'ta var."""
    _, sonuc = boru_motor
    kayit = _ld_kayitlari(sonuc)[0]
    yer_tutucular = set(re.findall(r'\{(\w+)\}', kayit['fallback']))
    assert yer_tutucular == set(kayit['params'])


def test_ld_uyarisi_kompakt_motorda_cikmiyor(kompakt_motor):
    motor, sonuc = kompakt_motor
    # Önkoşul gerçek: çok-port aynı görevi eşiğin altına indiriyor
    assert motor.L / motor.D_ch < GRAIN_LD_WARN_THRESHOLD
    assert not _ld_kayitlari(sonuc), (
        'Eşiğin altındaki motor narinlik uyarısı almamalı')


def test_ld_kodu_i18n_sozluk_bekcisiyle_catismaz(boru_motor):
    """Kod motor çeviri öneki taşımaz ama fallback metni taşır.

    Çeviri sözlüğü (i18n_common.js) bu değişikliğin kapsamı dışında; motor
    önekli bir kod sözlükte karşılıksız kalıp i18n bekçisini kırardı ve
    kullanıcı ham anahtar görürdü. Fallback yolu her iki uyarı
    görüntüleyicide de (app.js, analysis_dock.js) desteklidir.
    """
    _, sonuc = boru_motor
    kayit = _ld_kayitlari(sonuc)[0]
    assert not kayit['code'].startswith('warn.')
    assert isinstance(kayit.get('fallback'), str)
    assert len(kayit['fallback']) > 80


# ---------------------------------------------------------------------------
# T60 — toplam motor boyu iki tanım
# ---------------------------------------------------------------------------

def test_t60_iki_uzunluk_alani_ayrik_ve_tutarli(boru_motor):
    _, sonuc = boru_motor
    boyutlar = sonuc['design_summary']['key_dimensions']
    # Eski alan geriye uyum için aynen; açık adlı ikizi ona eşit
    assert boyutlar['total_motor_length_chamber_nozzle_mm'] == pytest.approx(
        boyutlar['total_motor_length_mm'])
    kapak = boyutlar['forward_closure_length_mm']
    assert kapak is not None and kapak > 0
    assert boyutlar['total_motor_length_with_caps_mm'] == pytest.approx(
        boyutlar['total_motor_length_mm'] + kapak, rel=1e-9)
    # Kapak boyu yapısal kapak analizinin GERÇEK değeri (uydurma değil)
    kapak_analizi = sonuc['structural_analysis']['end_cap_analysis']
    assert kapak == pytest.approx(
        kapak_analizi['head_thickness_used_mm'], rel=1e-9)


def test_t60_beyani_iki_tanimi_da_anlatiyor(boru_motor):
    _, sonuc = boru_motor
    beyan = sonuc['design_summary']['key_dimensions'][
        'total_motor_length_basis']
    assert 'EXCLUDES the forward closure' in beyan
    assert 'with_caps' in beyan
    assert 'end-cap' in beyan or 'end cap' in beyan


def test_t60_yapisal_analiz_yoksa_kapakli_boy_uydurulmaz(boru_motor):
    motor, _ = boru_motor
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sonuc = motor._compile_results()  # yapısal sonuç verilmedi
    boyutlar = sonuc['design_summary']['key_dimensions']
    assert boyutlar['total_motor_length_with_caps_mm'] is None
    assert boyutlar['forward_closure_length_mm'] is None
    assert 'not fabricated' in boyutlar['total_motor_length_basis']


def test_sonuc_json_serilestirilebilir(boru_motor):
    """Yeni bloklar (not_modelled, T60 alanları) yanıt sözleşmesini bozmaz."""
    _, sonuc = boru_motor
    json.dumps({'not_modelled': sonuc['not_modelled'],
                'not_modelled_basis': sonuc['not_modelled_basis'],
                'key_dimensions': sonuc['design_summary']['key_dimensions'],
                'design_warnings': sonuc['design_warnings']})
