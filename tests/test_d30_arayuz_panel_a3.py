# -*- coding: utf-8 -*-
"""OH D30 · arayuz-panel · asama 3/3 — bekci.

Her sinif bir onarim kalemini tutar. Olculer ILISKI olcusudur (sayi mandali
degil): "su alan su bolgede su yoldan basilmali", "su sinif CSS'te tanimli
olmali", "su kapi su yedekten ONCE kosmali". Saf JS islevleri (brCell,
ispLossTitle, twoPhaseDiagnosticHTML, parametrikAciklamaKapisi,
projeHataNedeni) Node ile GERCEKTEN kosturulur: bekci metnin degil
DAVRANISIN bekcisidir.
"""
import json
import os
import re
import subprocess

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def oku(*parca):
    with open(os.path.join(KOK, *parca), encoding='utf-8') as f:
        return f.read()


def node_kos(kaynak):
    node = subprocess.run(['node'], input=kaynak, capture_output=True,
                          text=True, timeout=60)
    assert node.returncode == 0, node.stderr
    return json.loads(node.stdout.strip())


def islev_govdesi(metin, ad):
    """Suslu parantez derinligiyle <ad> islevinin govdesini cikar."""
    m = re.search(r'function\s+' + re.escape(ad) + r'\s*\([^)]*\)\s*\{', metin)
    assert m, 'islev bulunamadi: ' + ad
    i = m.end() - 1
    derinlik = 0
    for j in range(i, len(metin)):
        if metin[j] == '{':
            derinlik += 1
        elif metin[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return metin[m.start():j + 1]
    raise AssertionError('govde kapanmadi: ' + ad)


@pytest.fixture(scope='module')
def liquid():
    return oku('hrma', 'templates', 'liquid.html')


@pytest.fixture(scope='module')
def solid():
    return oku('hrma', 'templates', 'solid.html')


@pytest.fixture(scope='module')
def advanced():
    return oku('hrma', 'templates', 'advanced.html')


@pytest.fixture(scope='module')
def formulas():
    return oku('hrma', 'templates', 'formulas.html')


@pytest.fixture(scope='module')
def launch_site():
    return oku('hrma', 'templates', 'launch_site.html')


# ===================================================================== B1-15
class TestP12bB1_15OluDataNesnesi:
    """calculateLiquid() yedi alanlik `data` nesnesini kurup kullanmiyordu."""

    def test_olu_nesne_kalmadi(self, liquid):
        govde = islev_govdesi(liquid, 'calculateLiquid')
        assert not re.search(r'const data = \{', govde), (
            'calculateLiquid icinde yeniden bir `data` nesnesi kuruluyor')

    def test_yuk_hala_toplayicidan_geliyor(self, liquid):
        govde = islev_govdesi(liquid, 'calculateLiquid')
        assert 'collectAllParameters()' in govde
        assert 'collectClosureAndFeedLineParams()' in govde


# ===================================================================== B1-16
class TestP12bB1_16OlmayanMotorAdiAlani:
    """Sayfada bulunmayan bir alandan motor adi okunuyordu."""

    def test_alan_sayfada_yok(self, liquid):
        assert not re.search(r'id=["\']motor_name["\']', liquid), (
            'alan eklendiyse bu bekci gozden gecirilmeli')

    def test_olmayan_alandan_okuma_yok(self, liquid):
        assert not re.search(
            r'getElementById\(\s*["\']motor_name["\']\s*\)', liquid)
        assert not re.search(
            r'querySelector\(\s*["\']#motor_name["\']\s*\)', liquid)

    def test_pdf_kunyesi_tek_cozucuden(self, liquid):
        m = re.search(r'_liquidPdfMotorData\(cr,\s*\n?\s*([^,]+),', liquid)
        assert m, 'PDF motor verisi cagrisi bulunamadi'
        assert '_liquidMotorName()' in m.group(1), (
            'motor adi tek cozucuden gelmiyor: ' + m.group(1))

    def test_ikinci_ad_artik_erisilemez(self, liquid):
        # `_liquidPdfMotorData` icindeki `motorName || 'HRMA-LIQUID'`
        # yedegi OK-21 geregi sokulmedi; erisilemez oldugu OLCULUR: her
        # cagri tek cozucuyu geciriyorsa yedek dal hic kosmaz.
        cagrilar = re.findall(r'_liquidPdfMotorData\(([^;]*?)\);', liquid,
                              re.S)
        assert cagrilar, 'cagri bulunamadi'
        for c in cagrilar:
            ilk_arg = c.split(',')[1]
            assert '_liquidMotorName()' in ilk_arg, (
                'motor adi tek cozucuden gecmiyor: ' + ilk_arg)
        # Tire-li ad yalnizca o erisilemez yedekte (ve gerekce yorumunda) kalir
        kod = [satir for satir in liquid.splitlines()
               if "'HRMA-LIQUID'" in satir
               and not satir.strip().startswith('//')]
        assert len(kod) == 1, 'tire-li ad kodda birden fazla yerde: %s' % kod


# ===================================================================== B2-20
class TestP12bB2_20KayipDokumu:
    """isp_loss_breakdown dort sayisal kayip yayimliyor, ekranda ikisi vardi."""

    ALANLAR = ['combustion_losses', 'nozzle_losses', 'two_phase_losses',
               'divergence_losses']

    @pytest.mark.parametrize('alan', ALANLAR)
    def test_dort_kayip_da_basiliyor(self, solid, alan):
        assert re.search(r"fmtField\(ispSplit, '%s'" % alan, solid), (
            '%s kayip dokumunde basilmiyor' % alan)

    def test_uygulama_durumu_hucrenin_kunyesinde(self, solid):
        assert re.search(r"title=\"\$\{ispLossTitle\(ispSplit, 'two_phase'\)\}\"",
                         solid)
        assert re.search(r"title=\"\$\{ispLossTitle\(ispSplit, 'divergence'\)\}\"",
                         solid)

    def test_ispLossTitle_uygulanmadigini_soyluyor(self, solid):
        govde = islev_govdesi(solid, 'ispLossTitle')
        kaynak = govde + """
        const cikti = {
            iki_faz: ispLossTitle({
                two_phase_losses: 4.081,
                two_phase_losses_applied: false,
                two_phase_losses_basis: 'eta_2phase = 1 - 0.30 * X_p'
            }, 'two_phase'),
            sapma: ispLossTitle({
                divergence_losses: 1.7,
                divergence_efficiency_applied: 0.983,
                divergence_losses_basis: 'half angle 15 deg'
            }, 'divergence'),
            bos: ispLossTitle({}, 'two_phase')
        };
        console.log(JSON.stringify(cikti));
        """
        r = node_kos(kaynak)
        assert 'two_phase_losses_applied=false' in r['iki_faz'], r['iki_faz']
        assert 'eta_2phase' in r['iki_faz']
        assert 'divergence_losses_applied=true' in r['sapma'], r['sapma']
        assert r['bos'] == '', 'veri yokken kunye UYDURULUYOR: ' + r['bos']

    def test_teshis_blogu_ekrana_iniyor(self, solid):
        # Tanim DEGIL, CAGRI aranir: islev tanimli ama hic cagrilmiyorsa
        # blok yine ekrana inmez (kusurun ta kendisi).
        assert '${twoPhaseDiagnosticHTML(results)}' in solid, (
            'teshis blogu uretilen HTML icinde cagrilmiyor')
        govde = islev_govdesi(solid, 'twoPhaseDiagnosticHTML')
        assert '(results || {}).two_phase_loss' in govde

    def test_teshis_blogu_cozucunun_alan_adlariyla(self, solid):
        kaynak = (islev_govdesi(solid, 'tpKacis')
                  + islev_govdesi(solid, 'tpSatir')
                  + islev_govdesi(solid, 'twoPhaseDiagnosticHTML')
                  + """
        const T = (k, f) => f;
        const html = twoPhaseDiagnosticHTML({ two_phase_loss: {
            status: 'evaluated',
            applied_to_isp: false,
            isp_loss_percent: 2.1837,
            overlap_declaration: 'not applied on top of nozzle efficiency',
            inputs_used: { condensed_mass_fraction: 0.33,
                           chamber_pressure_bar: 68.9 }
        }});
        const bos = twoPhaseDiagnosticHTML({});
        console.log(JSON.stringify({ html: html, bos: bos }));
        """)
        r = node_kos(kaynak)
        for ad in ('two_phase_loss.status', 'two_phase_loss.applied_to_isp',
                   'two_phase_loss.isp_loss_percent',
                   'condensed_mass_fraction'):
            assert ad in r['html'], 'alan adi basilmiyor: ' + ad
        # Ad + DEGER ayni satirda (D28 ad+deger olcutu)
        assert '2.1837' in r['html']
        assert 'false' in r['html']
        assert r['bos'] == '', 'blok yokken bos olmayan HTML uretiliyor'


# ===================================================================== B2-21
class TestP12bB2_21GrainSayfasiYasaBeyani:
    """Rejim yasali yakitlarda a/n hucreleri sessizce bos kaliyordu."""

    def test_ham_num_cagrisi_kalmadi(self, solid):
        m = re.search(r"const grain = \[(.*?)\n            \];", solid, re.S)
        assert m
        assert not re.search(
            r'num\(r\.burn_rate_(?:coefficient|exponent),', m.group(1)), (
            'a/n hala korumasiz num() ile basiliyor')

    def test_yasa_satirlari_var(self, solid):
        m = re.search(r"const grain = \[(.*?)\n            \];", solid, re.S)
        blok = m.group(1)
        for ad in ('burn_rate_basis', 'brLawName(r)',
                   'burn_rate_coefficient_input', 'burn_rate_exponent_input'):
            assert ad in blok, 'Grain sayfasinda yok: ' + ad
        # Gercekten kullanilan yasa adi cozucunun kaydindan okunuyor
        govde = re.search(r'const brLawName = function \(kayit\) \{(.*?)\};',
                          solid, re.S)
        assert govde and 'kayit.burn_rate_law' in govde.group(1)

    def test_brCell_bos_hucre_birakmiyor(self, solid):
        m = re.search(r'const brCell = function \(kayit, anahtar, basamak\) \{'
                      r'(.*?)\n            \};', solid, re.S)
        assert m
        kaynak = ('const brCell = function (kayit, anahtar, basamak) {'
                  + m.group(1) + '};' + """
        const rejim = brCell({
            burn_rate_coefficient: null,
            burn_rate_basis: 'piecewise regime table "kndx"'
        }, 'burn_rate_coefficient', 7);
        const tekUslu = brCell({ burn_rate_coefficient: 0.0022552 },
                               'burn_rate_coefficient', 7);
        const hicbiri = brCell({}, 'burn_rate_coefficient', 7);
        console.log(JSON.stringify({ rejim, tekUslu, hicbiri }));
        """)
        r = node_kos(kaynak)
        assert r['rejim'] and 'Burn rate basis' in str(r['rejim']), (
            'rejim yasasinda hucre hala sessizce bos: %r' % (r['rejim'],))
        assert r['tekUslu'] == 0.0022552, r['tekUslu']
        assert r['hicbiri'] == '', r['hicbiri']

    def test_sayi_uydurulmuyor(self, solid):
        # Rejim dalinda SAYI degil, gerekce doner.
        m = re.search(r'const brCell = function .*?\n            \};',
                      solid, re.S)
        assert 'Number(v.toFixed(basamak))' in m.group(0)
        assert re.search(r"return\s+\(typeof kayit\.burn_rate_basis", m.group(0))


# ===================================================================== B2-23
class TestP12bB2_23DurustBicimlendirici:
    """Specifications sekmesi dokuz alani korumasiz .toFixed() ile basiyordu."""

    ALANLAR = ['c_star', 'chamber_pressure', 'core_diameter', 'exit_diameter',
               'expansion_ratio', 'expansion_ratio_vacuum', 'grain_length',
               'propellant_mass', 'throat_diameter']

    def spec_blok(self, solid):
        bas = solid.index('<!-- Specifications Tab -->')
        son = solid.index('<!-- Performance Analysis Tab -->')
        return solid[bas:son]

    def test_korumasiz_toFixed_kalmadi(self, solid):
        blok = self.spec_blok(solid)
        kalan = re.findall(r'results\.(\w+)\.toFixed\(', blok)
        assert not kalan, 'korumasiz .toFixed() kalanlar: %s' % kalan

    @pytest.mark.parametrize('alan', ALANLAR)
    def test_her_alan_fmtField_ile(self, solid, alan):
        blok = self.spec_blok(solid)
        assert re.search(r"fmtField\(results, '%s'" % alan, blok), (
            '%s durust bicimlendiriciden gecmiyor' % alan)

    def test_metin_alanlari_da_korumali(self, solid):
        blok = self.spec_blok(solid)
        assert "fmtTextField(results, 'propellant_name')" in blok
        assert "fmtTextField(results, 'grain_type')" in blok
        assert '${results.propellant_name}' not in blok
        assert '${results.grain_type.toUpperCase()}' not in blok

    def test_birim_fmtField_icinde(self, solid):
        blok = self.spec_blok(solid)
        # Birim artik hucrede ayri metin degil, bicimlendiricinin isi.
        assert "fmtField(results, 'grain_length', 1, 'mm')" in blok
        assert "fmtField(results, 'c_star', 0, 'm/s')" in blok
        assert "fmtField(results, 'chamber_pressure', 1, 'bar')" in blok


# ===================================================================== B2-24
class TestP12bB2_24YedekKatalogSapmasi:
    """Yedek APCP kaydi merkezi katalogdan bes alanda sapiyordu."""

    def apcp_yedek(self, solid):
        m = re.search(r"var FALLBACK_PROPELLANTS = \[(.*?)\n        \];",
                      solid, re.S)
        assert m
        ma = re.search(r"key: 'apcp'(.*?)\n            \},", m.group(1), re.S)
        assert ma
        return ma.group(1)

    @pytest.mark.parametrize('alan', ['density', 'c_star', 'gamma',
                                      'flame_temperature', 'molecular_weight'])
    def test_merkezle_celisen_sayi_yazilmiyor(self, solid, alan):
        from hrma.data.propellants_db import PROPELLANTS
        blok = self.apcp_yedek(solid)
        m = re.search(r'\b%s:\s*([-\d.eE+]+|null)' % alan, blok)
        assert m, 'yedek kayitta alan yok: ' + alan
        if m.group(1) == 'null':
            return
        yedek = float(m.group(1))
        merkez = PROPELLANTS['apcp'][alan]
        assert abs(yedek - merkez) <= 1e-9, (
            '%s yedekte %r, merkezi katalogda %r — TEK KAYNAK ihlali'
            % (alan, yedek, merkez))

    def test_kaynak_kunyesi_duruyor(self, solid):
        blok = self.apcp_yedek(solid)
        assert 'built_in_fallback_catalogue_endpoint_unavailable' in blok

    def test_ucu_de_ayni_yolda(self, solid):
        # kndx/knsb zaten sayisizdi; apcp de ayni hukme baglandi.
        m = re.search(r"var FALLBACK_PROPELLANTS = \[(.*?)\n        \];",
                      solid, re.S)
        assert len(re.findall(r'burn_rate_a: null', m.group(1))) == 3


# ===================================================================== B3-04
class TestP12bB3_04RozetRenkleri:
    """Iki basarisizlik yolu tanimsiz CSS sinifi kullaniyordu."""

    def test_kullanilan_her_sinif_tanimli(self, advanced):
        css = advanced + oku('hrma', 'static', 'css', 'theme.css')
        siniflar = sorted(set(re.findall(
            r"set(?:Nist|Cea)Status\([^;]*?'(status-[a-z-]+)'\s*\)", advanced)))
        assert siniflar, 'rozet ayarlayici cagrisi bulunamadi'
        eksik = [c for c in siniflar
                 if not re.search(r'\.%s\b\s*(?:,|\{)' % c, css)]
        assert not eksik, 'tanimsiz rozet sinifi: %s' % eksik

    @pytest.mark.parametrize('sinif', ['status-offline', 'status-error'])
    def test_iki_tema_da_kapsiyor(self, advanced, sinif):
        assert re.search(r'\.%s\s*\{' % sinif, advanced), (
            'acik tema karsiligi yok: ' + sinif)
        assert re.search(r'\.%s\s*\{' % sinif,
                         oku('hrma', 'static', 'css', 'theme.css')), (
            'koyu tema karsiligi yok: ' + sinif)

    def test_renk_siddeti_metni_izliyor(self, advanced):
        # baglanti hatasi kirmizi ailededir (disconnected ile ayni)
        kirmizi = re.search(r'\.status-error \{ background: (#\w+);', advanced)
        kesik = re.search(r'\.status-disconnected \{ background: (#\w+);',
                          advanced)
        assert kirmizi and kesik and kirmizi.group(1) == kesik.group(1)


# ===================================================================== B3-07
class TestP12bB3_07OluApiAkisi:
    """D24/P9B5-31 sokmustu; onarim dosyada DURUYOR mu?"""

    def test_kosulsuz_return_yok(self, advanced):
        # Kusur KOSULSUZ bir `return;` idi: islevin ust duzeyinde (12 bosluk
        # girinti) duruyor ve altindaki 58 satiri erisilemez kiliyordu.
        # `custom` / `mixture` dallarindaki iki mesru `return;` daha derin
        # girintidedir; olcu SATIR SAYISI degil GIRINTI ILISKISIDIR.
        govde = islev_govdesi(advanced, 'updateFuelConfig')
        kosulsuz = re.findall(r'\n {12}return;', govde)
        assert not kosulsuz, (
            'islevin ust duzeyinde kosulsuz return geri gelmis (%d)'
            % len(kosulsuz))

    def test_kosullu_donusler_duruyor(self, advanced):
        """P17B4-01'in kazandigi DAVRANIS: custom/mixture erken doner.

        CEVRILDI (OH D33-KOLAY · OH-D32-11). ESKI olcut 16 bosluk
        girintili `return;` satirlarini SAYIYORDU (== 2). Taban surumde
        iki ayri dal vardi: `custom` dali `#custom_fuel_config` panelini
        gosterip donuyor, `mixture` dali `#custom_fuel_mixture` panelini
        gosterip `updateMixtureDensity()` cagirip donuyordu. Iki panel de
        OH-D31-05'te sayfadan kaldirildi; gosterme satirlari olu kaldigi
        icin D33'te silindi ve iki dal TEK kosula birlesti. Sayi mandali
        bu yuzden yanlis alarm verdi (1 != 2) — oysa KORUNAN davranis
        aynen duruyor.

        YENI olcut davranistir: `custom` ve `mixture` secildiginde
        paylasilan alanlar (`fuel_density`, `regression_a/n`) YAZILMAZ;
        gercek bir yakit secildiginde YAZILIR (asiri duzeltme kapisi).
        """
        govde = islev_govdesi(advanced, 'updateFuelConfig')
        kaynak = """
        function kos(tip) {
            var alanlar = {
                fuel_type: { value: tip },
                fuel_density: { value: 'DOKUNULMADI' },
                regression_a: { value: 'DOKUNULMADI' },
                regression_n: { value: 'DOKUNULMADI' }
            };
            var document = { getElementById: function (id) {
                return alanlar[id] || null; } };
            %s
            updateFuelConfig();
            return { d: alanlar.fuel_density.value,
                     a: alanlar.regression_a.value,
                     n: alanlar.regression_n.value };
        }
        console.log(JSON.stringify({ custom: kos('custom'),
            mixture: kos('mixture'), htpb: kos('htpb') }));
        """ % govde
        out = node_kos(kaynak)
        for tip in ('custom', 'mixture'):
            assert out[tip] == {'d': 'DOKUNULMADI', 'a': 'DOKUNULMADI',
                                'n': 'DOKUNULMADI'}, (
                "%s secildiginde paylasilan alanlar EZILIYOR: erken donus "
                "kayboldu, kullanicinin girdigi degerler uydurma "
                "varsayilanlarla degistiriliyor (%s)" % (tip, out[tip]))
        # Asiri duzeltme kapisi: gercek yakitta alanlar YAZILMALI.
        assert out['htpb']['d'] != 'DOKUNULMADI', (
            'gercek yakit seciminde de erken donuluyor: kol olmus')
        for k in ('d', 'a', 'n'):
            assert isinstance(out['htpb'][k], (int, float)), out['htpb']

    def test_son_satirlar_canli_kod(self, advanced):
        # Kusurun ikinci yarisi: returnden sonra 51 dolu satir olu duruyordu.
        # Bugun islevin son KOD satiri form yazimidir, olu blok degil.
        govde = islev_govdesi(advanced, 'updateFuelConfig')
        kod = [x.strip() for x in govde.splitlines()
               if x.strip() and not x.strip().startswith('//')]
        assert kod[-1] == '}'
        assert 'regressionN.value = defaultProps.n;' in kod

    def test_ucun_cagrisi_bu_islevde_yok(self, advanced):
        govde = islev_govdesi(advanced, 'updateFuelConfig')
        kod = '\n'.join(x for x in govde.splitlines()
                        if not x.strip().startswith('//'))
        assert '/api/get-propellant-properties' not in kod, (
            'olu API akisi KOD olarak geri gelmis'
        )


# ===================================================================== B3-10
class TestP12bB3_10TetikleyicisizBilesen:
    """D23/P17B3-07 sokmustu; onarim dosyada DURUYOR mu?"""

    def test_olu_islev_geri_gelmedi(self, advanced):
        app = oku('hrma', 'static', 'js', 'app.js')
        assert 'function exportOpenRocket' not in advanced
        assert 'function exportOpenRocket' not in app

    def test_durum_satiri_hem_var_hem_yaziliyor(self, advanced):
        assert 'id="packageStatus"' in advanced
        assert "getElementById('packageStatus')" in advanced


# ===================================================================== B3-11
class TestP12bB3_11TaramaAraligiKapisi:
    """Aralik O/F icin ayarliyken parametre degisince sabit kaliyordu."""

    def test_alanlar_sahibini_tasiyor(self, advanced):
        assert re.search(r'id="param_start"[^>]*data-param-type=', advanced)
        assert re.search(r'id="param_end"[^>]*data-param-type=', advanced)

    def test_kapi_yedekten_once_kosuyor(self, advanced):
        govde = advanced[advanced.index('async function runParametricAnalysis'):]
        kapi = govde.find('paramRangeGate()')
        yedek = govde.find('isNaN(sweepMin)')
        assert kapi >= 0, 'kapi cagrisi yok'
        assert yedek >= 0, 'form yedegi sokulmus (OK-21 ihlali)'
        assert kapi < yedek, 'kapi uydurma yedekten SONRA kosuyor'

    def test_kapi_uyusmazlikta_durduruyor(self, advanced):
        govde = islev_govdesi(advanced, 'paramRangeGate')
        kaynak = ("""
        const alan = {
            param_type: { value: 'chamber_pressure' },
            param_start: { dataset: { paramType: 'of_ratio' } },
            param_end: { dataset: { paramType: 'of_ratio' } }
        };
        const document = { getElementById: (id) => alan[id] || null };
        """ + govde + """
        const uyusmaz = paramRangeGate();
        alan.param_start.dataset.paramType = 'chamber_pressure';
        alan.param_end.dataset.paramType = 'chamber_pressure';
        const uyusur = paramRangeGate();
        console.log(JSON.stringify({ uyusmaz, uyusur }));
        """)
        r = node_kos(kaynak)
        assert r['uyusmaz'], 'parametre degisse de kapi aciyor'
        assert 'param_type=chamber_pressure' in r['uyusmaz']
        assert r['uyusur'] is None, 'uyusan aralikta kapi kapaniyor'

    def test_kapi_hata_dalina_dusuyor(self, advanced):
        govde = advanced[advanced.index('async function runParametricAnalysis'):]
        blok = govde[:govde.find('const baseParams')]
        assert "showMessage(" in blok and "'error'" in blok
        assert re.search(r'if \(kapi\) \{', blok)
        assert 'return;' in blok


# ===================================================================== B3-21
class TestP12bB3_21KazanilmamisAciklama:
    """Aciklama listesi figurde OLMAYAN iki ozelligi anlatiyordu."""

    def test_iki_iddia_varsayilan_gizli(self, advanced):
        assert re.search(r'<li id="param_li_optimum" hidden>', advanced)
        assert re.search(r'<li id="param_li_zarf" hidden>', advanced)

    def test_kosulsuz_gorunen_iddia_kalmadi(self, advanced):
        assert not re.search(
            r'<li><strong data-i18n="adv\.txt\.(?:optimalPoints|designEnvelope)"',
            advanced)

    def test_kapi_cizilen_figurden_karar_veriyor(self, advanced):
        assert 'parametrikAciklamaKapisi(plotData);' in advanced
        govde = islev_govdesi(advanced, 'parametrikAciklamaKapisi')
        kaynak = ("""
        const el = {};
        ['param_li_optimum', 'param_li_zarf'].forEach(i => el[i] = { hidden: null });
        const document = { getElementById: (i) => el[i] || null };
        """ + govde + """
        // URUNUN BUGUNKU figuru: her nokta isaretli (lines+markers), zarf yok
        parametrikAciklamaKapisi({ data: [
            { mode: 'lines+markers', x: [1, 2, 3, 4], y: [1, 2, 3, 4] }
        ]});
        const bugun = { optimum: el.param_li_optimum.hidden,
                        zarf: el.param_li_zarf.hidden };
        // Ozellik GERCEKTEN kazanilirsa satir acilir
        parametrikAciklamaKapisi({ data: [
            { mode: 'lines+markers', x: [1, 2, 3, 4], y: [1, 2, 3, 4] },
            { mode: 'markers', x: [3], y: [9] },
            { mode: 'lines', x: [1, 4], y: [0, 0], fill: 'tonexty' }
        ]});
        const kazanilmis = { optimum: el.param_li_optimum.hidden,
                             zarf: el.param_li_zarf.hidden };
        console.log(JSON.stringify({ bugun, kazanilmis }));
        """)
        r = node_kos(kaynak)
        assert r['bugun']['optimum'] is True, (
            'her noktayi isaretleyen iz "optimum noktalar" iddiasini kazandiriyor')
        assert r['bugun']['zarf'] is True, 'zarf yokken iddia gosteriliyor'
        assert r['kazanilmis']['optimum'] is False
        assert r['kazanilmis']['zarf'] is False


# ===================================================================== B3-24
class TestP12bB3_24GuverteGeometriBeyani:
    """Guverte alt basligi kosulsuz "LIVE GEOMETRY FROM SOLVER OUTPUT" diyordu."""

    def test_baslik_hedeflenebilir(self, advanced):
        assert re.search(
            r'<div class="viz-sub" id="viz_sub_geometry" data-i18n=', advanced)

    def test_port_dongusu_beyani_tazeliyor(self, advanced):
        govde = islev_govdesi(advanced, 'vizCyclePort')
        assert 'vizSetGeometryClaim(shape)' in govde

    def test_beyan_sekle_gore_degisiyor(self, advanced):
        govde = islev_govdesi(advanced, 'vizSetGeometryClaim')
        kaynak = ("""
        // Gercek DOM'daki baslangic hali: data-i18n VARDIR.
        const alt = { attrs: { 'data-i18n': 'adv.txt.parametricDigitalTwinLiveGeometry' },
            textContent: 'PARAMETRIC 3D MODEL',
            setAttribute(k, v) { this.attrs[k] = v; },
            removeAttribute(k) { delete this.attrs[k]; } };
        const document = { getElementById: (i) =>
            (i === 'viz_sub_geometry' ? alt : null) };
        const i18nText = (k, f) => f;
        """ + govde + """
        vizSetGeometryClaim('star');
        const oku = () => (alt.attrs['data-i18n'] === undefined
                           ? null : alt.attrs['data-i18n']);
        const yildiz = { metin: alt.textContent, i18n: oku() };
        vizSetGeometryClaim('circular');
        const daire = { metin: alt.textContent, i18n: oku() };
        console.log(JSON.stringify({ yildiz, daire }));
        """)
        r = node_kos(kaynak)
        assert 'LIVE GEOMETRY' not in r['yildiz']['metin'], (
            'yildiz portta hala cozucu beyani veriliyor: '
            + r['yildiz']['metin'])
        assert 'Visual representation only' in r['yildiz']['metin']
        assert r['yildiz']['i18n'] is None, (
            'canli durum yazildi ama data-i18n duruyor — dil degisimi ezer')
        assert 'LIVE GEOMETRY' in r['daire']['metin']
        assert r['daire']['i18n'] == 'adv.txt.parametricDigitalTwinLiveGeometry'

    def test_dugme_ipucu_tek_beyan_degil(self, advanced):
        # Eski hal: tek beyan btn.title icindeydi. Simdi baslik da soyluyor.
        assert 'vizSetGeometryClaim' in advanced


# ===================================================================== B4-07
class TestP12bB4_07OrneklemeBaginti:
    """Sekil fonksiyonlari urunde YOK; sayfada iddia beyandan once geliyordu."""

    def bolum(self, formulas):
        return formulas[formulas.find('fx.s14_1.h'):formulas.find('fx.s14_2.h')]

    def test_beyan_kutulardan_once(self, formulas):
        b = self.bolum(formulas)
        assert b.find('fx.s14_1.desc') < b.find('formula-box'), (
            'orneklem uyarisi hala kutulardan SONRA')

    def test_kutular_vurgusuz(self, formulas):
        b = self.bolum(formulas)
        assert len(re.findall(r'formula-box formula-illustrative', b)) == 3

    def test_vurgusuzluk_sinifi_metin_eklemiyor(self, formulas):
        m = re.search(r'\.formula-illustrative \{(.*?)\}', formulas, re.S)
        assert m, 'sinif tanimi yok'
        assert 'content' not in m.group(1), (
            'CSS content ile cevrilemeyen metin uretiliyor')

    def test_urun_bu_fonksiyonlari_degerlendirmiyor(self):
        vis = oku('hrma', 'visualization', 'visualization.py')
        assert not re.search(r'0\.15\s*\*\s*(?:np\.)?log', vis)
        assert not re.search(r'1\s*-\s*0\.3\s*\*\s*\(', vis)


# ===================================================================== B4-15
class TestP12bB4_15ProjeYuklemeGerekcesi:
    """Silinmis proje 500 doner; sayfa ucun gerekcesini hic basmiyordu."""

    def test_http_durumu_okunuyor(self, launch_site):
        govde = islev_govdesi(launch_site, 'loadProjectVehicle')
        assert 'httpDurum = r.status' in govde

    def test_json_olmayan_govde_zinciri_kirmiyor(self, launch_site):
        govde = islev_govdesi(launch_site, 'loadProjectVehicle')
        assert re.search(r'r\.json\(\)\.catch\(', govde), (
            '500 HTML hata sayfasinda zincir kopuyor')

    def test_gerekce_durum_satirina_yaziliyor(self, launch_site):
        govde = islev_govdesi(launch_site, 'loadProjectVehicle')
        assert govde.count('setStatus(projeHataNedeni(') == 2, (
            'her iki hata dalinda da gerekce yazilmiyor')

    def test_gerekce_ucun_kendi_alanlarindan(self, launch_site):
        govde = islev_govdesi(launch_site, 'projeHataNedeni')
        kaynak = govde + """
        const cikti = {
            besyuz: projeHataNedeni(500, { error: 'project file not found' }, 'eski'),
            govdesiz: projeHataNedeni(500, null, 'eski'),
            agsiz: projeHataNedeni(0, null, 'eski')
        };
        console.log(JSON.stringify(cikti));
        """
        r = node_kos(kaynak)
        assert 'HTTP 500' in r['besyuz'] and 'project file not found' in r['besyuz']
        assert 'project=eski' in r['besyuz']
        assert 'HTTP 500' in r['govdesiz'] and '(no JSON body)' in r['govdesiz']
        assert 'no HTTP response' in r['agsiz']
        assert '/api/flight-vehicle' in r['agsiz']

    def test_ornek_arac_kunyesi_duruyor(self, launch_site):
        govde = islev_govdesi(launch_site, 'loadProjectVehicle')
        assert govde.count("'site.projectLoadFailed'") == 2, (
            'ornek araca dusus kunyesiz kaldi')
