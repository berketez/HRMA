"""_fig_json kapısı bekçi testi (v2.5.5).

Kök neden (2026-07-19 "Regression Rate & Port Growth boş" bugı): plotly 6.x,
``fig.to_json()`` çıktısında numpy dizilerini base64 'bdata' blokları olarak
yazar; uygulamanın paketlediği vendor plotly.js 1.58.5 bu biçimi çözemez ve
grafik BOŞ çizilir. Çözüm tek kapı: her figür JSON'u
``hrma.visualization.visualization._fig_json`` üzerinden üretilir (bdata
blokları listeye açılır, numpy skalerleri Python tiplerine iner, NaN/Inf
null olur).

Bu test, hrma/ altında ÇIPLAK ``fig.to_json()`` çağrısı kalmadığını
AST ile doğrular (yorum ve docstring içindeki bahisler sayılmaz).

Bilinçli istisna: hrma/export/cad_visualization.py — bu dosya v2.5.5
dalgasının dokunulmayanlar listesindedir. İstisnanın BÜYÜMESİ yakalanır:
çağrı sayısı mevcut tavanı aşarsa test düşer.

MUAFİYETİN GEREKÇESİ ÖLÇÜLDÜ (ÖH FAZ D / D5, defter **P13B2-09**)
-----------------------------------------------------------------
Bu docstring eskiden şunu iddia ediyordu: *"bdata koruması orada farklı bir
yolla sağlanır: tüm diziler trace'e eklenirken ``.tolist()`` ile düz listeye
çevrilir"*. Ölçüldüğünde iddia **tutmadı**: 5 çağrı yerinin yalnız 1'inde
``.tolist()`` var ve muaf dosyanın "geçerli mesh yok" yedek yolu **6 base64
``bdata`` bloğu** üretiyor — yani kapının var olma sebebi olan hata, muaf
dosyanın içinde CANLI.

Ders: muafiyet **SAYIYI** tavanlıyordu, gerekçe **MEKANİZMA** iddia
ediyordu, kimse **SONUCU** ölçmüyordu. Bu yüzden tavana ek olarak bir ÇIKTI
denetimi konuldu: muaf dosyadaki her çıplak ``to_json`` çağrısının bulunduğu
fonksiyon gerçekten çağrılır ve ürettiği JSON'da ``bdata`` sayılır. Denetim
gerekçeye değil çıktıya bakar.

ÖH D26 · **P13B2-09** — ADRES DÜZELTMESİ (ölçüldü, ``once_p13b209.json``).
Borç iminin gösterdiği onarım adresi (``cad_visualization.py:945-947``)
bayattı: o satırlar cidar kalınlığı bloğudur. Kusur yardımcı bazında
ayrıştırıldı — 6 ``bdata`` bloğunun **tamamı**
``_add_fallback_3d_motor``ten geliyor (mesh bulunamayınca çağrılır);
``_add_cross_section_view`` 0, ``_add_performance_chart`` 0,
``_create_fallback_visualization`` 0. Onarım ÜRÜN işidir ve
``hrma/export/`` **ihracat kulvarının** sahasındadır; D26'da bu kulvar
yalnız ölçtü ve adresi düzeltti.

ÖH D27 · **P13B2-09 ONARILDI — borç imi KALDIRILDI** (ihracat kulvarı a1).
``_add_fallback_3d_motor`` içindeki iki ``go.Surface`` izi, meshgrid'den
gelen numpy dizilerini plotly'ye doğrudan veriyordu; artık ``.tolist()``
ile düz listeye iniyor (mesh yolunda 2378-2383'te zaten böyleydi, yedek yol
atlanmıştı). ÖLÇÜLDÜ (``once_p13b209.json`` -> ``sonra_p13b209.json``):
``_create_plotly_visualization`` bdata **6 -> 0**, ``_add_fallback_3d_motor``
bdata **6 -> 0** (iz sayısı 2, değişmedi; JSON 23.458 -> 30.308 bayt, çünkü
base64 blok yerine artık okunabilir sayılar var). Bu yüzden
``BUGUN_BDATA_URETEN`` boşaldı: ``xfail(strict=True)`` borç imi kalktı ve
:func:`test_muaf_ciktida_bdata_yok` artık dört sondanın DÖRDÜNDE de gerçek
yeşildir. İm geri konulmamalı; kusur dönerse test doğrudan kırmızı verir.
"""

import ast
import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HRMA_DIR = REPO_ROOT / 'hrma'

#: Çıplak to_json çağrısına izin verilen dosyalar -> izinli azami çağrı
#: sayısı. Yeni dosya eklemek YASAK; buradaki sayı ancak AZALABİLİR.
#: ÖH D27 (ihracat a1): tavan 5 idi, dosyadaki GERÇEK çağrı sayısı ise
#: 4 (ölçüldü: once/sonra_p13b209.json ``ciplak_to_json_sayisi``). Muafiyetin
#: bir çağrılık boş payı vardı — yeni çıplak çağrı sessizce sığabilirdi.
#: Tavan ölçülen değere indirildi; muafiyet artık pay taşımıyor.
ALLOWED_BARE_TO_JSON = {
    'hrma/export/cad_visualization.py': 4,
}

#: Çıktı denetimine bugün TAKILAN fonksiyonlar: ad -> (ölçülen bdata, defter).
#: Bunlar borç imidir, muafiyet değil: `xfail(strict=True)` olduğu için ürün
#: onarıldığı gün XPASS'e döner ve imin kaldırılmasını zorlar.
#:
#: ÖH D27 · P13B2-09 ONARILDI -> sözlük BOŞ. Tek girdi
#: ``'_create_plotly_visualization': (6, 'P13B2-09')`` idi; ürün onarıldı
#: (``_add_fallback_3d_motor`` dizileri ``.tolist()``e indi), ölçüm 6 -> 0.
#: Sözlüğün boş kalması bir eksiklik değil HEDEFTİR: her sonda gerçek yeşil.
BUGUN_BDATA_URETEN = {}

#: Sondaların kullandığı asgari motor ölçüleri (metre). Uydurma sonuç değil,
#: yalnız çizicinin çalışması için gereken geometri girdisi.
SONDA_MOTORU = {
    'chamber_diameter': 0.1,
    'chamber_length': 0.5,
    'throat_diameter': 0.04,
    'exit_diameter': 0.12,
    'nozzle_length': 0.2,
    'motor_name': 'fig_json_gate_sonda',
}


def _bare_to_json_lines(path: pathlib.Path):
    """Dosyadaki gerçek ``<nesne>.to_json(...)`` çağrılarının satırları.

    AST üzerinden bakıldığı için yorumlar, docstring'ler ve
    ``export_to_json`` gibi farklı adlı metotlar eşleşmez.
    """
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'to_json'):
            lines.append(node.lineno)
    return lines


def _scan():
    violations = {}
    allowed_hits = {}
    for path in sorted(HRMA_DIR.rglob('*.py')):
        rel = path.relative_to(REPO_ROOT).as_posix()
        lines = _bare_to_json_lines(path)
        if not lines:
            continue
        if rel in ALLOWED_BARE_TO_JSON:
            allowed_hits[rel] = lines
        else:
            violations[rel] = lines
    return violations, allowed_hits


def _muaf_fonksiyonlar():
    """Muaf dosyalardaki çıplak ``to_json`` çağrılarını SARAN fonksiyon adları.

    Elle liste değil: AST'ten türetilir. Muaf dosyaya yeni bir çağrı
    girdiğinde denetlenmesi gereken fonksiyon kümesi kendiliğinden büyür ve
    sondası olmayan fonksiyon :func:`test_her_muaf_cagri_yeri_sondalaniyor`
    ile KIRMIZI verir (fail-closed).
    """
    out = {}
    for rel in sorted(ALLOWED_BARE_TO_JSON):
        path = REPO_ROOT / rel
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        ebeveyn = {}
        for node in ast.walk(tree):
            for cocuk in ast.iter_child_nodes(node):
                ebeveyn[cocuk] = node
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'to_json'):
                continue
            saran = node
            while saran is not None and not isinstance(
                    saran, (ast.FunctionDef, ast.AsyncFunctionDef)):
                saran = ebeveyn.get(saran)
            ad = saran.name if saran is not None else '<modül düzeyi>'
            out.setdefault(ad, []).append(node.lineno)
    return out


def _sondalar():
    """Fonksiyon adı -> o fonksiyonu GERÇEKTEN çalıştıran çağrı."""
    from hrma.export.cad_visualization import (
        DetailedCADGenerator,
        MotorCADDesigner,
    )

    tasarimci = MotorCADDesigner()
    uretici = DetailedCADGenerator()
    return {
        # Mesh listesi boş -> ürün "geçerli mesh yok" yedeğine düşer; kusurun
        # canlı olduğu yol tam olarak budur (P13B2-09).
        '_create_plotly_visualization':
            lambda: tasarimci._create_plotly_visualization([], SONDA_MOTORU),
        '_create_fallback_visualization':
            lambda: tasarimci._create_fallback_visualization(SONDA_MOTORU),
        'generate_liquid_motor_cad':
            lambda: uretici.generate_liquid_motor_cad(SONDA_MOTORU),
        'generate_solid_motor_cad':
            lambda: uretici.generate_solid_motor_cad(SONDA_MOTORU),
    }


def _bdata_sayisi(cikti):
    metin = cikti if isinstance(cikti, str) else json.dumps(cikti, default=str)
    return metin.count('"bdata"'), len(metin)


def _sonda_param(ad):
    if ad not in BUGUN_BDATA_URETEN:
        return pytest.param(ad, id=ad)
    olculen, defter = BUGUN_BDATA_URETEN[ad]
    return pytest.param(ad, id=ad, marks=pytest.mark.xfail(strict=True, reason=(
        'ÖH defter %s — muafiyetin gerekçesi (".tolist() ile düz listeye '
        "çevriliyor\") 5 çağrı yerinin yalnız 1'inde tutuyor; %s bugün %d "
        'base64 bdata bloğu üretiyor (vendor plotly.js 1.58.5 bu biçimi '
        'çözemez -> 3B görünüm sessizce BOŞ kalır). Onarım ÜRÜN işidir '
        '(ihracat kulvarı). ÖH D26 ADRES DÜZELTMESİ: kusurun adresi '
        'cad_visualization.py:945-947 DEĞİL (o satırlar cidar kalınlığı '
        'bloğudur, grafikle ilgisi yok) — 6 bdata bloğunun TAMAMI '
        '`_add_fallback_3d_motor`ten geliyor (mesh yokken :2271\'de '
        'çağrılır). ÖLÇÜLDÜ (once_p13b209.json): _add_fallback_3d_motor '
        '6, _add_cross_section_view 0, _add_performance_chart 0, '
        '_create_fallback_visualization 0. Onarım: o yardımcının Mesh3d/ '
        'Surface dizileri _fig_json kapısından geçmeli ya da .tolist() '
        'ile düz listeye çevrilmeli; xfail onarım dalgasında kalkar.'
        % (defter, ad, olculen))))


def test_ciplak_fig_to_json_kalmadi():
    """hrma/ altında istisna listesi dışında fig.to_json() çağrısı yok."""
    violations, _allowed = _scan()
    assert not violations, (
        'Çıplak fig.to_json() çağrısı bulundu — _fig_json kapısından '
        'geçirilmeli (bdata / vendor plotly.js 1.58.5 uyumsuzluğu, boş '
        'grafik bugunun kökü): %r' % violations)


def test_istisna_listesi_buyumedi():
    """İzinli dosyadaki çağrı sayısı tavanı aşamaz (istisna şişmesin)."""
    _violations, allowed = _scan()
    for rel, lines in allowed.items():
        cap = ALLOWED_BARE_TO_JSON[rel]
        assert len(lines) <= cap, (
            '%s içindeki to_json çağrısı %d oldu (tavan %d) — yeni çağrı '
            'ekleme, _fig_json kullan. Satırlar: %r'
            % (rel, len(lines), cap, lines))


# ---------------------------------------------------------------------------
# ÇIKTI DENETİMİ — muafiyet gerekçeye değil SONUCA bakar (ÖH FAZ D / D5)
# ---------------------------------------------------------------------------
def test_her_muaf_cagri_yeri_sondalaniyor():
    """AST'ten türetilen her muaf fonksiyonun bir sondası olmalı.

    Fail-closed: muaf dosyaya sondasız yeni bir ``to_json`` çağrısı girerse
    çıktısı hiç denetlenmeden geçemez. Ters yön de denetlenir — artık var
    olmayan bir fonksiyonun sondası kalmışsa denetim boşa koşuyordur.
    """
    muaf = _muaf_fonksiyonlar()
    assert muaf, ('Muaf dosyada hiç çıplak to_json bulunamadı — muafiyet '
                  'gereksizse ALLOWED_BARE_TO_JSON temizlenmeli.')
    sonda = _sondalar()
    sondasiz = sorted(set(muaf) - set(sonda))
    assert not sondasiz, (
        'Muaf dosyada sondası olmayan to_json çağrısı: %s (satırlar: %s) — '
        'çıktısı denetlenmeyen çağrı muafiyete giremez.'
        % (sondasiz, {ad: muaf[ad] for ad in sondasiz}))
    olu = sorted(set(sonda) - set(muaf))
    assert not olu, (
        'Artık çıplak to_json çağırmayan fonksiyonun sondası duruyor: %s — '
        'denetim boşa koşuyor, sonda kaldırılmalı.' % olu)


@pytest.mark.parametrize('fonksiyon',
                         [_sonda_param(ad) for ad in sorted(_muaf_fonksiyonlar())])
def test_muaf_ciktida_bdata_yok(fonksiyon):
    """Muaf fonksiyonun ÜRETTİĞİ JSON'da base64 bdata bloğu olmamalı.

    Tavan denetimi çağrı SAYISINI, bu denetim ÇIKTIYI sınar. İkisi farklı
    sorulardır: tavan 5/5 dolu ve yeşilken, çağrıların birinin çıktısında
    6 bdata bloğu canlıydı (P13B2-09).
    """
    cikti = _sondalar()[fonksiyon]()
    sayi, uzunluk = _bdata_sayisi(cikti)
    assert sayi == 0, (
        '%s çıktısında %d base64 "bdata" bloğu var (JSON %d bayt). Vendor '
        'plotly.js 1.58.5 bu biçimi çözemez: grafik BOŞ çizilir ve kullanıcı '
        'uyarı almaz. Çözüm: çıktı hrma.visualization.visualization._fig_json '
        'kapısından geçmeli.' % (fonksiyon, sayi, uzunluk))


def test_bdata_sayaci_kor_degil():
    """Negatif kontrol: sayaç gerçek bir bdata bloğunu görüyor mu?

    Sayaç kör olsaydı yukarıdaki denetim her koşulda yeşil olurdu — yani
    "bdata yok" hükmü ölçüm değil temenni olurdu.
    """
    import numpy as np
    import plotly.graph_objects as go
    from hrma.visualization.visualization import _fig_json

    fig = go.Figure(data=[go.Scatter(x=np.arange(64, dtype='f8'),
                                     y=np.arange(64, dtype='f8'))])
    ham, _uz = _bdata_sayisi(fig.to_json())
    assert ham > 0, ('plotly çıplak to_json artık bdata üretmiyor — bu '
                     'denetimin dayandığı ölçüm eskimiş, kapının gerekçesi '
                     'gözden geçirilmeli.')
    gecen, _uz = _bdata_sayisi(_fig_json(fig))
    assert gecen == 0, '_fig_json kapısı bdata bloğunu açmıyor'


def test_fig_json_kapisi_yerinde():
    """Kapının kendisi silinmediğinden emin ol (import + davranış)."""
    import numpy as np
    import plotly.graph_objects as go
    from hrma.visualization.visualization import _fig_json
    import json

    fig = go.Figure(data=[go.Scatter(x=np.array([0.0, 1.0]),
                                     y=np.array([1.0, np.nan]))])
    out = _fig_json(fig)
    assert isinstance(out, str)
    assert 'bdata' not in out
    parsed = json.loads(out)
    # NaN, plotly.js'in boşluk olarak yorumladığı null'a iner
    assert parsed['data'][0]['y'][1] is None
