# -*- coding: utf-8 -*-
"""Windows arayüz görünümünün iki kusuru için KAYNAK SEVİYESİ bekçileri.

Neden bu dosya var (ikisi de fotoğrafla doğrulandı, 2026-08-14):

1. **Beyaz menü çubuğu.** Koyu temalı uygulamanın üstünde bembeyaz bir WinForms
   MenuStrip duruyordu. Kaynağı okundu: pywebview'in winforms arka ucu menüyü
   ``WinForms.MenuStrip()`` olarak kurup hiçbir renk/çizici ayarı yapmadan
   forma ekliyor; varsayılan "Professional" çizici de BackColor'ı yok sayıp
   kendi açık gri gradyanını çiziyor. launcher.py'de tek bir stil satırı yoktu.
2. **Python ikonu.** Pencere başlığında ve görev çubuğunda Python logosu vardı.
   Kaynağı okundu: aynı arka uç, kendisine ikon verilmezse simgeyi
   ``sys.executable``dan (pythonw.exe) ExtractIconW ile çıkarıyor. Kısayoldaki
   hrma.ico kısayola aittir, pencereye değil.

**Bu testler Windows'ta çalıştırılamadığımız için var.** Düzeltme macOS'ta kör
yazıldı; hedef makinede hiç koşmadı. Elimizde kalan tek güvence, düzeltmenin
kodda DURDUĞUNU ve macOS yolunu bozmadığını mekanik olarak sınamak:

- Windows'a özgü her adım ``os.name == "nt"`` koruması altında mı?
- .NET'e dokunan her atama kendi ``try`` gövdesinde mi? (çökme yasak)
- ``import clr`` modül düzeyine sızmış mı? (sızarsa launcher macOS'ta import
  anında ölür — yani bu düzeltme macOS'u öldürmüş olur)
- Özel çizici KANITLANMADAN kuruluyor mu? (kurulursa beyaz gradyan geri gelir)
- macOS dalı (``setApplicationIconImage_``) yerinde mi?
- Dürüstlük beyanı duruyor mu? (docstring "Windows'ta DOĞRULANMADI" demeli;
  gerçek doğrulama yapıldığında bu ibare BİLEREK güncellenecek ve test o
  zaman düzeltilecek)

Testlerin hiçbiri Windows gerektirmez; hepsi macOS/Linux'ta koşar.
"""

import ast
import importlib.util
import pathlib
import re
import subprocess
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
LAUNCHER = KOK / 'packaging' / 'launcher.py'
ICO = KOK / 'packaging' / 'hrma.ico'

KAYNAK = LAUNCHER.read_text(encoding='utf-8')
AGAC = ast.parse(KAYNAK)


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _tr_kucult(metin):
    """Türkçe duyarlı küçültme: 'DOĞRULANMADI' -> 'doğrulanmadı'.

    Düz ``.lower()`` 'I' harfini 'i' yapar, 'ı' yapmaz; ibare aramaları bu
    yüzden sessizce ıskalanırdı.
    """
    return metin.replace('I', 'ı').replace('İ', 'i').lower()


def _islev(ad):
    for node in ast.walk(AGAC):
        if isinstance(node, ast.FunctionDef) and node.name == ad:
            return node
    raise AssertionError('launcher.py içinde %s() tanımlı değil' % ad)


def _islev_kaynagi(ad):
    return ast.get_source_segment(KAYNAK, _islev(ad)) or ''


def _cagrilan_adlar(node):
    """Bir düğümün altında çağrılan tüm isimler (fonksiyon + yöntem adları)."""
    adlar = set()
    for alt in ast.walk(node):
        if isinstance(alt, ast.Call):
            hedef = alt.func
            if isinstance(hedef, ast.Name):
                adlar.add(hedef.id)
            elif isinstance(hedef, ast.Attribute):
                adlar.add(hedef.attr)
    return adlar


def _atanan_ozellikler(node):
    """Bir düğümün altında ``x.Ozellik = ...`` biçiminde atanan öznitelikler."""
    adlar = set()
    for alt in ast.walk(node):
        if isinstance(alt, ast.Assign):
            for hedef in alt.targets:
                if isinstance(hedef, ast.Attribute):
                    adlar.add(hedef.attr)
    return adlar


def _nt_dali(islev_adi):
    """İşlev içindeki ``if os.name == "nt":`` düğümünü döndürür."""
    for node in ast.walk(_islev(islev_adi)):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        karsilastirma = node.test
        sol = karsilastirma.left
        if (isinstance(sol, ast.Attribute) and sol.attr == 'name'
                and isinstance(sol.value, ast.Name) and sol.value.id == 'os'
                and isinstance(karsilastirma.ops[0], ast.Eq)
                and getattr(karsilastirma.comparators[0], 'value', None) == 'nt'):
            return node
    return None


def _nt_erken_cikis_var(islev_adi):
    """``if os.name != "nt": return`` koruması var mı?"""
    for node in ast.walk(_islev(islev_adi)):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        karsilastirma = node.test
        sol = karsilastirma.left
        if (isinstance(sol, ast.Attribute) and sol.attr == 'name'
                and isinstance(sol.value, ast.Name) and sol.value.id == 'os'
                and isinstance(karsilastirma.ops[0], ast.NotEq)
                and getattr(karsilastirma.comparators[0], 'value', None) == 'nt'
                and any(isinstance(st, ast.Return) for st in node.body)):
            return True
    return False


def _try_korumali_dugumler(islev):
    """İşlev içinde bir ``try`` GÖVDESİNDE yer alan tüm düğümler."""
    korunan = set()
    for node in ast.walk(islev):
        if isinstance(node, ast.Try):
            for st in node.body:
                for alt in ast.walk(st):
                    korunan.add(alt)
    return korunan


@pytest.fixture(scope='module')
def launcher_modulu():
    """launcher.py'yi macOS'ta gerçekten import eder (modül düzeyi yan etkisiz)."""
    spec = importlib.util.spec_from_file_location('hrma_launcher_bekci', LAUNCHER)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


# ---------------------------------------------------------------------------
# 0. Kaynak sağlığı
# ---------------------------------------------------------------------------

def test_launcher_derleniyor():
    sonuc = subprocess.run(
        [sys.executable, '-m', 'py_compile', str(LAUNCHER)],
        capture_output=True, text=True)
    assert sonuc.returncode == 0, (
        'packaging/launcher.py derlenmiyor:\n%s' % sonuc.stderr)


def test_hrma_ico_var():
    """Simge düzeltmesinin KAYNAĞI: dosya yoksa kod doğru olsa da işe yaramaz."""
    assert ICO.is_file(), 'packaging/hrma.ico yok — pencere simgesi verilemez'
    veri = ICO.read_bytes()
    assert len(veri) > 1000, 'hrma.ico şüpheli derecede küçük (%d bayt)' % len(veri)
    assert veri[:4] == b'\x00\x00\x01\x00', 'hrma.ico geçerli bir ICO başlığı taşımıyor'


# ---------------------------------------------------------------------------
# 1. macOS'u öldürmeme güvencesi (kör yazılan kodun EN BÜYÜK riski)
# ---------------------------------------------------------------------------

def test_dotnet_importlari_modul_duzeyinde_degil():
    """``import clr`` / ``import System...`` modül düzeyine SIZMAMALI.

    Sızarsa launcher macOS'ta ve pythonnet'siz her ortamda import anında
    çöker; yani Windows kozmetiği uğruna çalışan platform kaybedilir.
    """
    yasak = {'clr', 'System', 'System.Windows.Forms', 'System.Drawing'}
    for node in AGAC.body:
        if isinstance(node, ast.Import):
            for ad in node.names:
                assert ad.name.split('.')[0] not in yasak, (
                    'modül düzeyinde "import %s" var — macOS import anında çöker'
                    % ad.name)
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split('.')[0] not in yasak, (
                'modül düzeyinde "from %s import ..." var' % node.module)


def test_launcher_macosta_import_edilebilir(launcher_modulu):
    assert hasattr(launcher_modulu, 'main')


def test_windows_islevleri_macosta_sessizce_cikar(launcher_modulu):
    """nt olmayan platformda hiçbiri patlamamalı; hepsi sessizce dönmeli."""
    assert launcher_modulu._windows_app_identity() is None
    assert launcher_modulu._windows_chrome_fix() is None
    assert launcher_modulu._windows_chrome_fix_gecikmeli() is None


def test_macos_yolu_dokunulmamis():
    """macOS kimliği ve simgesi yerinde ve create_window'dan ÖNCE çağrılıyor."""
    macos = _islev_kaynagi('_macos_app_identity')
    # Dizge araması YETMEZ: sembolün adı üstteki açıklama bloğunda da geçiyor,
    # yani çağrı silinse bile dizge kalırdı (mutasyon denemesinde kaçtı).
    cagriliyor = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == 'setApplicationIconImage_'
        for n in ast.walk(_islev('_macos_app_identity')))
    assert cagriliyor, (
        'macOS simge ÇAĞRISI kaybolmuş — Dock/About simgesi Python\'a düşer')
    assert 'icon_runtime.png' in macos and 'icon.icns' in macos

    yerel = _islev('_try_native_window')
    kimlik_satiri = simge_satiri = None
    for node in ast.walk(yerel):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == '_macos_app_identity':
            kimlik_satiri = node.lineno
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == 'create_window':
            simge_satiri = node.lineno
    assert kimlik_satiri is not None, '_macos_app_identity çağrısı kaldırılmış'
    assert simge_satiri is not None
    assert kimlik_satiri < simge_satiri, (
        'macOS kimliği pencere kurulduktan SONRA veriliyor — NSApplication '
        'oluştuktan sonra yamalamak menü çubuğunu düzeltmez')

    assert 'darwin' in _islev_kaynagi('_native_menu')


# ---------------------------------------------------------------------------
# 2. Kusur 2 — görev çubuğu kimliği ve pencere simgesi
# ---------------------------------------------------------------------------

def test_appusermodelid_tek_kaynakta():
    assert KAYNAK.count('UZAYTEK.HRMA') == 1, (
        'AppUserModelID dizgesi birden fazla yerde — tek sabitte durmalı')
    assert re.search(r'^WIN_APP_USER_MODEL_ID\s*=\s*"UZAYTEK\.HRMA"',
                     KAYNAK, re.M), 'kimlik modül düzeyinde sabit değil'
    kimlik = _islev_kaynagi('_windows_app_identity')
    assert 'SetCurrentProcessExplicitAppUserModelID' in kimlik
    assert 'WIN_APP_USER_MODEL_ID' in kimlik, (
        'kimlik çağrısı sabiti değil, elle yazılmış dizgeyi kullanıyor')


def test_app_identity_nt_korumali_ve_try_icinde():
    assert _nt_erken_cikis_var('_windows_app_identity'), (
        '_windows_app_identity() nt koruması olmadan ctypes.windll çağırıyor')
    islev = _islev('_windows_app_identity')
    korunan = _try_korumali_dugumler(islev)
    for node in ast.walk(islev):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == 'SetCurrentProcessExplicitAppUserModelID':
            assert node in korunan, 'shell32 çağrısı try dışında — launcher çöker'


def test_app_identity_pencere_akisinin_en_basinda():
    """Kimlik, HİÇBİR pencere kurulmadan önce verilmeli.

    Kabuk süreç kimliğini ilk pencerede önbelleğe alır; sonradan çağırmak
    görev çubuğu gruplamasını düzeltmez.
    """
    govde = _islev('_show_window_blocking').body
    ilk_ifade = govde[1] if isinstance(govde[0], ast.Expr) and isinstance(
        govde[0].value, ast.Constant) else govde[0]
    assert isinstance(ilk_ifade, ast.Expr) and isinstance(ilk_ifade.value, ast.Call)
    assert getattr(ilk_ifade.value.func, 'id', '') == '_windows_app_identity', (
        '_windows_app_identity() pencere akışının ilk adımı değil')


def test_ikon_yolu_iki_adayi_sirayla_deniyor():
    kaynak = _islev_kaynagi('_windows_icon_path')
    assert 'hrma.ico' in kaynak
    kurulum = kaynak.find('parent.parent / "hrma.ico"')
    gelistirme = kaynak.find('parent / "hrma.ico"', kurulum + 1)
    assert kurulum != -1, (
        'kurulum düzeni adayı (INSTDIR/hrma.ico -> parent.parent) yok')
    assert gelistirme != -1, (
        'geliştirme düzeni adayı (packaging/hrma.ico -> parent) yok')
    assert kurulum < gelistirme, 'adaylar yanlış sırada: kurulum önce gelmeli'
    assert 'is_file()' in kaynak, 'aday var mı diye bakılmıyor'


def test_ikon_yolu_depoda_packaging_hrma_ico_cozuyor(launcher_modulu):
    """Davranış sınaması: bu depoda ikinci aday tutmalı."""
    assert launcher_modulu._windows_icon_path() == str(ICO)


def test_ikon_baslangicta_ve_pencere_sonrasinda_veriliyor():
    """Simge iki yoldan da basılıyor: start(icon=) ve .NET rötuşu."""
    nt = _nt_dali('_try_native_window')
    assert nt is not None, '_try_native_window içinde nt dalı yok'
    nt_kaynak = ast.get_source_segment(KAYNAK, nt) or ''
    assert '"icon"' in nt_kaynak and '_windows_icon_path' in nt_kaynak, (
        'webview.start(icon=...) yolu kaldırılmış — pywebview simgeyi yine '
        'pythonw.exe\'den çıkarır')
    assert '_webview_start_ikonu_destekliyor' in nt_kaynak, (
        'icon parametresi sürüm denetimi olmadan veriliyor — eski pywebview '
        'TypeError verip yerel pencereyi komple düşürür')
    assert '"icon"' not in _islev_kaynagi('_try_native_window').replace(
        nt_kaynak, ''), 'icon parametresi nt dalının DIŞINDA da veriliyor'

    ikon = _islev_kaynagi('_windows_form_ikonu')
    assert 'form.Icon' in ikon and 'ShowIcon' in ikon


# ---------------------------------------------------------------------------
# 3. Kusur 1 — beyaz menü şeridi
# ---------------------------------------------------------------------------

def test_chrome_fix_tanimli_ve_nt_korumali():
    assert _nt_erken_cikis_var('_windows_chrome_fix'), (
        '_windows_chrome_fix() nt koruması olmadan .NET\'e dokunuyor')


def test_chrome_fix_nt_dalinda_pencereye_baglaniyor():
    nt = _nt_dali('_try_native_window')
    nt_kaynak = ast.get_source_segment(KAYNAK, nt) or ''
    assert '_windows_chrome_kancasi' in nt_kaynak, (
        'rötuş hiçbir kancaya bağlanmıyor — kod yazılmış ama hiç çalışmaz')
    assert '_windows_chrome_fix_gecikmeli' in nt_kaynak and 'func' in nt_kaynak, (
        "'shown' kancası kurulamazsa start(func=...) yedeği yok")
    kanca = _islev_kaynagi('_windows_chrome_kancasi')
    assert 'events.shown' in kanca, 'kanca events.shown olayına bağlanmıyor'
    assert '_windows_chrome_fix' in kanca


def test_menu_stil_katmanlari_duruyor():
    """Üç katman da kodda olmalı: düz renk, açılır menüler, çizici."""
    tema = _islev_kaynagi('_windows_menu_temasi')
    ozellikler = _atanan_ozellikler(_islev('_windows_menu_temasi'))
    assert 'BackColor' in ozellikler and 'ForeColor' in ozellikler, (
        'katman 1 (şerit rengi) yok')
    assert 'RenderMode' in ozellikler and 'ToolStripRenderMode.System' in tema, (
        'katman 1 eksik: Professional çizici BackColor\'ı yok sayar, render '
        'kipi Sistem\'e alınmazsa şerit beyaz kalır')
    assert '_windows_menu_ogeleri_boya' in tema, 'katman 2 (ögeler) yok'
    assert 'Renderer' in ozellikler, 'katman 3 (özel çizici) yok'

    # Yine dizge araması YETMEZ: 'DropDown' sözcüğü docstring'de ve
    # 'DropDownItems' içinde de geçiyor, okuma silinse bile kalırdı.
    boya_islev = _islev('_windows_menu_ogeleri_boya')
    dropdown_okunuyor = any(
        isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'getattr'
        and any(getattr(a, 'value', None) == 'DropDown' for a in n.args)
        for n in ast.walk(boya_islev))
    dropdown_okunuyor = dropdown_okunuyor or any(
        isinstance(n, ast.Attribute) and n.attr == 'DropDown'
        for n in ast.walk(boya_islev))
    assert dropdown_okunuyor, (
        'açılır menü nesnesi hiç okunmuyor — şerit koyu, açılan menü beyaz kalır')
    assert any(isinstance(n, ast.Attribute) and n.attr == 'DropDownItems'
               for n in ast.walk(boya_islev)), 'alt ögeler hiç gezilmiyor'
    assert '_windows_menu_ogeleri_boya' in _cagrilan_adlar(boya_islev), (
        'alt menülere özyineleme yok — yalnız üst ögeler boyanır')

    cizici = _islev_kaynagi('_windows_koyu_cizici')
    for anahtar in ('MenuStripGradientBegin', 'MenuStripGradientEnd',
                    'ToolStripDropDownBackground', 'MenuItemSelected',
                    'MenuItemPressedGradientBegin', 'MenuBorder',
                    'MenuItemBorder', 'ImageMarginGradientBegin'):
        assert anahtar in cizici, 'renk tablosunda %s eksik' % anahtar
    assert 'ProfessionalColorTable' in cizici
    assert 'ToolStripProfessionalRenderer' in cizici


def test_cizici_kanitlanmadan_kurulmuyor():
    """Sınanmamış çizici KURULMAMALI.

    Geçersiz kılması tutmamış bir Professional çizici, sistem çizicisinin
    yerine geçip beyaz gradyanı GERİ getirir — yani düzeltmeyi bozar.
    """
    cizici = _islev('_windows_koyu_cizici')
    kaynak = _islev_kaynagi('_windows_koyu_cizici')
    assert 'WIN_MENU_RENK' in kaynak and '!=' in kaynak, (
        'çizici üretilen rengi hiç ölçmüyor')
    olcum_var = False
    for node in ast.walk(cizici):
        if isinstance(node, ast.If) and any(
                isinstance(st, ast.Return) and getattr(st.value, 'value', 1) is None
                for st in node.body):
            olcum_var = True
    assert olcum_var, 'sınama başarısız olduğunda None dönen dal yok'

    tema = _islev('_windows_menu_temasi')
    kapi_satiri = atama_satiri = None
    for node in ast.walk(tema):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) \
                and isinstance(node.test.left, ast.Name) \
                and node.test.left.id == 'cizici' \
                and any(isinstance(st, ast.Return) for st in node.body):
            kapi_satiri = node.lineno
        if isinstance(node, ast.Assign):
            for hedef in node.targets:
                if isinstance(hedef, ast.Attribute) and hedef.attr == 'Renderer' \
                        and getattr(node.value, 'id', '') == 'cizici':
                    atama_satiri = min(atama_satiri or node.lineno, node.lineno)
    assert kapi_satiri is not None, (
        "'cizici is None' kapısı yok — doğrulanmamış çizici kuruluyor")
    assert atama_satiri is not None and kapi_satiri < atama_satiri, (
        'çizici, kapıdan ÖNCE kuruluyor')


def test_renk_paleti_tek_yerde_tanimli():
    """Aynı RGB değeri iki yerde yazılmamalı (parametre tutarlılığı kuralı)."""
    assert re.search(r'^WIN_MENU_RENK\s*=\s*\{', KAYNAK, re.M), (
        'menü paleti modül düzeyinde tek sözlükte değil')
    for isim, (r, g, b) in ((m.group(1), tuple(int(x) for x in m.groups()[1:]))
                            for m in re.finditer(
                                r'"(\w+)":\s*\((\d+),\s*(\d+),\s*(\d+)\)',
                                KAYNAK)):
        desen = r'\(\s*%d\s*,\s*%d\s*,\s*%d\s*\)' % (r, g, b)
        assert len(re.findall(desen, KAYNAK)) == 1, (
            '%s rengi (%d,%d,%d) birden fazla yerde yazılmış' % (isim, r, g, b))
    for anahtar in ('serit_zemin', 'acilir_zemin', 'metin', 'secili', 'kenar'):
        assert '"%s"' % anahtar in KAYNAK, 'palette %s anahtarı yok' % anahtar


# ---------------------------------------------------------------------------
# 4. Çökme yasağı ve dürüstlük dili
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('islev_adi', [
    '_windows_form_ikonu',
    '_windows_menu_temasi',
    '_windows_menu_ogeleri_boya',
    '_windows_koyu_cizici',
    '_windows_forms',
])
def test_her_dotnet_atamasi_kendi_try_govdesinde(islev_adi):
    """.NET öznitelik ataması try dışında kalırsa pencere hiç açılmayabilir."""
    islev = _islev(islev_adi)
    korunan = _try_korumali_dugumler(islev)
    for node in ast.walk(islev):
        if isinstance(node, ast.Assign) and any(
                isinstance(h, ast.Attribute) for h in node.targets):
            hedef = [h.attr for h in node.targets if isinstance(h, ast.Attribute)]
            assert node in korunan, (
                '%s(): "%s" ataması try gövdesinde değil (satır %d)'
                % (islev_adi, '/'.join(hedef), node.lineno))


def test_chrome_fix_arayuz_is_parcacigina_geciyor():
    """'shown' işleyicisi ayrı bir iş parçacığında koşuyor (webview/event.py);
    WinForms denetimleri kendi iş parçacığından değiştirilmeli."""
    kaynak = _islev_kaynagi('_windows_chrome_fix')
    assert 'InvokeRequired' in kaynak, 'iş parçacığı denetimi yok'
    assert 'BeginInvoke' in kaynak or 'Invoke(' in kaynak, (
        'arayüz iş parçacığına marshalling yok')


def test_durustluk_beyani_docstringde():
    """Doğrulama yapılmadan 'düzeltildi' denmemeli.

    Windows'ta gerçekten doğrulandığında bu ibare BİLEREK güncellenecek ve bu
    test o zaman elle düzeltilecek — yani ibare bir kilit değil, bir kayıt.
    """
    docstring = ast.get_docstring(_islev('_windows_chrome_fix')) or ''
    d = _tr_kucult(docstring)
    assert 'doğrulanmadı' in d and 'windows' in d, (
        '_windows_chrome_fix docstring\'inde "Windows\'ta DOĞRULANMADI" '
        'beyanı yok:\n%s' % docstring)


def test_dogrulandi_iddiasi_yok():
    k = _tr_kucult(KAYNAK)
    for iddia in ("windows'ta doğrulandı", "windows'ta test edildi",
                  "windows'ta sınandı", "windows'ta doğrulanmıştır"):
        assert iddia not in k, 'kaynakta asılsız doğrulama iddiası: %s' % iddia
