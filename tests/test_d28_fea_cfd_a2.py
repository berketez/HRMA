# -*- coding: utf-8 -*-
"""OH Dalga-28, kulvar fea-cfd, asama 2/2 — bekci dosyasi.

Kalemler:

* **P8B4-24** (dusuk, YENI) — karsilastirma figurunun 4. paneli
  "Mass Efficiency" basligini tasiyordu ama bir verim degil, boyutlu bir
  sacilim ciziyordu (x = Total Mass (kg), y = Isp (s)). Iz adi
  ("Mass vs Isp") dogruyu soyleyen tek metindi. Onarim: panel kimligi tek
  kaynaga (``COMPARATIVE_PANELS``) indi, sacilim basligi eksenlerden
  turetilir ve fail-closed bir kapi yalan basligi reddeder.
* **P15B4-12** (dusuk, YENI) — ENGELLI (kardes dal cakismasi: ihracat
  kulvari ayni dosyaya dokundu). Kusur olculdu, borc imiyle duruyor.

Olcum betikleri: docs/scofield/raw/OH/D28/fea-cfd/a2/olcum_*.py
"""
import ast
import json
import os
import re

import pytest

from hrma.visualization import visualization as V


KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FULL_CONFIGS = {
    'Motor A': {'thrust': 1000.0, 'isp': 220.0,
                'total_impulse': 5000.0, 'total_mass': 12.0},
    'Motor B': {'thrust': 1500.0, 'isp': 235.0,
                'total_impulse': 8000.0, 'total_mass': 18.0},
    'Motor C': {'thrust': 2400.0, 'isp': 248.0,
                'total_impulse': 15000.0, 'total_mass': 27.5},
}

# plotly subplot duzeni: (1,1)->x/y, (1,2)->x2/y2, (2,1)->x3/y3, (2,2)->x4/y4
EKSEN_CIFTLERI = (('xaxis', 'yaxis'), ('xaxis2', 'yaxis2'),
                  ('xaxis3', 'yaxis3'), ('xaxis4', 'yaxis4'))


def _eksen_basligi(layout, ad):
    ax = layout.get(ad) or {}
    baslik = ax.get('title')
    if isinstance(baslik, dict):
        return baslik.get('text') or ''
    return baslik or ''


def _figur(configs=None):
    fig = json.loads(V.create_comparative_analysis_plot(
        FULL_CONFIGS if configs is None else configs))
    layout = fig.get('layout') or {}
    basliklar = [a.get('text', '') for a in (layout.get('annotations') or [])]
    paneller = []
    for i, (xa, ya) in enumerate(EKSEN_CIFTLERI):
        paneller.append({
            'baslik': basliklar[i] if i < len(basliklar) else '',
            'x': _eksen_basligi(layout, xa),
            'y': _eksen_basligi(layout, ya),
        })
    return fig, paneller


# ---------------------------------------------------------------------------
# P8B4-24 — ad <-> davranis
# ---------------------------------------------------------------------------
class TestP8B424PanelAdiDavranisiAnlatir:
    """Bir panel basligi, panelin cizdigi buyuklugu anlatmak ZORUNDA."""

    def test_hicbir_baslik_boyutlu_buyuklugu_verim_diye_adlandirmaz(self):
        """OLCULEN KUSUR: taban agacinda yalan_baslik_sayisi = 1.

        4. panel "Mass Efficiency" diyordu; eksenleri kg ve s. Verim
        boyutsuzdur — boyutlu bir sacilimi verim diye adlandirmak
        kullanicinin gormedigi bir normalizasyon vaat eder.
        """
        _, paneller = _figur()
        yalanlar = []
        for p in paneller:
            bl = p['baslik'].lower()
            iddia = [s for s in V.PANEL_ORAN_IDDIA_SOZCUKLERI if s in bl]
            if not iddia:
                continue
            if (V._panel_ekseni_boyutlu_mu(p['y'])
                    or V._panel_ekseni_boyutlu_mu(p['x'])):
                yalanlar.append((p['baslik'], iddia, p['x'], p['y']))
        assert yalanlar == [], (
            'Bu paneller bir oran/verim vaat ediyor ama boyutlu buyukluk '
            'ciziyor: %r' % (yalanlar,))

    def test_sacilim_basligi_eksenlerinden_turetilir(self):
        """Baslik, eksen etiketlerinin bir FONKSIYONU olmali."""
        _, paneller = _figur()
        p = paneller[3]
        assert p['x'] == 'Total Mass (kg)'
        assert p['y'] == 'Isp (s)'
        assert p['baslik'] == V._sacilim_basligi(p['x'], p['y'])
        assert p['baslik'] == 'Isp vs Total Mass'

    def test_sacilim_basligi_kaynakta_metin_sabiti_DEGIL(self):
        """Tek kaynak: turetilen baslik kodda hicbir yerde YAZILI olmamali.

        Yazili olsaydi eksenlerden bagimsiz olarak degistirilebilirdi —
        P8B4-24'un tam olarak dogdugu yer budur.
        """
        yol = os.path.join(KOK, 'hrma/visualization/visualization.py')
        agac = ast.parse(open(yol, encoding='utf-8').read())
        docstring_id = set()
        for d in ast.walk(agac):
            govde = getattr(d, 'body', None)
            if (isinstance(d, (ast.Module, ast.FunctionDef,
                               ast.AsyncFunctionDef, ast.ClassDef))
                    and govde and isinstance(govde[0], ast.Expr)
                    and isinstance(govde[0].value, ast.Constant)
                    and isinstance(govde[0].value.value, str)):
                docstring_id.add(id(govde[0].value))
        kod_metinleri = [n.value for n in ast.walk(agac)
                         if isinstance(n, ast.Constant)
                         and isinstance(n.value, str)
                         and id(n) not in docstring_id]
        assert 'Isp vs Total Mass' not in kod_metinleri
        # Taban agacindaki yalan baslik da geri gelmemeli.
        assert 'Mass Efficiency' not in kod_metinleri

    def test_eksen_etiketleri_ve_iz_adlari_TABLODAN_gelir(self):
        """Figurun her metni COMPARATIVE_PANELS ile birebir ayni olmali."""
        fig, paneller = _figur()
        for panel, cizilen in zip(V.COMPARATIVE_PANELS, paneller):
            assert cizilen['x'] == panel['x_label']
            assert cizilen['y'] == panel['y_label']
            assert cizilen['baslik'] == V.comparative_panel_title(panel)
        iz_adlari = [t.get('name') for t in fig['data']]
        assert iz_adlari == [p['trace_name'] for p in V.COMPARATIVE_PANELS]


class TestP8B424KapiFailClosed:
    """Kapi bir IDDIA degil, calisan bir REDDETME olmali."""

    YALAN_PANEL = {
        'metrics': ('total_mass', 'isp'), 'row': 2, 'col': 2,
        'kind': 'scatter', 'title': 'Mass Efficiency',
        'x_label': 'Total Mass (kg)', 'y_label': 'Isp (s)',
        'trace_name': 'Mass vs Isp', 'color': '#c792ea', 'text_format': None,
    }

    def test_yalan_baslik_REDDEDILIR(self):
        with pytest.raises(ValueError) as exc:
            V._dogrula_comparative_panels([self.YALAN_PANEL])
        ileti = str(exc.value)
        assert 'Mass Efficiency' in ileti      # alan adi iletide
        assert 'efficiency' in ileti           # hangi sozcuk tetikledi
        assert 'dimensionless' in ileti        # neden

    # --- ÖH D28 fix-28a (9 Eylül 2026) --------------------------------
    # Aşağıdaki üç test "yükselmemeli" diyordu ama gövdesinde HİÇ iddia
    # yoktu; dördü birden kırmızı veriyordu (test_d22 iki tavan, test_d24
    # hizalama, test_d25 kurulum kredisi). Kırmızılar haklıydı: kapı
    # sessizce hiçbir paneli denetlemese de — boş liste, kırık döngü —
    # üçü de yeşil kalırdı. Çözüm tavanı yükseltmek DEĞİL: kapı artık
    # DENETLEDİĞİ panel sayısını döndürüyor ve testler o sayıyı sınıyor.
    # Ters mutasyon: döngü gövdesindeki sayaç sökülürse üçü de kırmızı.

    def test_gercek_oran_paneli_KABUL_EDILIR(self):
        """Kapı aşırı sıkı olmamalı: boyutsuz bir verim çizilebilir."""
        durust = dict(self.YALAN_PANEL,
                      title='Nozzle Efficiency',
                      x_label='Configuration',
                      y_label='Nozzle Efficiency (-)')
        # Yükselmemeli VE paneli gerçekten denetlemiş olmalı.
        assert V._dogrula_comparative_panels([durust]) == 1

    def test_iddiasiz_baslik_boyutlu_eksende_KABUL_EDILIR(self):
        durust = dict(self.YALAN_PANEL, title='Thrust Comparison',
                      x_label='Configuration', y_label='Thrust (N)')
        assert V._dogrula_comparative_panels([durust]) == 1

    def test_modul_tablosu_kapidan_gecer(self):
        # Tablonun TAMAMI denetimden geçmeli; bir panel atlanırsa sayı
        # tabloyla eşleşmez.
        assert (V._dogrula_comparative_panels()
                == len(V.COMPARATIVE_PANELS) > 0)


class TestP8B424DavranisKorundu:
    """Onarim yalnizca ad<->davranis kusurunu kaldirmali; cizim aynen kalmali."""

    def test_tam_sema_dort_iz_cizer(self):
        fig, _ = _figur()
        assert len(fig['data']) == 4

    def test_eksik_anahtar_KeyError_vermez(self):
        configs = {n: {k: v for k, v in c.items() if k != 'total_impulse'}
                   for n, c in FULL_CONFIGS.items()}
        fig, _ = _figur(configs)
        assert len(fig['data']) == 3

    def test_sacilim_iki_metrigi_birden_ister(self):
        """total_mass'i olmayan config sacilimda cizilmez (eski davranis)."""
        configs = {'A': dict(FULL_CONFIGS['Motor A']),
                   'B': {k: v for k, v in FULL_CONFIGS['Motor B'].items()
                         if k != 'total_mass'}}
        fig, _ = _figur(configs)
        sacilim = [t for t in fig['data'] if t.get('name') == 'Mass vs Isp']
        assert len(sacilim) == 1
        assert list(sacilim[0]['text']) == ['A']

    def test_cubuk_metin_bicimleri_korundu(self):
        fig, _ = _figur()
        adla = {t['name']: t for t in fig['data']}
        assert list(adla['Thrust']['text'])[0] == '1000 N'
        assert list(adla['Specific Impulse']['text'])[0] == '220.0 s'
        assert list(adla['Total Impulse']['text'])[0].endswith('N⋅s')

    def test_sacilim_izinde_uydurma_sayi_yok(self):
        fig, _ = _figur()
        sacilim = [t for t in fig['data'] if t.get('name') == 'Mass vs Isp'][0]
        assert list(sacilim['x']) == [12.0, 18.0, 27.5]
        assert list(sacilim['y']) == [220.0, 235.0, 248.0]


# ---------------------------------------------------------------------------
# P15B4-12 — BORC IMI (ENGELLI: kardes dal cakismasi)
# ---------------------------------------------------------------------------
CAD_YOLU = os.path.join(KOK, 'hrma/export/cad_visualization.py')
METIN_SONEKLERI = ('_source', '_note', '_basis', '_scope', '_material',
                   '_reason', '_status', '_units')


def _mass_breakdown_alanlari():
    agac = ast.parse(open(CAD_YOLU, encoding='utf-8').read())
    hedef = None
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Dict):
            continue
        for anahtar, deger in zip(dugum.keys, dugum.values):
            if (isinstance(anahtar, ast.Constant)
                    and anahtar.value == 'mass_breakdown'
                    and isinstance(deger, ast.Dict)):
                hedef = deger
    assert hedef is not None, 'mass_breakdown sozluk sabiti bulunamadi'
    return [k.value for k in hedef.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)]


def _kutle_olmayan_sayisal_alanlar():
    disi = []
    for ad in _mass_breakdown_alanlari():
        if ad.endswith(METIN_SONEKLERI):
            continue
        if ad.endswith('_mass') or ad.startswith('mass_') or '_mass_' in ad:
            if ad.endswith('_kg_m3'):
                disi.append(ad)      # ..._mass_density_kg_m3 -> yogunluk
            continue
        disi.append(ad)
    return disi


class TestP15B412YerlesimKapandi:
    """`mass_breakdown` artik YALNIZ kutle tasir — borc imi KALKTI.

    D28 OLCUMU (bu dal ve taban ayni): 18 alanin 9'u sayisal, 4'u kutle
    (kg), **5'i degil** — 3 uzunluk (mm) + 2 yogunluk (kg/m3). Kalem
    basligi "mm cinsinden IKI kalinlik alani" diyordu; olculen UC idi.
    Onarim D28'de ENGELLI kaldi (hrma/export/cad_visualization.py ihracat
    kulvarinin sahasi, kardes-dal kurali) ve strict xfail borc imiyle
    kaydedildi.

    D29 IHRACAT a1 (OH-D28-07): kusur giderildi. Alanlar SILINMEDI,
    kunyeleriyle birlikte kendi boyut sozluklerine tasindi —
    ``performance_summary.geometry_summary`` (mm) ve yeni
    ``performance_summary.material_summary`` (kg/m3 + malzeme adi);
    ``mass_breakdown`` yon tarifini ``mass_inputs_note`` ile yazar.
    OLCUM: 5 -> 0 kutle-olmayan sayisal alan
    (docs/scofield/raw/OH/D29/ihracat/a1/{once,sonra}_p15b412.json);
    kosum olcumu 33 tasima, 0 kayip, 0 deger degisimi
    (a1/{once,sonra}_yerlesim.json). Borc imi KALDIRILDI — im kalsaydi
    asagidaki test XPASS(strict) ile suiti kirardi.
    """

    def test_mass_breakdown_yalniz_kutle_tasir(self):
        """Eski borc imi, imsiz. Kusur geri gelirse KIRMIZI."""
        assert _kutle_olmayan_sayisal_alanlar() == []

    def test_mm_alani_KALMADI(self):
        mm = [a for a in _kutle_olmayan_sayisal_alanlar()
              if a.endswith('_mm')]
        assert mm == [], mm      # D28'de UC taneydi

    def test_tasinan_alanlar_YENI_ADRESINDE_duruyor(self):
        """Onarim silme degil TASIMA: on bir alan yeni sozlugunde.

        Kaybetmek de "mass_breakdown yalniz kutle tasir" testini
        yesillendirirdi; bu bekci bu kaciyi kapatir.
        """
        agac = ast.parse(open(CAD_YOLU, encoding='utf-8').read())
        bulunan = {}
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Dict):
                continue
            for anahtar, deger in zip(dugum.keys, dugum.values):
                if (isinstance(anahtar, ast.Constant)
                        and anahtar.value in ('geometry_summary',
                                              'material_summary')
                        and isinstance(deger, ast.Dict)):
                    bulunan[anahtar.value] = {
                        k.value for k in deger.keys
                        if isinstance(k, ast.Constant)
                        and isinstance(k.value, str)}
        assert bulunan.get('geometry_summary', set()) >= {
            'wall_thickness_mm', 'wall_thickness_source',
            'wall_thickness_recommended_mm', 'wall_thickness_note',
            'nozzle_wall_thickness_mm', 'nozzle_wall_thickness_source',
        }, bulunan.get('geometry_summary')
        assert bulunan.get('material_summary', set()) >= {
            'chamber_material', 'chamber_mass_density_kg_m3',
            'chamber_mass_density_source', 'nozzle_mass_density_kg_m3',
            'nozzle_mass_density_source',
        }, bulunan.get('material_summary')
