"""Faz 6 — tarayıcı denetiminin KÖK nedenleri (ana model tarafından kapatıldı).

Bu üç kalem tek bir ajanın dosya sınırına sığmadığı için düzeltme dalgasında
açık kalmıştı; her biri "arayüz doğru davranıyor ama beslendiği veri yanlış"
sınıfından.

* **T11** — kullanıcının girdiği tank basıncı motor sonucuna hiç yazılmıyordu.
* **T07** — dış yüzey yanarken tükenen web yayımlanmıyordu, son port hep grain
  dış çapı sanılıyordu.
* **T18** — 3B performans yüzeyi motorun iticileriyle değil sabit bir referans
  çiftiyle çözülüyordu.
"""

import json

import pytest

from hrma.app import app
from hrma.export.motor_geometry import solid_results_to_motor_geometry


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _basinc_cubugu(cizimler):
    """Basınç dağılımı çubuğunu (x'inde 'Chamber' geçen) bulur."""
    for fig in (cizimler or {}).values():
        if isinstance(fig, str):
            try:
                fig = json.loads(fig)
            except Exception:
                continue
        for t in (fig or {}).get('data', []):
            if t.get('type') == 'bar' and 'Chamber' in (t.get('x') or []):
                return list(t['x']), list(t['y'])
    return None, None


# ---------------------------------------------------------------------------
# T11 — tank basıncı
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('tank_bar', [30.0, 50.0, 90.0])
def test_t11_tank_basinci_yanita_ve_cubuga_yansiyor(istemci, tank_bar):
    """Kullanıcının girdiği tank basıncı hem sonuçta hem çubukta görünmeli.

    Arıza (ölçüldü): 30 / 50 / 90 bar girilen üç koşuda da çubuk sabit 24 bar
    gösteriyordu, çünkü motor sözlüğünde 'tank' geçen anahtar YOKTU. Değer
    çözücüde vardı (kavitasyon uyarısı P_v ile tutarlıydı) ama yayımlanmıyordu.

    Alanın **grafiklerden ÖNCE** konması şart: sonuç sözlüğü kurulurken
    eklenirse çubuk onu göremez — düzeltme sırasında tam bu hata yapıldı ve
    ölçümle yakalandı, bu test o gerilemeyi de yakalar.
    """
    g = {'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
         'chamber_pressure': 20, 'tank_pressure': tank_bar,
         'oxidizer_type': 'n2o', 'fuel_type': 'htpb', 'of_ratio': 6.0}
    y = istemci.post('/calculate', json=g)
    assert y.status_code == 200, y.get_data(as_text=True)[:300]
    d = y.get_json()

    motor = d.get('motor') or {}
    assert motor.get('tank_pressure') == pytest.approx(tank_bar), (
        'motor sonucunda tank_pressure yok ya da yanlış: %r' % motor.get('tank_pressure'))
    assert motor.get('tank_pressure_source') == 'user_input'

    x, deger = _basinc_cubugu(d.get('plots'))
    assert x is not None, 'basınç dağılımı çubuğu figürlerde yok'
    assert 'Tank' in x, "tank basıncı verildiği hâlde çubukta 'Tank' etiketi yok: %s" % x
    assert deger[x.index('Tank')] == pytest.approx(tank_bar), (
        'çubuk kullanıcının girdiği tank basıncını göstermiyor: %s = %s' % (x, deger))


def test_t11_tank_basinci_yoksa_cubuk_tank_demez(istemci):
    """Tank basıncı verilmediğinde çubuk 'Tank' diye YALAN SÖYLEMEZ.

    Geri düşüş değeri (Pc + ΔP) yanlış değil; yanlış olan onu 'Tank' diye
    etiketlemekti. Dürüst etiket: 'Inj. inlet'.
    """
    g = {'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
         'chamber_pressure': 20, 'oxidizer_type': 'n2o', 'fuel_type': 'htpb',
         'of_ratio': 6.0}
    y = istemci.post('/calculate', json=g)
    assert y.status_code == 200
    x, deger = _basinc_cubugu(y.get_json().get('plots'))
    assert x is not None
    assert 'Tank' not in x, (
        "tank basıncı verilmediği hâlde çubuk 'Tank' diye etiketlenmiş: %s" % x)


# ---------------------------------------------------------------------------
# T07 — son port çapı
# ---------------------------------------------------------------------------

def _kati_sonuc(istemci, inhibit_outer):
    g = {'motor_type': 'solid', 'chamber_diameter': 100, 'outer_diameter': 100,
         'core_diameter': 30, 'grain_length': 500, 'grain_count': 3,
         'propellant_type': 'apcp', 'chamber_pressure': 40,
         'inhibit_outer': inhibit_outer}
    y = istemci.post('/calculate_solid', json=g)
    assert y.status_code == 200, y.get_data(as_text=True)[:300]
    return y.get_json()


def test_t07_son_port_inhibitor_duzenine_gore_degisir(istemci):
    """Dış yüzey de yanıyorsa son port grain dış çapı OLAMAZ.

    Arıza (ölçüldü): inhibitör açık/kapalı arasında yanma süresi 1,80 s ->
    1,07 s değişiyordu — yani çözücü tükenmenin yarıya indiğini biliyordu —
    ama ``port_diameter_final`` iki koşuda da 100,0 mm dönüyordu.

    İki cepheli yanmada cephe hem içten hem dıştan ilerler, tükenme yarı
    web'te olur ve grain dışı hiçbir zaman porta dönüşmez.
    """
    tek = _kati_sonuc(istemci, True)    # yalnız iç yüzey yanar
    cift = _kati_sonuc(istemci, False)  # iç + dış yüzey yanar

    gd_tek = tek.get('grain_design') or {}
    gd_cift = cift.get('grain_design') or {}

    # Çözücü tükenen web'i ve dayanağını yayımlamalı
    assert gd_tek.get('web_basis') == 'single_sided'
    assert gd_cift.get('web_basis') == 'two_sided'
    assert gd_cift['web_burnout_mm'] == pytest.approx(gd_tek['web_burnout_mm'] / 2.0)

    p_tek = solid_results_to_motor_geometry(tek)['port_diameter_final'] * 1000
    p_cift = solid_results_to_motor_geometry(cift)['port_diameter_final'] * 1000

    # Tek cepheli: web tamamen tükenir, son port = grain dış çapı
    assert p_tek == pytest.approx(100.0, abs=0.5)
    # İki cepheli: son port = çekirdek + 2 × tükenen web = 30 + 2×17,5 = 65
    assert p_cift == pytest.approx(65.0, abs=0.5), (
        'iki cepheli yanmada son port %s mm — grain dış çapı yazılmış olabilir' % p_cift)
    assert p_cift < p_tek, 'son port inhibitör düzeninden bağımsız çıkıyor'


def test_t07_son_port_grain_disini_asamaz(istemci):
    """Son port hiçbir koşulda grain dış çapını geçmemeli (fiziksel sınır)."""
    for inh in (True, False):
        d = _kati_sonuc(istemci, inh)
        gd = d.get('grain_design') or {}
        geo = solid_results_to_motor_geometry(d)
        assert geo['port_diameter_final'] * 1000 <= gd['outer_diameter_mm'] + 1e-6


# ---------------------------------------------------------------------------
# T18 — 3B performans yüzeyinin itici kimliği
# ---------------------------------------------------------------------------

TEMEL = {'analysis_type': '3d_surface', 'chamber_pressure': 50,
         'expansion_ratio': 12, 'chamber_temperature': 3500, 'gamma': 1.2,
         'optimal_of_ratio': 2.3, 'base_isp': 300, 'mdot_total': 3.4,
         'throat_area': 0.004, 'chamber_length': 0.4, 'chamber_diameter': 0.2,
         'burn_time': 400}


def _yuzey(istemci, ek):
    g = dict(TEMEL)
    g.update(ek)
    y = istemci.post('/api/advanced-performance-analysis', json=g)
    assert y.status_code == 200, y.get_data(as_text=True)[:300]
    pd = y.get_json().get('plot_data')
    if isinstance(pd, str):
        pd = json.loads(pd)
    for t in (pd or {}).get('data', []):
        if t.get('type') == 'surface' and t.get('z'):
            return t['z']
    pytest.fail('3B yüzey izi yanıtta yok')


def test_t18_yuzey_itici_kimligine_duyarli(istemci):
    """Farklı itici çifti verilince yüzey DEĞİŞMELİ.

    Arıza: uç ``fuel_type`` / ``oxidizer_type`` alanlarını okuyordu ama panel
    onları hiç göndermiyordu; RP-1/LOX sayfasında bile denge yüzeyi N2O/HTPB
    referans çiftiyle çözülüyor, üstüne o yüzeye ait olmayan bir tasarım
    noktası basılıyordu.
    """
    kimliksiz = _yuzey(istemci, {})
    rp1_lox = _yuzey(istemci, {'fuel_type': 'rp1', 'oxidizer_type': 'lox'})
    assert rp1_lox != kimliksiz, (
        'itici kimliği verildiği hâlde yüzey aynı — uç kimliği yok sayıyor')


def test_t18_panel_itici_kimligini_gonderiyor():
    """``performance_panel.js`` motorun iticilerini isteğe ekliyor mu?

    Kaynak taraması: tarayıcı testi olmadan da gerilemeyi yakalar.
    """
    import os
    yol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'hrma', 'static', 'js', 'panels', 'performance_panel.js')
    with open(yol, encoding='utf-8') as f:
        kaynak = f.read()
    assert 'payload.fuel_type' in kaynak and 'payload.oxidizer_type' in kaynak, (
        'panel isteğe itici kimliğini eklemiyor — 3B yüzey yanlış çiftle çözülür')
    assert 'sonIticiler' in kaynak, 'itici kimliği motor sonucundan yakalanmıyor'
