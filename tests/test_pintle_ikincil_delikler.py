"""Pintle ikincil delik seçimi ve iki blok arasındaki künye (v2.6.27).

Ayberk'in 2. maddesi: "Pintle Injector seçilip Secondary Holes = Radial Holes
yapıldığında radyal delik geometrisi oluşmuyor." Ölçüm iki ayrı kusur buldu:

  1. ``secondary_holes`` alanı sayfada duruyordu ama toplayıcı okumuyordu ve
     arka uçta TEK SATIR karşılığı yoktu. Ölçüldü: none/radial/tangential
     için yayımlanan enjektör bloğu BAYT BAYT AYNIYDI.
  2. Asıl sebep kullanıcının sandığı değildi: depoda İKİ bağımsız enjektör
     modülü vardı ve radyal delik modeli YALNIZ kardeş modüldeydi
     (``engines/injector_design.py``). Ekrana çizilen model
     (``utils/injector_design.py``) pintle'ı çıplak bir anülüs sanıyordu.

Birleştirmeden sonra ikisi de aynı ``pintle_tip_geometry`` fonksiyonunu
çağırıyor, ama FARKLI pintle çapıyla besleniyorlar: ekran bloğu kullanıcının
form değerini, motor bloğu akıştan kendinden tutarlı çözülen değeri. Sayılar
farklı olabilir — yanlış olan, hangisinin ne olduğunun YAZMAMASIYDI.

Bu dosya üç sözleşmeyi kilitler:
  A) ``secondary_holes`` seçimi sonuca GERÇEKTEN giriyor,
  B) 'none' seçiminde TMR ve sprey konisi UYDURULMUYOR (tanımsız kalıyor),
  C) ekran bloğu pintle çapının kaynağını ve akıştan boyutlandırılan
     karşılığını BEYAN ediyor; imal edilemez uç sessiz kalmıyor.
"""

import pytest

from hrma.app import app

HIBRIT_PINTLE = {
    'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 2.5, 'expansion_ratio': 0,
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'injector_type': 'pintle',
}


@pytest.fixture(scope='module')
def istemci():
    return app.test_client()


def _enjektor(istemci, **ek):
    r = istemci.post('/calculate', json=dict(HIBRIT_PINTLE, **ek))
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return (r.get_json() or {}).get('injector') or {}


@pytest.fixture(scope='module')
def uc_secim(istemci):
    return {s: _enjektor(istemci, secondary_holes=s)
            for s in ('none', 'radial', 'tangential')}


# --------------------------------------------------------------------------
# A) Seçim sonuca giriyor
# --------------------------------------------------------------------------

def test_uc_secim_farkli_sonuc_uretir(uc_secim):
    """Kusurun kendisi buydu: üç seçim bayt bayt aynı bloğu üretiyordu."""
    imzalar = {s: repr(sorted(b.items(), key=lambda kv: kv[0]))
               for s, b in uc_secim.items()}
    assert len(set(imzalar.values())) == 3, (
        'secondary_holes seçimi sonucu değiştirmiyor: '
        + ', '.join('%s==%s' % (a, b)
                    for a in imzalar for b in imzalar
                    if a < b and imzalar[a] == imzalar[b]))


def test_secim_kunyeye_yaziliyor(uc_secim):
    for secim, blok in uc_secim.items():
        g = blok.get('pintle_geometry') or {}
        assert g.get('secondary_holes') == secim


# --------------------------------------------------------------------------
# B) 'none' gerçek bir geometri değişikliği, uydurma yok
# --------------------------------------------------------------------------

def test_none_secildiginde_radyal_delik_kalmaz(uc_secim):
    g = uc_secim['none'].get('pintle_geometry') or {}
    assert g['n_radial_holes'] == 0
    assert g['radial_hole_d_mm'] == 0.0
    assert g['radial_flow_fraction'] == 0.0


def test_none_secildiginde_tmr_ve_sprey_acisi_uydurulmaz(uc_secim):
    """Radyal jet yoksa TMR tanımsızdır; sayı basmak uydurma olurdu."""
    g = uc_secim['none'].get('pintle_geometry') or {}
    assert g['tmr'] is None
    assert g['spray_half_angle_deg'] is None
    assert 'NOT_APPLICABLE' in (g.get('tmr_basis') or '')


def test_radial_secildiginde_gercek_delik_dizisi_var(uc_secim):
    g = uc_secim['radial'].get('pintle_geometry') or {}
    assert g['n_radial_holes'] >= 4
    assert g['radial_hole_d_mm'] > 0.0
    assert g['tmr'] is not None and g['spray_half_angle_deg'] is not None


def test_tangential_ayni_alani_kullanir_ama_girdabi_modellemedigini_soyler(uc_secim):
    """Delik sayısı/çapı radyalle aynı (aynı alan, aynı ΔP); fark BEYANDA."""
    r = uc_secim['radial'].get('pintle_geometry') or {}
    t = uc_secim['tangential'].get('pintle_geometry') or {}
    assert t['n_radial_holes'] == r['n_radial_holes']
    assert t['radial_hole_d_mm'] == pytest.approx(r['radial_hole_d_mm'])
    assert t.get('tangential_momentum_modelled') is False
    assert 'NOT_MODELLED' in (t.get('tangential_basis') or '')
    # Bildirilen açının ALT SINIR olduğu söylenmeli — yoksa kullanıcı onu
    # gerçek koni sanır.
    assert 'lower bound' in (t.get('tangential_basis') or '')


def test_none_secildiginde_pintle_olmadigi_uyarilir(uc_secim):
    uyarilar = ' '.join(str(x) for x in (uc_secim['none'].get('warnings') or []))
    assert 'annular injector' in uyarilar, (
        "'none' seçiminde eleman artık pintle değil; kullanıcıya söylenmeli")


# --------------------------------------------------------------------------
# C) İki blok çelişmesin: künye pintle çapının kaynağını söylesin
# --------------------------------------------------------------------------

def test_ekran_blogu_pintle_capinin_kaynagini_beyan_eder(uc_secim):
    g = uc_secim['radial'].get('pintle_geometry') or {}
    assert 'user input' in (g.get('d_pintle_source') or ''), (
        'ekran bloğu pintle çapının kullanıcı girdisi olduğunu söylemiyor; '
        'aynı yanıttaki motor bloğu akıştan çözülen BAŞKA bir çap taşıyor ve '
        'kullanıcı iki sayının neden farklı olduğunu göremiyor')


def test_akistan_boyutlandirilan_karsilik_da_yayimlanir(uc_secim):
    g = uc_secim['radial'].get('pintle_geometry') or {}
    for alan in ('flow_sized_d_pintle_mm', 'flow_sized_n_radial_holes',
                 'flow_sized_radial_hole_d_mm', 'flow_sizing_basis'):
        assert alan in g, f'{alan} yayımlanmıyor'
    assert g['flow_sized_d_pintle_mm'] > 0
    assert g['flow_sized_n_radial_holes'] >= 4


def test_imal_edilemez_uc_sessiz_kalmaz(istemci):
    """Kullanıcının çapı delikleri imalat sınırının altına düşürüyorsa UYAR.

    Ölçüldü (1 kN, Pc 20 bar, HTPB/N2O): form varsayılanı 25 mm pintle ile
    uç 182 x 0,250 mm delik istiyor — modülün pintle geometrisi için beyan
    ettiği 0,30 mm alt sınırının altında, yani uç çizildiği gibi imal
    edilemez. Eskiden bu sayı sessizce basılıyordu.
    """
    blok = _enjektor(istemci, secondary_holes='radial', pintle_diameter=25)
    g = blok.get('pintle_geometry') or {}
    if g['radial_hole_d_mm'] >= 0.30:
        pytest.skip('bu tasarımda delikler imalat bandının içinde')
    uyarilar = ' '.join(str(x) for x in (blok.get('warnings') or []))
    assert 'not manufacturable' in uyarilar
    # Uyarı SEBEBİ ve çözümü de söylemeli: sürücü pintle çapıdır.
    assert 'flow-sized diameter' in uyarilar
