"""3.0.7 ONARIM2-ÇALK-GEO — yüklenen tank geometrisi bulguları (dalga 2).

M7-CALK-8 (temiz kapsül STEP/STL reddi), M7-CALK-17 (ölçülen profilde
kapalı biçimin silindiri bulamaması), M7-CALK-9 (ölçek uyarısı + kart
nedeni), M7-CALK-10 (sığmayan sıvıda doluluk), M7-CALK-11 (motor perde
sönümü satırı), M7-CALK-12 (yakınsama beyanı + simetri reddi metni),
M7-CALK-5 ikinci adım (σ bağlama). Kanıt:
``docs/scofield/raw/OH/V307/onarim2-calk-geo/RAPOR.md``.
"""

import contextlib
import io
import json
import math
import os
import pathlib
import re
import sys

import numpy as np
import pytest

from hrma.analysis import slosh_analysis as sa
from hrma.analysis import slosh_fem_axisym as se
from hrma.analysis import slosh_motor_baglanti as smb
from hrma.analysis import slosh_tablo as st
from hrma.engines.injector_design import SIGMA_LIQUID_REF
from hrma.importers import tank_geometry_import as tg

sys.path.insert(0, os.path.dirname(__file__))
import tank_geometri_ornekleyici as orn  # noqa: E402

KOK = pathlib.Path(__file__).resolve().parents[1]
FIK = KOK / 'tests' / 'fixtures' / 'tank_geometry'
JS = KOK / 'hrma' / 'static' / 'js'
UST = (0.0, 0.0, 1.0)
R_K, L_K = 0.22, 1.2           # mühendisin kapsülü (M7-CALK-8/17)
SIVI = {'ad': 'RP1', 'rho_kg_m3': 815.0}


def donel_ag(profil, n_boylam):
    """(r, z) profilinden dönel üçgen ağı: her profil düğümü bir halka,
    uçlar tek düğüm; komşu halkalar arası tek bant (silindir boydan boya
    tek bant = CAD'in ince üçgenleri). Dışa yönelimli, kapalı."""
    p = np.asarray(profil, dtype=float)
    nokta = [[0.0, 0.0, p[0, 1]]]
    for r, z in p[1:-1]:
        for j in range(n_boylam):
            f = 2.0 * math.pi * j / n_boylam
            nokta.append([r * math.cos(f), r * math.sin(f), z])
    nokta.append([0.0, 0.0, p[-1, 1]])
    P = np.array(nokta)
    n_h = p.shape[0] - 2

    def v(i, j):
        return 1 + (i - 1) * n_boylam + (j % n_boylam)
    T = [(0, v(1, j + 1), v(1, j)) for j in range(n_boylam)]
    for i in range(1, n_h):
        for j in range(n_boylam):
            a, b, c, d = v(i, j), v(i, j + 1), v(i + 1, j), v(i + 1, j + 1)
            T += [(a, b, d), (a, d, c)]
    son = P.shape[0] - 1
    T += [(son, v(n_h, j), v(n_h, j + 1)) for j in range(n_boylam)]
    return P, np.array(T, dtype=np.int64)


def kapsul_agi(n_bas=24, n_boylam=126):
    return donel_ag(orn.kubbeli_silindir(R_K, L_K, n=n_bas), n_boylam)


V_KAPSUL = math.pi * R_K ** 2 * L_K + 4.0 / 3.0 * math.pi * R_K ** 3


# ===========================================================================
# M7-CALK-8 — temiz kapsül ağı / STEP
# ===========================================================================
class TestKapsulAgi:

    def test_ince_ucgenli_kapsul_agi_kabul(self):
        P, T = kapsul_agi()
        out = tg.nokta_bulutu_isle(P, ucgenler=T, ust_yon=UST)
        assert out['durum'] == 'GECERLI', out.get('mesaj_en')
        assert out['geometri']['R_ref_m'] == pytest.approx(R_K, rel=2e-3)
        assert out['geometri']['H_ic_m'] == pytest.approx(L_K + 2 * R_K,
                                                          rel=1e-3)

    def test_bolme_kapatilirsa_eski_ret_geri_gelir(self, monkeypatch):
        """Ters mutasyon kanıtı (test içinde): bölme kapatılınca aynı ağ
        bugünkü iki-yüzey reddine düşer; yani kabul bölmenin sonucudur."""
        monkeypatch.setattr(tg, 'TANK_AG_ORNEK_ARALIK_KATI', math.inf)
        P, T = kapsul_agi()
        out = tg.nokta_bulutu_isle(P, ucgenler=T, ust_yon=UST)
        assert out['durum'] == 'RET'
        assert out['sebep'] == ['PROFIL_TEK_DEGERLI_DEGIL']
        assert out['ayrinti'] == 'iki_yuzey'

    def test_kutup_dejenere_ucgeni_ayiklanir_sayisi_kunyede(self):
        P, T = kapsul_agi()
        # CAD STL'sinin kutup üçgeni: iki köşesi aynı düğüm
        T2 = np.vstack([T, [[0, 0, int(T[0, 1])]]])
        out = tg.nokta_bulutu_isle(P, ucgenler=T2, ust_yon=UST)
        assert out['durum'] == 'GECERLI', out.get('mesaj_en')
        assert out['kunye']['dejenere_ucgen_ayiklandi'] == 1
        assert out['kunye']['ucgen_sayisi'] == T2.shape[0]
        temiz = tg.nokta_bulutu_isle(P, ucgenler=T, ust_yon=UST)
        assert temiz['kunye']['dejenere_ucgen_ayiklandi'] == 0
        assert out['profil_rz_m'] == temiz['profil_rz_m']

    def test_delik_acan_sifir_alanli_ucgen_yine_ret(self):
        """Üç ayrı köşeli düz üçgen bir deliği kapatıyorsa ayıklanınca ağ
        açılır: adıyla RET (fail-closed; sessiz onarım yok). Sekizyüzlünün
        bir yüzü, kenarının tam orta noktasıyla bölünür; aradaki düz üçgenin
        alanı kayan noktada tam sıfırdır."""
        X, Y, Z = np.eye(3)
        P = [X, Y, Z, -X, -Y, -Z]
        T = []
        for sx in (0, 3):
            for sy in (1, 4):
                for sz in (2, 5):
                    isaret = ((1 if sx == 0 else -1) * (1 if sy == 1 else -1)
                              * (1 if sz == 2 else -1))
                    T.append((sx, sy, sz) if isaret > 0 else (sx, sz, sy))
        a, b, c = T[0]                                   # (X, Y, Z)
        m = len(P)
        P = np.array(P + [0.5 * (P[a] + P[c])])
        T2 = np.array(T[1:] + [(a, b, m), (m, b, c), (c, a, m)])
        temiz = tg.ag_kapalilik(np.array(P[:-1]), np.array(T))
        assert temiz > 0.0                               # sağlam ağ
        out = tg.nokta_bulutu_isle(P, ucgenler=T2, ust_yon=UST)
        assert out['durum'] == 'RET'
        assert out['sebep'] == ['YUZEY_KAPALI_DEGIL']
        assert out['ayrinti'] == 'acik_kenar'
        assert out['mesaj_parametreleri']['adet'] == 3
        assert out['kunye']['dejenere_ucgen_ayiklandi'] == 1

    def test_tek_degerli_olmayan_ag_yine_ret(self):
        s = np.linspace(0, 1, 60)
        ust = np.stack([0.5 * (1 - s), 2.0 - 0.3 * (1 - (1 - s) ** 2)], 1)
        perde = np.vstack([[[0, 0], [0.5, 0], [0.5, 2.0]], ust[1:]])
        perde[-1, 0] = 0
        P, T = donel_ag(perde, 96)
        out = tg.nokta_bulutu_isle(P, ucgenler=T, ust_yon=UST)
        assert out['durum'] == 'RET'
        assert out['sebep'] == ['PROFIL_TEK_DEGERLI_DEGIL']

    @pytest.mark.slow
    def test_muhendisin_step_kapsulu_kabul(self):
        pytest.importorskip('build123d')
        out = tg.tank_geometrisi_oku(str(FIK / 'kapsul_r220_l1200_mm.step'),
                                     'mm', ust_yon=UST)
        assert out['durum'] == 'GECERLI', out.get('mesaj_en')
        assert out['geometri']['V_ic_m3'] == pytest.approx(V_KAPSUL,
                                                           rel=1e-3)
        assert out['geometri']['R_ref_m'] == pytest.approx(R_K, rel=1e-4)
        assert out['kunye']['dejenere_ucgen_ayiklandi'] == 2
        assert out['kunye']['step_mozaik']['aci_rad'] == tg.TANK_STEP_ACI_RAD


# ===========================================================================
# M7-CALK-17 — ölçülen profilde kapalı biçim
# ===========================================================================
class TestKapaliBicimOlculenProfil:

    @pytest.fixture(scope='class')
    def bulut_profili(self):
        P = orn.ornekle(orn.kubbeli_silindir(R_K, L_K), 60000, tohum=7)
        out = tg.nokta_bulutu_isle(P, ust_yon=UST)
        assert out['durum'] == 'GECERLI'
        p = np.asarray(out['profil_rz_m'])
        assert int(np.sum(p[:, 0] == p[:, 0].max())) == 1  # ölçülen profil
        return out['profil_rz_m']

    def test_silindir_bulunur_satirlar_beyanli(self, bulut_profili):
        s = sa.esdeger_model_tablosu(
            'yakit', {'tur': 'profil', 'profil_rz_m': bulut_profili}, SIVI,
            yontem='kapali_bicim')
        sat = {r['doluluk']: r for r in s['tablo'].sozluk()['satirlar']}
        # el hesabı: baş hacmi oranı 0,098 → 0,10–0,90 yüzey silindirde
        for d in (0.15, 0.3, 0.5, 0.7, 0.85):
            assert sat[d]['durum'] == st.DURUM_BEYANLI, d
            assert sat[d]['sebep'] == ['TANK_BASLARI_MODELLENMEDI']
            h_es = sat[d]['V_sivi_m3'] / (math.pi * max(
                r for r, _ in bulut_profili) ** 2)
            m = sa.silindir_esdeger_model(max(r for r, _ in bulut_profili),
                                          h_es)
            assert sat[d]['kappa1_1m'] == m['kappa1_1m']
        for d in (0.005, 0.05, 0.95, 0.995):
            assert sat[d]['durum'] == st.DURUM_RET, d
            assert 'silindir_bolumu_bulunamadi' not in (sat[d].get('ek') or {})

    def test_tolerans_sifirsa_eski_hata_geri_gelir(self, bulut_profili,
                                                   monkeypatch):
        monkeypatch.setattr(sa, 'TANK_SILINDIR_YARICAP_BAGIL_TOL', 0.0)
        s = sa.esdeger_model_tablosu(
            'yakit', {'tur': 'profil', 'profil_rz_m': bulut_profili}, SIVI,
            yontem='kapali_bicim')
        assert s['satir_durumlari']['RET'] == 29

    def test_silindirsiz_profilde_gercek_neden_tani_alaninda(self):
        s = sa.esdeger_model_tablosu(
            'yakit', {'tur': 'profil', 'profil_rz_m': orn.kure(0.3).tolist()},
            SIVI, yontem='kapali_bicim')
        assert s['satir_durumlari']['RET'] == 29
        for r in s['tablo'].sozluk()['satirlar']:
            assert r['ek']['silindir_bolumu_bulunamadi'] is True
            assert r['ek']['silindir_yaricap_bagil_tol'] == (
                sa.TANK_SILINDIR_YARICAP_BAGIL_TOL)

    def test_tam_esit_profil_bit_ayni_kural(self):
        """Analitik profil (iki düğüm tam R'de) tam eşitlik kuralıyla:
        toleranslı kuşak başa uzanmaz."""
        p = orn.kubbeli_silindir(0.5, 1.0)
        assert sa._silindir_bolumu(p) == pytest.approx((0.5, 1.5), abs=1e-15)

    def test_panel_gercek_nedeni_soyler(self):
        js = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')
        assert "ek.silindir_bolumu_bulunamadi === true" in js
        assert "'panel.calkanti.silindirBolumuYok'" in js


# ===========================================================================
# M7-CALK-9 / 10 / 11 / 5σ — motor bağlantısı (K4) ve sonuç bölümü
# ===========================================================================
def _coz(mt):
    from hrma.analysis import flight_vehicle as fv
    from tests.test_example_projects import NAMES
    doc = json.loads((KOK / 'examples' / (NAMES[mt] + '.hrma'))
                     .read_text(encoding='utf-8'))
    with contextlib.redirect_stdout(io.StringIO()):
        durum, govde = fv.run_page_calculation(
            mt, fv.page_payload(mt, doc['inputs']['fields']))
    assert durum == 200, govde
    return govde


@pytest.fixture(scope='module')
def sivi():
    return _coz('liquid')


def _silindir_geo(R, H):
    return {'tur': sa.TANK_TURU_PROFIL,
            'profil_rz_m': [[0.0, 0.0], [R, 0.0], [R, H], [0.0, H]]}


def _rapor(sivi, geo=None, tank='yakit'):
    out = smb.slosh_tanklari('liquid', sivi, tank_geometrileri=(
        {tank: geo} if geo is not None else None))
    return {t['tank_id']: t for t in out['tanklar']}[tank]


@pytest.mark.slow
class TestMotorBaglantisi:

    def test_sigmayan_sivida_doluluk_yok_oran_ayri(self, sivi):
        r = _rapor(sivi, _silindir_geo(0.05, 0.1))
        assert 'TANK_HACMI_YETERSIZ' in r['sebep']
        assert r['yuklu_doluluk'] is None
        assert r['f1_hz_1g']['tablo'] is None
        assert r['f1_hz_1g']['tablo_sebep'] == ['TANK_HACMI_YETERSIZ']
        V = math.pi * 0.05 ** 2 * 0.1
        assert r['geometri']['sivi_hacmi_ic_hacim_orani'] == pytest.approx(
            r['yuklenen_sivi_kg'] / (r['rho_kg_m3'] * V), rel=1e-12)
        assert r['geometri']['sivi_hacmi_ic_hacim_orani'] > 1.0

    def test_olcek_uyarisi_ve_kart_nedeni(self, sivi):
        m = _rapor(sivi)
        R_m, H_m = m['geometri']['R_ref_m'], m['geometri']['H_ic_m']
        assert m['geometri']['motor_tanki_olcegi'] is None  # yükleme yok
        # mm dosyası "m" seçilmiş: 1000 kat
        r = _rapor(sivi, _silindir_geo(1000 * R_m, 1000 * H_m))
        o = r['geometri']['motor_tanki_olcegi']
        assert o['uyari'] is True
        assert o['R_orani'] == pytest.approx(1000.0, rel=1e-9)
        assert o['V_orani'] == pytest.approx(1e9, rel=1e-9)
        assert o['uyari_kati'] == smb.TANK_GEOMETRISI_OLCEK_UYARI_KATI
        assert r['f1_hz_1g']['tablo'] is None
        assert r['f1_hz_1g']['tablo_sebep'] == ['IZGARA_DISI']
        # aynı mertebede tasarım: uyarı yok
        r2 = _rapor(sivi, _silindir_geo(1.5 * R_m, 0.8 * H_m))
        assert r2['geometri']['motor_tanki_olcegi']['uyari'] is False

    def test_sigma_tek_kaynaktan_lox_rp1(self, sivi):
        out = smb.slosh_tanklari('liquid', sivi)
        t = {x['tank_id']: x for x in out['tanklar']}
        ox = t['oksitleyici']['tablo'].sozluk()['sivi']
        yk = t['yakit']['tablo'].sozluk()['sivi']
        assert t['oksitleyici']['sivi_adi'].upper() == 'LOX'
        assert ox['sigma_N_m'] == SIGMA_LIQUID_REF['lox'][0]
        assert yk['sigma_N_m'] is None          # RP-1: kaynaklı değer yok
        # Bond kapısı: LOX 0,001 m/s²'de RET (Bo < 10), RP-1 beyanlı
        h_ox = sa.geff_frekans_haritasi(t['oksitleyici']['tablo'], [1e-3])
        h_yk = sa.geff_frekans_haritasi(t['yakit']['tablo'], [1e-3])
        assert {k for s in h_ox['sebep'] for c in s for k in c} >= {
            'BOND_DUSUK_RET'}
        assert {k for s in h_yk['sebep'] for c in s for k in c} >= {
            'BOND_HESAPLANAMADI'}

    def test_motor_perde_sonumu_satiri_yuklenen_tankta_notlu(self):
        js = (JS / 'calkanti_panel.js').read_text(encoding='utf-8')
        i = js.index("'panel.calkanti.kMotorBafl'")
        assert "geoDosya ? ' — ' + esc(T('panel.calkanti.kMotorBaflGeoNot'" \
            in js[i:i + 600]


def test_sigma_ad_eslemesi_ve_sayi_kopyalanmadi():
    assert smb.sivi_sigmasi('LOX') == SIGMA_LIQUID_REF['lox'][0]
    assert smb.sivi_sigmasi('n2o') == SIGMA_LIQUID_REF['n2o'][0]
    for ad in ('RP1', 'RP-1', 'ETHANOL', '', None):
        assert smb.sivi_sigmasi(ad) is None
    kaynak = (KOK / 'hrma' / 'analysis' / 'slosh_motor_baglanti.py'
              ).read_text(encoding='utf-8')
    assert '0.013145' not in kaynak and '0.0020577' not in kaynak
    assert 'SIGMA_GENERIC' not in kaynak.replace(
        '(kaynaksız ``SIGMA_GENERIC`` KULLANILMAZ)', '')


# ===========================================================================
# M7-CALK-12 — yakınsama beyanı ve simetri reddi metni
# ===========================================================================
def test_yakinsama_satirina_olcut_yazilir():
    t = sa.silindir_tablosu('yakit', 0.3, 1.0, 815.0, 'RP1')
    v = t.sozluk()
    v['satirlar'][3]['sebep'] = ['AG_YAKINSAMA_ZAYIF']
    v['satirlar'][3]['durum'] = st.DURUM_BEYANLI
    v['satirlar'][3]['ek'] = {'hata_kappa1': 1e-3}
    t2 = sa._yakinsama_olcutunu_ekle(st.SloshTablo.sozlukten(v))
    s2 = t2.sozluk()['satirlar']
    assert s2[3]['ek']['yakinsama_olcutu_bagil'] == se.SE_YAKINSAMA_BAGIL_TOL
    assert s2[3]['ek']['yakinsama_olcutu_mertebe'] == se.SE_MERTEBE_BEYAN_ESIGI
    assert s2[3]['ek']['yakinsama_olcutu_z_orani'] == (
        se.SE_YAKINSAMA_Z_TOL_ORANI)
    assert s2[3]['ek']['yakinsama_sinama_alt_orani'] == (
        se.SE_MERTEBE_SINAMA_ALT_ORANI)
    assert s2[3]['ek']['hata_kappa1'] == 1e-3
    assert 'ek' not in s2[4] or 'yakinsama_olcutu_bagil' not in s2[4]['ek']


def test_simetri_reddi_metninde_kod_adi_yok():
    ph = re.compile(r'\{\w+\}')
    metin = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    satirlar = [s for s in metin.splitlines()
                if "'panel.calkanti.geo.eksenel_simetrik_degil.esik'" in s]
    assert len(satirlar) == 2                        # EN + TR
    for s in satirlar + [tg.YEDEK_METINLER[('EKSENEL_SIMETRIK_DEGIL',
                                            'esik')]]:
        yalin = ph.sub('', s.split(':', 1)[-1])
        assert 'eps_' not in yalin, s
        assert ' R' in yalin                         # tanım: R'ye bölünmüş


def test_yakinsama_ve_yeni_metinler_en_tr():
    metin = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    for k in ('yakinsamaBaslik', 'yakinsamaSatir', 'yakinsamaMonoton',
              'yakinsamaHata', 'yakinsamaMertebe', 'silindirBolumuYok',
              'geoDejenereAyiklandi', 'sivHacimOrani', 'olcekBaslik',
              'olcekUyarisi', 'yukluNedenYok', 'kSigma', 'kSigmaKaynak',
              'kSigmaYok', 'kMotorBaflGeoNot'):
        assert metin.count(f"'panel.calkanti.{k}':") == 2, k
