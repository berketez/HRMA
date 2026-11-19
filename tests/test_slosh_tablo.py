"""3.0.7 K1.0 — çalkantı eşdeğer model tablosu sözleşmesi (slosh_tablo).

Sözleşme: docs/tasarim/v307/CALKANTI_6DOF_TASARIM.md §2 ve
TANK_GEOMETRI_TASARIM.md §F. Bu dosya sözleşmenin kendisini kilitler:
ızgara, şema doğrulayıcısı, özdeşlikler, JSON/CSV gidiş-dönüş, PCHIP ara
değer kuralları, sebep kodu sınıfları ve okuyucu kapıları.

Tablo kurucusu (fixture) dik silindirin kapalı biçim ifadelerini bu dosyada
BAĞIMSIZ olarak yazar (Dodge 2000 Denk. (1.40), Tablo 3.2; CALKANTI
§A.1.1); üretim kodundaki silindir üreticisine dayanmaz.
"""

import copy
import math

import numpy as np
import pytest
from scipy.special import jnp_zeros

from hrma.analysis import slosh_tablo as st

XI1 = float(jnp_zeros(1, 1)[0])


def _silindir_satiri(d, R, H, rho):
    V_ic = math.pi * R * R * H
    V = d * V_ic
    h = V / (math.pi * R * R)
    m = rho * V
    t = math.tanh(XI1 * h / R)
    k1 = XI1 / R * t
    m1 = 2.0 * R * t / (XI1 * (XI1 ** 2 - 1.0) * h)
    z1 = h - (2.0 * R / XI1) * math.tanh(XI1 * h / (2.0 * R))
    z_km = h / 2.0
    m0 = 1.0 - m1
    z0 = (z_km - m1 * z1) / m0
    return {
        'doluluk': d, 'h_m': h, 'V_sivi_m3': V, 'm_sivi_kg': m,
        'z_km_m': z_km, 'I_km_donmus_kgm2': m * (R * R / 4 + h * h / 12),
        'I_eksenel_donmus_kgm2': 0.5 * m * R * R,
        'A_yuzey_m2': math.pi * R * R, 'R_yuzey_m': R,
        'kappa1_1m': k1, 'L1_m': 1.0 / k1, 'm1_oran': m1, 'z1_m': z1,
        'z_aski_m': z1 + 1.0 / k1, 'm0_oran': m0, 'z0_m': z0,
        'I0_kgm2': None, 'I0_kaynak': None,
        'Gamma1': (XI1 ** 2 - 1.0) / (2.0 * XI1 * t),
        'durum': st.DURUM_GECERLI, 'sebep': [],
    }


def _silindir_verisi(R=0.5, H=2.0, rho=1000.0):
    return {
        'sema': st.SEMA_ADI, 'sema_surumu': st.SEMA_SURUMU,
        'tank_id': 'oksitleyici',
        'geometri': {'tur': st.GEOMETRI_DIK_SILINDIR, 'R_ref_m': R,
                     'H_ic_m': H, 'V_ic_m3': math.pi * R * R * H,
                     'kaynak': 'kullanıcı girdisi'},
        'sivi': {'ad': 'su', 'rho_kg_m3': rho, 'sigma_N_m': None,
                 'nu_m2_s': None},
        'yontem': st.YONTEM_KAPALI_BICIM,
        'satirlar': [_silindir_satiri(d, R, H, rho)
                     for d in st.DOLULUK_IZGARASI],
    }


@pytest.fixture
def veri():
    return _silindir_verisi()


def _red(veri):
    """Doğrulayıcının reddini döner; kodu test gövdesi iddia eder."""
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.SloshTablo.sozlukten(veri)
    return e.value


# ---------------------------------------------------------------- ızgara ---
def test_izgara_29_nokta_8_13_8():
    g = st.DOLULUK_IZGARASI
    assert len(g) == 29
    assert all(b > a for a, b in zip(g, g[1:]))
    assert g[:8] == (0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15)
    orta = g[8:21]
    assert len(orta) == 13
    assert np.allclose(orta, np.arange(0.20, 0.8001, 0.05), atol=1e-15, rtol=0)
    assert g[21:] == (0.85, 0.90, 0.925, 0.95, 0.97, 0.98, 0.99, 0.995)
    assert 0.0 < g[0] and g[-1] < 1.0


def test_sebep_kodlari_tasarim_listesini_kapsar():
    tasarim = {'BOND_DUSUK_RET', 'BOND_BEYAN', 'BOND_HESAPLANAMADI',
               'IZGARA_DISI', 'KUBBE_BOLGESI_SILINDIR_FORMULU_YOK',
               'EKSENEL_SIMETRIK_DEGIL', 'YUZEY_KAPALI_DEGIL',
               'BAFL_GECERLILIK_DISI', 'GENLIK_DOGRUSAL_SINIR_DISI',
               'EKSIK_BOLGE', 'PROFIL_TEK_DEGERLI_DEGIL',
               'PROFIL_AG_HACIM_TUTARSIZ', 'AG_YAKINSAMA_ZAYIF', 'BIRIM_YOK',
               'STEP_MOZAIK_YOK'}
    assert tasarim <= set(st.SEBEP_KODLARI)
    for kod, (sinif, anlam) in st.SEBEP_KODLARI.items():
        assert sinif in (st.SINIF_RET, st.SINIF_BEYAN), kod
        assert anlam.strip()


# ------------------------------------------------------------ doğrulayıcı ---
def test_gecerli_silindir_tablosu_kabul(veri):
    t = st.SloshTablo.sozlukten(veri)
    assert t.tank_id == 'oksitleyici'
    assert len(t.satirlar) == 29


def test_bilinmeyen_alan_reddi(veri):
    veri['satirlar'][3]['kappa_1m'] = 1.0
    e = _red(veri)
    assert e.kod == 'ALAN_BILINMEYEN', str(e)
    assert e.alan == 'satirlar[3].kappa_1m'


def test_eksik_alan_reddi(veri):
    del veri['satirlar'][0]['Gamma1']
    assert _red(veri).kod == 'ALAN_EKSIK'


def test_surum_reddi(veri):
    veri['sema_surumu'] = 'v307-0'
    assert _red(veri).kod == 'SURUM_UYUSMAZ'


def test_izgara_uyusmaz_reddi(veri):
    veri['satirlar'][5]['doluluk'] = 0.074
    assert _red(veri).kod == 'IZGARA_UYUSMAZ'
    v2 = _silindir_verisi()
    v2['satirlar'].pop()
    assert _red(v2).kod == 'IZGARA_UYUSMAZ'


def test_L1_ozdesligi_kirilinca_red(veri):
    veri['satirlar'][10]['L1_m'] *= 1.001
    e = _red(veri)
    assert e.kod == 'DEGISMEZ_IHLALI', str(e)
    assert e.alan == 'satirlar[10].L1_m'


def test_m0_z0_ozdesligi_kirilinca_red(veri):
    veri['satirlar'][12]['z0_m'] += 1e-4
    assert _red(veri).kod == 'DEGISMEZ_IHLALI'


def test_silindir_atalet_ozdesligi_kirilinca_red(veri):
    veri['satirlar'][7]['I_km_donmus_kgm2'] *= 1.01
    assert _red(veri).kod == 'DEGISMEZ_IHLALI'


def test_nan_ve_bool_reddi(veri):
    v = copy.deepcopy(veri)
    v['satirlar'][2]['m1_oran'] = float('nan')
    assert _red(v).kod == 'DEGER_GECERSIZ'
    v = copy.deepcopy(veri)
    v['sivi']['rho_kg_m3'] = True
    assert _red(v).kod == 'TUR_HATASI'


def test_durum_sebep_tutarliligi(veri):
    v = copy.deepcopy(veri)
    v['satirlar'][0]['sebep'] = ['BOND_BEYAN']          # GECERLI + BEYAN kodu
    assert _red(v).kod == 'DURUM_SEBEP_TUTARSIZ'
    v = copy.deepcopy(veri)
    v['satirlar'][0]['durum'] = st.DURUM_RET             # RET ama kod yok
    assert _red(v).kod == 'DURUM_SEBEP_TUTARSIZ'
    v = copy.deepcopy(veri)
    v['satirlar'][0]['sebep'] = ['UYDURMA_KOD']
    v['satirlar'][0]['durum'] = st.DURUM_BEYANLI
    assert _red(v).kod == 'SEBEP_BILINMEYEN'


def test_ret_satirinda_model_null_olabilir_baskasinda_olamaz(veri):
    v = copy.deepcopy(veri)
    for k in st.SATIR_MODEL:
        v['satirlar'][0][k] = None
    v['satirlar'][0]['durum'] = st.DURUM_RET
    v['satirlar'][0]['sebep'] = ['KUBBE_BOLGESI_SILINDIR_FORMULU_YOK']
    st.SloshTablo.sozlukten(v)
    v['satirlar'][1]['kappa1_1m'] = None
    assert _red(v).kod == 'DEGER_GECERSIZ'


def test_profilli_tankta_kapali_bicim_beyansiz_gecemez(veri):
    R, H = 0.5, 2.0
    veri['geometri'] = {'tur': st.GEOMETRI_PROFIL, 'R_ref_m': R, 'H_ic_m': H,
                        'V_ic_m3': math.pi * R * R * H,
                        'kaynak': 'motor tasarımı',
                        'profil_rz_m': [[0.0, 0.0], [R, 0.0], [R, H],
                                        [0.0, H]]}
    assert _red(veri).kod == 'DURUM_SEBEP_TUTARSIZ'
    for s in veri['satirlar']:
        s['durum'] = st.DURUM_BEYANLI
        s['sebep'] = ['TANK_BASLARI_MODELLENMEDI']
    st.SloshTablo.sozlukten(veri)


def test_I0_kaynaksiz_verilemez(veri):
    veri['satirlar'][4]['I0_kgm2'] = 1.0
    assert _red(veri).kod == 'ALAN_EKSIK'


# ----------------------------------------------------------- gidiş-dönüş ---
def test_json_gidis_donus_bit_ayni(veri):
    t = st.SloshTablo.sozlukten(veri)
    metin = st.json_yaz(t)
    t2 = st.json_oku(metin)
    assert t2.sozluk() == t.sozluk()
    t3 = st.json_oku(metin.encode('utf-8'))
    assert t3.sozluk() == t.sozluk()


def test_csv_gidis_donus_bit_ayni(veri):
    veri['satirlar'][3]['ek'] = {'p_gozlenen': 3.97, 'not': 'a,b;c'}
    veri['satirlar'][4]['I0_kgm2'] = 2.5
    veri['satirlar'][4]['I0_kaynak'] = 'SP-106 Tablo 6.1 (yaklaşık), "x"'
    for s in veri['satirlar']:
        s['kappa2_1m'] = s['kappa1_1m'] * 3.0
        s['m2_oran'] = s['m1_oran'] * 0.03
        s['z2_m'] = s['z1_m']
    veri['kunye'] = ['Dodge 2000 Denk. (1.40)', 'SP-8009 Tablo I']
    t = st.SloshTablo.sozlukten(veri)
    metin = st.csv_yaz(t)
    assert metin.startswith(st.CSV_KIMLIK_SATIRI + '\n')
    t2 = st.csv_oku(metin)
    assert t2.sozluk() == t.sozluk()


def test_json_nan_metni_reddedilir(veri):
    metin = st.json_yaz(st.SloshTablo.sozlukten(veri))
    bozuk = metin.replace('"sigma_N_m": null', '"sigma_N_m": NaN', 1)
    assert bozuk != metin
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.json_oku(bozuk)
    assert e.value.kod == 'DEGER_GECERSIZ'


def test_okuyucu_boyut_ve_bicim_kapilari():
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.json_oku(b' ' * (st.TABLO_DOSYA_BOYUT_SINIRI + 1))
    assert e.value.kod == 'BOYUT_SINIRI'
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.json_oku(b'\xff\xfe{}')
    assert e.value.kod == 'BICIM_HATASI'
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.json_oku('[1, 2]')
    assert e.value.kod == 'BICIM_HATASI'
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.json_oku('{"a": ')
    assert e.value.kod == 'BICIM_HATASI'
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.csv_oku('doluluk\n1\n2\n')
    assert e.value.kod == 'SURUM_UYUSMAZ'


def test_csv_baslik_degisirse_red(veri):
    metin = st.csv_yaz(st.SloshTablo.sozlukten(veri))
    bozuk = metin.replace('kappa1_1m', 'kappa_1m', 1)
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.csv_oku(bozuk)
    assert e.value.kod == 'BICIM_HATASI'


# --------------------------------------------------------------- ara değer ---
def test_ara_dugumde_satirin_kendisi(veri):
    t = st.SloshTablo.sozlukten(veri)
    for i in (0, 9, 28):
        s = t.ara(st.DOLULUK_IZGARASI[i])
        for k in st.SATIR_GEOMETRI + st.SATIR_MODEL:
            assert s[k] == t.satirlar[i][k], (i, k)


def test_ara_ozdeslikler_ve_kappa_log_olcek(veri):
    t = st.SloshTablo.sozlukten(veri)
    for d in (0.0075, 0.0125, 0.033, 0.42, 0.9375, 0.9925):
        s = t.ara(d)
        assert s['durum'] == st.DURUM_GECERLI
        assert s['L1_m'] == 1.0 / s['kappa1_1m']
        assert s['m0_oran'] == 1.0 - s['m1_oran']
        assert s['z_aski_m'] == s['z1_m'] + s['L1_m']
        assert abs(s['m0_oran'] * s['z0_m'] + s['m1_oran'] * s['z1_m']
                   - s['z_km_m']) < 1e-15
        # PCHIP monoton: komşu satırlar arasında kalır.
        i = int(np.searchsorted(st.DOLULUK_IZGARASI, d)) - 1
        a, b = t.satirlar[i], t.satirlar[i + 1]
        for k in ('kappa1_1m', 'm1_oran', 'z1_m'):
            lo, hi = sorted((a[k], b[k]))
            assert lo <= s[k] <= hi, (d, k)
        # Silindirde h doluluğun doğrusal fonksiyonu; PCHIP onu korur.
        assert abs(s['h_m'] - d * 2.0) < 1e-12


def test_ara_log_log_sig_uc_dogru():
    """Sığ uçta κ1 ∝ h, z1 ∝ h³: log-log PCHIP kuvvet yasasını taşır
    (tasarım düzeltmesi; ilk metindeki log-κ1 doğrusal-doluluk %2,3 hata
    verdi)."""
    for H in (0.25, 1.0, 5.0):
        t = st.SloshTablo.sozlukten(_silindir_verisi(R=1.0, H=H))
        x = np.array(st.DOLULUK_IZGARASI)
        for d in (x[:-1] + x[1:]) / 2.0:
            gercek = _silindir_satiri(d, 1.0, H, 1000.0)
            s = t.ara(d)
            for k in ('kappa1_1m', 'm1_oran', 'z1_m', 'Gamma1', 'h_m'):
                assert abs(s[k] / gercek[k] - 1.0) < 3e-3, (H, d, k)


def test_ara_izgara_disi_ret(veri):
    t = st.SloshTablo.sozlukten(veri)
    for d in (0.0, 0.004, 0.996, 1.0):
        s = t.ara(d)
        assert s['durum'] == st.DURUM_RET
        assert s['sebep'] == ['IZGARA_DISI']
        assert s['kappa1_1m'] is None and s['h_m'] is None


def test_ara_ret_komsulugu_ve_beyan_yayilimi(veri):
    s0 = veri['satirlar'][0]
    for k in st.SATIR_MODEL:
        s0[k] = None
    s0['durum'] = st.DURUM_RET
    s0['sebep'] = ['KUBBE_BOLGESI_SILINDIR_FORMULU_YOK']
    veri['satirlar'][20]['durum'] = st.DURUM_BEYANLI
    veri['satirlar'][20]['sebep'] = ['AG_YAKINSAMA_ZAYIF']
    t = st.SloshTablo.sozlukten(veri)
    r = t.ara(0.0075)
    assert r['durum'] == st.DURUM_RET and r['kappa1_1m'] is None
    assert r['sebep'] == ['KUBBE_BOLGESI_SILINDIR_FORMULU_YOK']
    assert r['h_m'] is not None            # geometri RET satırında da var
    b = t.ara(0.79)
    assert b['durum'] == st.DURUM_BEYANLI
    assert b['sebep'] == ['AG_YAKINSAMA_ZAYIF']
    assert t.ara(0.5)['durum'] == st.DURUM_GECERLI


def test_doluluk_kutleden(veri):
    t = st.SloshTablo.sozlukten(veri)
    s = t.satirlar[14]
    assert abs(t.doluluk_kutleden(s['m_sivi_kg']) - s['doluluk']) < 1e-15


# ------------------------------------------------------- Bond ve ω1 kapıları ---
def test_bond_esikleri_sp8009():
    assert (st.BOND_RET_ESIGI, st.BOND_BEYAN_ESIGI) == (10.0, 100.0)
    # Bo = rho g R^2 / sigma; rho = 1000, g = 1, sigma = 1 → Bo = 1000 R².
    def bo(R):
        return st.bond_degerlendir(1000.0, 1.0, R, 1.0)
    assert bo(0.05)['durum'] == st.DURUM_RET          # Bo = 2,5
    assert bo(0.05)['sebep'] == ['BOND_DUSUK_RET']
    assert bo(0.2)['durum'] == st.DURUM_BEYANLI       # Bo = 40
    assert bo(0.2)['sebep'] == ['BOND_BEYAN']
    assert bo(1.0)['durum'] == st.DURUM_GECERLI       # Bo = 1000
    yok = st.bond_degerlendir(1000.0, 1.0, 1.0, None)
    assert yok == {'Bo': None, 'durum': st.DURUM_BEYANLI,
                   'sebep': ['BOND_HESAPLANAMADI']}


def test_omega1_geff_kapisi():
    assert st.omega1(4.0, 9.0) == 6.0
    for g in (0.0, -1.0, float('nan'), float('inf'), None, True):
        with pytest.raises(st.SloshTabloHatasi) as e:
            st.omega1(1.0, g)
        assert e.value.kod == 'GEFF_POZITIF_DEGIL'


def test_tasarim_belgesi_sozlesme_metni_ayni():
    """CALKANTI §2 ve TANK §F aynı sözleşme metnini taşır; modüldeki
    sebep kodları iki belgede de geçer."""
    import pathlib
    from tests.support.kanit import kanit_gerekli
    kok = pathlib.Path(__file__).resolve().parents[1] / 'docs' / 'tasarim' / 'v307'
    for ad in ('CALKANTI_6DOF_TASARIM.md', 'TANK_GEOMETRI_TASARIM.md'):
        metin = kanit_gerekli(kok / ad).read_text(encoding='utf-8')
        for kod in st.SEBEP_KODLARI:
            assert f'`{kod}`' in metin, (ad, kod)
        assert st.SEMA_SURUMU in metin


# ------------------------------------------------- v307-2 (K6) eklemeleri ---
def test_v307_2_sebep_kodlari_ve_siniflari():
    """K6: K3b'nin AG_URETILEMEDI önerisi (RET) ve K3a'nın gürültü beyanı
    (BEYAN) sözleşmede; eklendikleri sürüm kayıtlı."""
    assert st.SEBEP_KODLARI['AG_URETILEMEDI'][0] == st.SINIF_RET
    assert st.SEBEP_KODLARI['GURULTU_ESIKLE_KIYASLANABILIR'][0] == \
        st.SINIF_BEYAN
    assert st.SEMA_SURUMU == 'v307-2'
    assert st.DESTEKLENEN_SEMA_SURUMLERI == ('v307-1', 'v307-2')
    assert set(st.SEBEP_KODU_EKLENDIGI_SURUM) == {
        'AG_URETILEMEDI', 'GURULTU_ESIKLE_KIYASLANABILIR'}
    for kod, surum in st.SEBEP_KODU_EKLENDIGI_SURUM.items():
        assert kod in st.SEBEP_KODLARI
        assert surum in st.DESTEKLENEN_SEMA_SURUMLERI
        assert kod in st.SEMA_DEGISIKLIK_GUNLUGU[surum]


def test_eski_surum_v307_1_okunur_ve_surumunu_korur(veri):
    veri['sema_surumu'] = 'v307-1'
    t = st.SloshTablo.sozlukten(veri)
    assert t.sozluk()['sema_surumu'] == 'v307-1'
    assert st.json_oku(st.json_yaz(t)).sozluk() == t.sozluk()
    metin = st.csv_yaz(t)
    assert metin.startswith(f'# {st.SEMA_ADI} v307-1\n')
    assert st.csv_oku(metin).sozluk() == t.sozluk()


def test_eski_surumde_yeni_kod_reddedilir(veri):
    veri['sema_surumu'] = 'v307-1'
    s = veri['satirlar'][5]
    s['sebep'] = ['GURULTU_ESIKLE_KIYASLANABILIR']
    s['durum'] = st.DURUM_BEYANLI
    assert _red(veri).kod == 'SEBEP_BILINMEYEN'
    veri['sema_surumu'] = 'v307-2'
    st.SloshTablo.sozlukten(veri)


@pytest.mark.parametrize('surum', ('v307-0', 'v307-3', '', None, 2))
def test_desteklenmeyen_surum_reddi(veri, surum):
    veri['sema_surumu'] = surum
    assert _red(veri).kod == 'SURUM_UYUSMAZ'


def test_csv_kimlik_ve_meta_surumu_uyusmali(veri):
    metin = st.csv_yaz(st.SloshTablo.sozlukten(veri))
    bozuk = metin.replace(st.CSV_KIMLIK_SATIRI, f'# {st.SEMA_ADI} v307-1', 1)
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.csv_oku(bozuk)
    assert e.value.kod == 'SURUM_UYUSMAZ'


def test_ag_uretilemedi_satiri_ret_ve_model_null(veri):
    s = veri['satirlar'][10]
    for k in st.SATIR_MODEL:
        s[k] = None
    s['sebep'] = ['AG_URETILEMEDI']
    s['durum'] = st.DURUM_RET
    t = st.SloshTablo.sozlukten(veri)
    d = st.DOLULUK_IZGARASI
    a = t.ara(0.5 * (d[10] + d[11]))
    assert a['durum'] == st.DURUM_RET and a['kappa1_1m'] is None
    assert a['sebep'] == ['AG_URETILEMEDI']


def test_hata_turleri_adli_sabit_ve_kapali_liste():
    """K6 (K3a devri): hata türleri adlı sabit; modülün ürettiği her tür
    listede (AST), listede olmayanla hata kurulamaz."""
    import ast
    import inspect
    kaynak = inspect.getsource(st)
    kullanilan = set()
    for d in ast.walk(ast.parse(kaynak)):
        if not isinstance(d, ast.Call):
            continue
        ad = getattr(d.func, 'id', None)
        if ad == '_hata' and d.args and isinstance(d.args[0], ast.Constant):
            kullanilan.add(d.args[0].value)
        if ad == 'SloshTabloHatasi':
            for k in d.keywords:
                if k.arg == 'kod' and isinstance(k.value, ast.Constant):
                    kullanilan.add(k.value.value)
    assert len(kullanilan) >= 10
    assert kullanilan <= set(st.HATA_KODLARI), kullanilan - set(st.HATA_KODLARI)
    for ad, kod in vars(st).items():
        if ad.startswith('HATA_') and isinstance(kod, str):
            assert kod in st.HATA_KODLARI and ad == 'HATA_' + kod
    assert len([a for a in vars(st) if a.startswith('HATA_')
                and isinstance(getattr(st, a), str)]) == len(st.HATA_KODLARI)
    assert set(st.OKUYUCU_HATA_KODLARI) <= set(st.HATA_KODLARI)
    with pytest.raises(TypeError):
        st.SloshTabloHatasi('x', kod='UYDURMA_KOD')
    e = st.SloshTabloHatasi('x', kod=st.HATA_BICIM_HATASI, alan='a')
    assert e.kunye() == {'kod': 'BICIM_HATASI', 'alan': 'a', 'mesaj': 'x'}


def test_satirlara_sebep_ekle(veri):
    veri['satirlar'][0]['sebep'] = ['BOND_BEYAN']
    veri['satirlar'][0]['durum'] = st.DURUM_BEYANLI
    t = st.SloshTablo.sozlukten(veri)
    once = t.sozluk()
    t2 = st.satirlara_sebep_ekle(t, ['GURULTU_ESIKLE_KIYASLANABILIR'],
                                 kunye_satiri='gürültü beyanı')
    assert t.sozluk() == once                      # girdi değişmez
    for s in t2.satirlar:
        assert 'GURULTU_ESIKLE_KIYASLANABILIR' in s['sebep']
        assert s['durum'] == st.DURUM_BEYANLI
    # sıra SEBEP_KODLARI sırası, tekrar yok
    assert t2.satirlar[0]['sebep'] == ['BOND_BEYAN',
                                       'GURULTU_ESIKLE_KIYASLANABILIR']
    assert t2.sozluk()['kunye'][-1] == 'gürültü beyanı'
    for k in st.SATIR_MODEL:
        assert [s[k] for s in t2.satirlar] == [s[k] for s in t.satirlar]
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.satirlara_sebep_ekle(t, ['EKSENEL_SIMETRIK_DEGIL'])
    assert e.value.kod == 'DEGER_GECERSIZ'
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.satirlara_sebep_ekle(t, ['YOK_BOYLE'])
    assert e.value.kod == 'SEBEP_BILINMEYEN'
    with pytest.raises(st.SloshTabloHatasi) as e:
        st.satirlara_sebep_ekle(t, 'GURULTU_ESIKLE_KIYASLANABILIR')
    assert e.value.kod == 'TUR_HATASI'
