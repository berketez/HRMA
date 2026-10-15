# -*- coding: utf-8 -*-
"""ÖH FAZ B-3 / Paket 2 — C4: serileştirici ALAN-EŞLİĞİ bekçileri.

ÖLÇÜLEN KUSUR (P13 savcı §3.1-C4, §1.3 B4-03/-04/-05 + P10 D-03 devri)
----------------------------------------------------------------------
Depoda beş serileştirici elle ≥5 anahtar sayıyor ve **beşinde de** iç nesne
ile yayımlanan gövde arasında alan-eşliği bekçisi yok. Sonuç tek cümleyle:
çözücü dürüst bir bayrak/künye üretiyor, serileştirici onu sessizce
düşürüyor, kullanıcı ve programatik tüketici o bayrağı hiçbir kanaldan
göremiyor. Bugüne kadarki bekçiler kusuru göremedi çünkü hepsi **iç
nesnenin üstünde** duruyor (P10 D-03'ün adı: "bekçi serileştiricinin
üstünde"): ``tests/test_tank_blowdown.py:132/:139`` ``state['vapor_model_
valid']``i sınıyor, ``tests/test_stability_tablolar.py:257`` ``record_
confidence``ı sınıyor — ikisi de serileştiricinin GİRDİ tarafında.

ADRES DÜZELTMESİ (ÖLÇÜLDÜ, uydurulmadı)
---------------------------------------
Paket görevinde iki modül ``hrma/analysis/`` altında adreslenmişti; ikisi
de ``hrma/stability/`` altında yaşıyor (``fuel_thermal.py``, ``response.
py``). Savcı §3.1-C4 satırı dizin vermeden yazdığı için sapma orada değil,
paket promptunda. Beş adresin SATIR numaraları bugünkü depoda birebir
tutuyor (``test_serilestirici_adresleri_yerinde`` bunu her koşumda ölçer).

ÖLÇÜLEN SAYILAR (bu dosyanın fikstürleriyle yeniden üretilir)
-------------------------------------------------------------
    S1 status_report._flatten_cell   iç 20 anahtar -> yayım  9  (13 düşüyor;
                                     min/max -> worst_test_id indirgemesi
                                     gerekçeli izinle düşülünce defterin
                                     saydığı 11 kalır)
    S2 tank_blowdown._pack_state     iç  8 anahtar -> blok 36 anahtar,
                                     ``vapor_model_valid`` blokta YOK
    S3 fuel_thermal.ThermalProperty  iç  7 -> yayım 7 (serileştirici sağlam)
                                     ama ürün tüketicisi 0 -> gövde YOK
    S4 response.QSHODBand            iç  7 -> yayım 7, blokta 7/7 TAM
                                     (kampanyanın SAĞLIKLI örneği)
    S5 bands.QSHODBandRecord         iç  5 -> yayım 5, ürün gövdesinde
                                     künye alanları 0 kez

BU DOSYANIN ÇAPASI: ENVANTER ÜRÜNDEN TÜRETİLİR
----------------------------------------------
Hiçbir alan listesi elle yazılmaz. İç envanter ya ``__slots__``tan ya da
ürünün KENDİ üreticisi çağrılarak (``correlation_runner._cell``,
``N2OTankBlowdown.step``, ``qshod_response_band``, katalog kaydı) alınır;
yayımlanan gövde ya ürün fonksiyonu koşularak (``SolidRocketEngine.
_qshod_band_block``) ya da ürün kaynağının AST'inden (``_tank_blowdown_
block``ın ``status='modelled'`` dönüş sözlüğü) çıkarılır. Böylece alan
eklenince/silinince bekçi kendiliğinden görür.

DÜRÜSTLÜK ALANI ⟷ KOZMETİK ALAN AYRIMI
--------------------------------------
Düşen her alan iki kovadan birine girer:

* **Dürüstlük alanı** (ad deseniyle sınıflanır: valid / confidence / note /
  basis / warning / reason / status / source / outlier / flag / campaign /
  measurement_u / normalized_error / retrieved / reference / record_id):
  düşmesi KUSUR iddiasıdır. İzin listesine ancak **başka bir kanalda
  yaşadığı mekanik olarak gösterilirse** girebilir (``yasadigi_yer`` +
  gerekirse ``kanit``). Gerekçe metni tek başına yetmez.
* **Kozmetik/iç alan**: gerekçeli izin listesine girer. Gerekçe 40
  karakterden kısa olamaz ve izinli alanın iç envanterde GERÇEKTEN
  bulunması zorlanır (çürümüş izin listesi = kırmızı).

Bu iki kural bekçinin kendini silahsızlandırmasını engeller: bir dürüstlük
alanı "izinli" yapılarak susturulamaz.

DEFTER KURALI (FAZB-plan §7-5, ana model onaylı)
------------------------------------------------
Bugün kırmızı olan iddia ``xfail(strict=True)`` + defter-ID yorumuyla
yazılır; ürün onarımı inince XPASS olur, strict kip kırmızıya çevirir ve
işaretin SİLİNMESİNİ zorlar. Bu dosya ÜRÜN KODUNA DOKUNMAZ.

    xfail'li borçlar:  P13B4-05 (S1) · P13B4-04 (S2) · P13B4-05+P10 D-03
                       (S3) · P13B4-03 (S5, iki iddia)
    bugün yeşil:       S4 üçlüsü (band/mod satırı/köşe satırı), adres
                       bekçisi, uç-kimlik bekçisi, izin listesi denetimi
"""

import ast
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence, Set, Tuple

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hrma.analysis.tank_blowdown import N2OTankBlowdown          # noqa: E402
from hrma.engines.solid_rocket_engine import SolidRocketEngine   # noqa: E402
from hrma.stability import bands as bands_mod                    # noqa: E402
from hrma.stability import fuel_thermal as fuel_thermal_mod      # noqa: E402
from hrma.stability.response import (                            # noqa: E402
    QSHODBand,
    qshod_response,
    qshod_response_band,
)
from hrma.validation import correlation_runner as _cr            # noqa: E402
from hrma.validation.status_report import _flatten_cell          # noqa: E402

HRMA_DIR = os.path.join(REPO_ROOT, 'hrma')


# ===========================================================================
# 0. ORTAK ALTYAPI — sınıflandırıcı, izin sözleşmesi, eşlik raporu
# ===========================================================================

#: Dürüstlük alanı ad desenleri. Her desen bir BEYAN taşıyan alan ailesini
#: yakalar; düşmesi kullanıcının/tüketicinin bilgiyi kaybetmesi demektir.
#: (Kaynak: görev tanımı "valid/confidence/note/basis/warning sınıfı" +
#: ürünün kendi sözcükleri — ör. fuel_thermal "a temperature-blind value is
#: not published", correlation_runner F006/F007/F008 dürüstlük alanları.)
DURUSTLUK_DESENLERI: Tuple[Tuple[str, str], ...] = (
    (r'valid', 'geçerlilik bayrağı'),
    (r'confidence', 'güven derecesi'),
    (r'notes?$|_note', 'kayıt notu'),
    (r'basis', 'dayanak / künye'),
    (r'warning', 'uyarı metni'),
    (r'reason', 'gerekçe'),
    (r'status', 'durum beyanı'),
    (r'source', 'kaynak künyesi'),
    (r'outlier', 'aykırı kayıt beyanı'),
    (r'anomaly', 'anomali beyanı'),
    (r'flags?$', 'bayrak listesi'),
    (r'campaign', 'kampanya (sözde-tekrar) beyanı'),
    (r'in_sample', 'örneklem-içi bağımlılık bayrağı'),
    (r'weak_evidence', 'zayıf kanıt bayrağı'),
    (r'measurement_u', 'ölçüm belirsizliği'),
    (r'normalized_error', 'normalize hata E_n'),
    (r'retrieved', 'doğrulama tarihi'),
    (r'reference', 'referans koşulu (karar 4)'),
    (r'record_id', 'kayıt künyesi'),
    (r'missing|not_modelled', 'eksiklik beyanı'),
)


def durustluk_sinifi(alan: str) -> Optional[str]:
    """Alan adı dürüstlük sınıfına giriyorsa gerekçesini, yoksa None döner."""
    ad = alan.lower()
    for desen, aciklama in DURUSTLUK_DESENLERI:
        if re.search(desen, ad):
            return aciklama
    return None


def normalize(alan: str) -> str:
    """Yalnız yazım farkını siler (percent ⟷ pct); anlam eşlemesi YAPMAZ.

    Gerçek ad değişiklikleri (``confidence`` -> ``record_confidence`` gibi)
    kasten burada çözülmez: her biri gerekçeli izin listesinde ``yasadigi_
    yer`` ile ADIYLA gösterilir, böylece sessiz eşleşme olmaz.
    """
    return alan.lower().replace('percent', 'pct')


@dataclass(frozen=True)
class Izin:
    """Bir alanın yayımlanan gövdede bulunmamasına gerekçeli izin.

    Alanlar:
        alan: iç envanterdeki ad (envanterde bulunması ZORUNLU).
        gerekce: neden düşmesinin bilgi kaybı olmadığı (>= 40 karakter).
        yasadigi_yer: bilginin yaşadığı yayımlanan anahtar. Dürüstlük
            sınıfındaki alanlar için ZORUNLU ve gövdede varlığı ölçülür.
        kanit: (ic_govde, yayim_govde) -> (tamam, aciklama). Verilirse
            koşulur; hayatta kalmayı DEĞERLE ispatlar.
        deger_esit: True ise ic[alan] == yayim[yasadigi_yer] zorlanır.
    """

    alan: str
    gerekce: str
    yasadigi_yer: Optional[str] = None
    kanit: Optional[Callable[[Mapping, Mapping], Tuple[bool, str]]] = None
    deger_esit: bool = False


@dataclass
class EslikRaporu:
    ad: str
    ic: Tuple[str, ...]
    yayim: Tuple[str, ...]
    dusen: Tuple[str, ...]
    izinli: Tuple[str, ...]
    ihlaller: Tuple[str, ...]
    durustluk_ihlalleri: Tuple[str, ...]

    def metin(self) -> str:
        satir = [
            f'{self.ad}: iç {len(self.ic)} alan -> yayım {len(self.yayim)} '
            f'alan; düşen {len(self.dusen)}, gerekçeli izinli '
            f'{len(self.izinli)}, GEREKÇESİZ {len(self.ihlaller)} '
            f'(dürüstlük: {len(self.durustluk_ihlalleri)})',
            f'  iç      : {list(self.ic)}',
            f'  yayım   : {list(self.yayim)}',
            f'  düşen   : {list(self.dusen)}',
        ]
        if self.durustluk_ihlalleri:
            satir.append('  DÜRÜSTLÜK ALANI DÜŞÜYOR:')
            for i in self.durustluk_ihlalleri:
                satir.append(f'    - {i}')
        for i in self.ihlaller:
            if i not in self.durustluk_ihlalleri:
                satir.append(f'  gerekçesiz düşen: {i}')
        return '\n'.join(satir)


def _anahtarlar(govde: Any) -> Tuple[str, ...]:
    if isinstance(govde, Mapping):
        return tuple(govde)
    return tuple(sorted(govde))


def izin_denetimi(ad: str, ic: Any, yayim: Any,
                  izinler: Sequence[Izin]) -> Tuple[str, ...]:
    """İzin listesinin kendi sözleşmesini denetler (çürüme + susturma kapısı).

    Bu denetim izinli alan düşsün düşmesin koşar: izin listesi ürünün
    envanterinden saparsa (alan artık yok, gerekçe boş, dürüstlük alanı
    kanıtsız izinli) bekçi kırmızıya döner.
    """
    ic_anahtar = set(_anahtarlar(ic))
    yayim_anahtar = set(_anahtarlar(yayim))
    hatalar = []
    goruldu = set()
    for izin in izinler:
        if izin.alan in goruldu:
            hatalar.append(f'{ad}: {izin.alan!r} izin listesinde iki kez var')
        goruldu.add(izin.alan)
        if izin.alan not in ic_anahtar:
            hatalar.append(
                f'{ad}: izin listesi çürümüş — {izin.alan!r} artık iç '
                f'envanterde yok (envanter: {sorted(ic_anahtar)})')
            continue
        if len((izin.gerekce or '').strip()) < 40:
            hatalar.append(
                f'{ad}: {izin.alan!r} izninin gerekçesi yok/kısa — '
                f'"gerekçesiz izin" bekçiyi susturur')
        sinif = durustluk_sinifi(izin.alan)
        if sinif and not (izin.yasadigi_yer or izin.kanit):
            hatalar.append(
                f'{ad}: {izin.alan!r} DÜRÜSTLÜK alanı ({sinif}) ve kanıtsız '
                f'izinli — dürüstlük alanı ancak başka bir kanalda '
                f'yaşadığı GÖSTERİLİRSE izinli olabilir')
        if izin.yasadigi_yer and izin.yasadigi_yer not in yayim_anahtar:
            hatalar.append(
                f'{ad}: {izin.alan!r} için gösterilen yaşam yeri '
                f'{izin.yasadigi_yer!r} yayımlanan gövdede YOK '
                f'({sorted(yayim_anahtar)})')
        elif (izin.deger_esit and izin.yasadigi_yer
                and isinstance(ic, Mapping) and isinstance(yayim, Mapping)):
            if ic[izin.alan] != yayim[izin.yasadigi_yer]:
                hatalar.append(
                    f'{ad}: {izin.alan!r} değeri {izin.yasadigi_yer!r} '
                    f'anahtarında AYNEN taşınmıyor '
                    f'({ic[izin.alan]!r} != {yayim[izin.yasadigi_yer]!r})')
        if izin.kanit is not None:
            tamam, aciklama = izin.kanit(ic, yayim)
            if not tamam:
                hatalar.append(
                    f'{ad}: {izin.alan!r} için kanıt tutmadı — {aciklama}')
    return tuple(hatalar)


def eslik_raporu(ad: str, ic: Any, yayim: Any,
                 izinler: Sequence[Izin] = ()) -> EslikRaporu:
    """İç nesne ⟷ yayımlanan gövde alan-eşliği raporu."""
    ic_anahtar = _anahtarlar(ic)
    yayim_anahtar = _anahtarlar(yayim)
    yayim_norm = {normalize(k) for k in yayim_anahtar}
    izinli_adlar = {i.alan for i in izinler}

    dusen = tuple(a for a in ic_anahtar if normalize(a) not in yayim_norm)
    ihlaller = []
    durustluk_ihlalleri = []
    for alan in dusen:
        if alan in izinli_adlar:
            continue
        sinif = durustluk_sinifi(alan)
        if sinif:
            mesaj = (f'{alan!r} ({sinif}) iç nesnede var, yayımlanan '
                     f'gövdede YOK')
            durustluk_ihlalleri.append(mesaj)
            ihlaller.append(mesaj)
        else:
            ihlaller.append(
                f'{alan!r} düşüyor ve gerekçeli izin listesinde değil')
    return EslikRaporu(
        ad=ad, ic=ic_anahtar, yayim=yayim_anahtar, dusen=dusen,
        izinli=tuple(a for a in dusen if a in izinli_adlar),
        ihlaller=tuple(ihlaller),
        durustluk_ihlalleri=tuple(durustluk_ihlalleri))


def eslik_iddiasi(ad: str, ic: Any, yayim: Any,
                  izinler: Sequence[Izin] = ()) -> EslikRaporu:
    """Eşliği ZORLAR: izin sözleşmesi + gerekçesiz düşen alan yasağı."""
    izin_hatalari = izin_denetimi(ad, ic, yayim, izinler)
    assert not izin_hatalari, (
        'izin listesi sözleşmeyi çiğniyor:\n  ' + '\n  '.join(izin_hatalari))
    rapor = eslik_raporu(ad, ic, yayim, izinler)
    assert not rapor.ihlaller, rapor.metin()
    return rapor


# --- ürün kaynağından envanter çıkaran AST yardımcıları ---------------------

def _agac(gorece_yol: str) -> ast.AST:
    with open(os.path.join(REPO_ROOT, gorece_yol), encoding='utf-8') as fh:
        return ast.parse(fh.read())


def fonksiyon_dugumu(agac: ast.AST, nitelikli_ad: str) -> ast.FunctionDef:
    """``Sinif.metot`` ya da ``fonksiyon`` adını AST'te bulur."""
    parcalar = nitelikli_ad.split('.')
    kapsam = agac
    for i, parca in enumerate(parcalar):
        son = (i == len(parcalar) - 1)
        bulunan = None
        for dugum in ast.iter_child_nodes(kapsam):
            if son and isinstance(dugum, ast.FunctionDef) and dugum.name == parca:
                bulunan = dugum
                break
            if not son and isinstance(dugum, ast.ClassDef) and dugum.name == parca:
                bulunan = dugum
                break
        assert bulunan is not None, (
            f'{nitelikli_ad!r} AST\'te bulunamadı (adres kaymış olabilir)')
        kapsam = bulunan
    return kapsam  # type: ignore[return-value]


def donus_sozlugu_anahtarlari(gorece_yol: str, nitelikli_ad: str,
                              durum_degeri: str) -> Tuple[str, ...]:
    """Fonksiyonun ``'status': <durum_degeri>`` taşıyan dönüş sözlüğü."""
    dugum = fonksiyon_dugumu(_agac(gorece_yol), nitelikli_ad)
    adaylar = []
    for alt in ast.walk(dugum):
        if not isinstance(alt, ast.Return) or not isinstance(alt.value, ast.Dict):
            continue
        anahtarlar = [k.value for k in alt.value.keys
                      if isinstance(k, ast.Constant)]
        degerler = {k.value: v for k, v in zip(alt.value.keys, alt.value.values)
                    if isinstance(k, ast.Constant)}
        durum = degerler.get('status')
        if isinstance(durum, ast.Constant) and durum.value == durum_degeri:
            adaylar.append(tuple(anahtarlar))
    assert len(adaylar) == 1, (
        f'{gorece_yol}:{nitelikli_ad} içinde status={durum_degeri!r} olan '
        f'dönüş sözlüğü tam olarak 1 tane olmalı, {len(adaylar)} bulundu — '
        f'adres/şekil kaymış, envanter körlemesine okunmuyor')
    return adaylar[0]


def _urun_dosyalari() -> Tuple[str, ...]:
    yollar = []
    for kok, dizinler, dosyalar in os.walk(HRMA_DIR):
        dizinler[:] = [d for d in dizinler if d != '__pycache__']
        for ad in dosyalar:
            if ad.endswith('.py'):
                yollar.append(os.path.join(kok, ad))
    return tuple(sorted(yollar))


def tuketici_dosyalari(modul_dosyasi: str, modul_adi: str) -> Tuple[str, ...]:
    """``hrma/`` altında bu modülü İTHAL eden ürün dosyaları (AST)."""
    hedef_mutlak = os.path.abspath(os.path.join(REPO_ROOT, modul_dosyasi))
    tuketiciler = []
    for yol in _urun_dosyalari():
        if os.path.abspath(yol) == hedef_mutlak:
            continue
        try:
            with open(yol, encoding='utf-8') as fh:
                agac = ast.parse(fh.read())
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Import):
                if any(a.name.split('.')[-1] == modul_adi for a in dugum.names):
                    tuketiciler.append(yol)
                    break
            elif isinstance(dugum, ast.ImportFrom):
                mod = dugum.module or ''
                if (mod.split('.')[-1] == modul_adi
                        or any(a.name == modul_adi for a in dugum.names)):
                    tuketiciler.append(yol)
                    break
    return tuple(sorted(set(tuketiciler)))


def govde_anahtarlari(dosyalar: Sequence[str]) -> Set[str]:
    """Verilen ürün dosyalarındaki sözlük literallerinin sabit anahtarları."""
    bulunan: Set[str] = set()
    for yol in dosyalar:
        try:
            with open(yol, encoding='utf-8') as fh:
                agac = ast.parse(fh.read())
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Dict):
                for anahtar in dugum.keys:
                    if isinstance(anahtar, ast.Constant) and isinstance(
                            anahtar.value, str):
                        bulunan.add(anahtar.value)
    return bulunan


def anahtar_gecisleri(alanlar: Sequence[str],
                      haric: Sequence[str]) -> dict:
    """Alan adlarının ``hrma/`` altında sözlük ANAHTARI olarak geçtiği yerler."""
    haric_mutlak = {os.path.join(REPO_ROOT, y) for y in haric}
    bulgu = {a: [] for a in alanlar}
    for yol in _urun_dosyalari():
        if yol in haric_mutlak:
            continue
        try:
            with open(yol, encoding='utf-8') as fh:
                agac = ast.parse(fh.read())
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Dict):
                for anahtar in dugum.keys:
                    if (isinstance(anahtar, ast.Constant)
                            and anahtar.value in bulgu):
                        bulgu[anahtar.value].append(
                            f'{os.path.relpath(yol, REPO_ROOT)}:'
                            f'{anahtar.lineno}')
    return bulgu


# ===========================================================================
# 1. ADRES BEKÇİSİ — beş serileştirici defterin yazdığı satırda mı?
# ===========================================================================

#: (defter kodu, dosya, satır, nitelikli ad). Satırlar P13 §3.1-C4'ten;
#: dizinler ÖLÇÜLDÜ (paket promptundaki ``hrma/analysis/`` iki modülde
#: yanlıştı — ikisi de ``hrma/stability/`` altında).
SERILESTIRICILER: Tuple[Tuple[str, str, int, str], ...] = (
    # ÖH D16/app-api P10B2-01: künye taşıyıcı blok _flatten_cell'in ÜSTÜNE
    # eklendi (49 -> 85). Adres kaydı defterin kendi kuralıyla güncellendi.
    # ÖH D27 a3 / P13B4-05: _HONESTY_FIELDS künye bloğu _flatten_cell'in
    # ÜSTÜNE girdi, tanım 85 -> 114'e kaydı (P10B2-01 desenin aynısı).
    ('S1', 'hrma/validation/status_report.py', 114, '_flatten_cell'),
    # ÖH D27/hibrit a1: iki adres TABANDA (709a235e) ZATEN kaymıştı ve bu
    # bekçi orada da kırmızıydı — kayma bu kulvarın değişikliğinden DEĞİL,
    # önceki dalgaların ürün dosyalarına eklediği künye/gerekçe
    # bloklarından doğuyor (bu kulvar iki dosyanın ikisine de dokunmadı).
    # Defterin kendi kuralıyla (S1 satırındaki D16 örneği) adres kaydı
    # güncellendi: S2 473 -> 543, S4 184 -> 223. Eşik değil ADRES
    # güncellenir; iddianın gücü aynen durur. (Birleşme: S1 app-api a3, S2/S4 hibrit a1.)
    ('S2', 'hrma/analysis/tank_blowdown.py', 543, 'N2OTankBlowdown._pack_state'),  # Z1: doyma tablosu 306->309 K uzadı, adres kaydı
    ('S3', 'hrma/stability/fuel_thermal.py', 123, 'ThermalProperty.as_dict'),
    ('S4', 'hrma/stability/response.py', 223, 'QSHODBand.as_dict'),
    ('S5', 'hrma/stability/bands.py', 103, 'QSHODBandRecord.as_dict'),
)


def test_serilestirici_adresleri_yerinde():
    """Beş serileştirici defterin adreslediği dosya:satırda duruyor.

    Adres bekçisi olmadan alan-eşliği iddiaları sessizce boş kümeye
    dayanabilir (fonksiyon taşınır, AST okuması hiç bulmaz, bekçi yeşil
    kalır). Bu iddia kayma olduğu an kırmızı verir ve defterin adresini
    düzelttirir.
    """
    sapma = []
    for kod, yol, satir, nitelikli in SERILESTIRICILER:
        tam = os.path.join(REPO_ROOT, yol)
        assert os.path.exists(tam), f'{kod}: {yol} yok'
        dugum = fonksiyon_dugumu(_agac(yol), nitelikli)
        if dugum.lineno != satir:
            sapma.append(f'{kod} {yol}:{satir} -> gerçekte '
                         f'{dugum.lineno} ({nitelikli})')
    assert not sapma, (
        'serileştirici adresleri kaymış (defter güncellenmeli):\n  '
        + '\n  '.join(sapma))


# ===========================================================================
# 2. S1 — status_report._flatten_cell (P13B4-05, P10 D-03)
# ===========================================================================

def _s1_ic_hucre() -> dict:
    """İç nesne: correlation_runner'ın KENDİ hücre üreticisinden."""
    girisler = [
        {'test_id': 'olcum_a', 'error_pct': 3.0, 'confidence': 'high',
         'campaign': 'kampanya_1', 'flags': ['in_sample'],
         'measurement_u_pct': 0.8, 'normalized_error': 0.4},
        {'test_id': 'olcum_b', 'error_pct': -5.0, 'confidence': 'high',
         'campaign': 'kampanya_2', 'flags': ['weak_evidence'],
         'measurement_u_pct': 1.2, 'normalized_error': 1.1},
        {'test_id': 'olcum_c', 'error_pct': 1.0, 'confidence': 'medium',
         'campaign': 'kampanya_2', 'flags': [],
         'measurement_u_pct': None, 'normalized_error': None},
    ]
    return _cr._cell('hybrid', 'c_star', girisler, 'high_medium')


S1_IZINLER = (
    Izin(alan='min',
         gerekce=('uç kayıt çifti tek "en kötü" kimliğe indirgeniyor: '
                  'mutlak hatası büyük olanın test_id\'si yayımlanıyor'),
         yasadigi_yer='worst_test_id'),
    Izin(alan='max',
         gerekce=('uç kayıt çiftinin diğer ucu; aynı indirgemeye giriyor '
                  've kimliği worst_test_id alanında yayımlanıyor'),
         yasadigi_yer='worst_test_id'),
    Izin(alan='entries',
         gerekce=('ham satır listesi: düz hücre görünümü tasarımı gereği '
                  'satır ayrıntısı taşımaz (rapor/panel şekli). Dürüstlük '
                  'sınıfında değil — satırların güven/bayrak özeti hücre '
                  'düzeyinde AYRI alanlarda duruyor ve o alanların düşmesi '
                  'bu bekçide ayrıca sayılıyor.')),
)


# ÖH D27 / app-api a3 (P13B4-05) — xfail(strict) BORÇ İMİ KALDIRILDI.
# Onarım indi: ``status_report._HONESTY_FIELDS`` dört dürüstlük alanını
# (``confidence_band``, ``campaign_stats``, ``outlier_test_ids``,
# ``stats_excl_outliers``) yayımlanan hücreye taşıyor. İmin kendi yazdığı
# şart ("onarım inince XPASS olur") yerine geldi; im kalsaydı süit XPASS
# ile kırılırdı. İDDİA AYNEN durur ve artık ileri yönde koşar: onarımın
# geri alınması bu testi KIRMIZI yapar (ters-mutasyon M6).
def test_s1_korelasyon_hucresi_alan_esligi():
    """İç hücre ⟷ /api/correlation-report hücresi alan-eşliği.

    ``_flatten_cell`` API katmanıyla PAYLAŞILAN tek düzleştirmedir
    (modülün kendi docstring'i); yani burada düşen alan kullanıcıya giden
    gövdede bir daha doğmaz.
    """
    ic = _s1_ic_hucre()
    yayim = _flatten_cell(ic, 'main')
    eslik_iddiasi('S1 _flatten_cell', ic, yayim, S1_IZINLER)


def test_s1_dusen_alanlar_defterin_saydigi_kadar():
    """Ölçüm çapası: iç 20 / yayım 16; defterin saydığı 5 düşen alan.

    Bu iddia kusuru DÜZELTMEZ, kusurun KALAN BOYUNU dondurur: bir alan daha
    düşürülürse (ya da defterdeki sayı ürüne uymuyorsa) kırmızı verir.

    ÖH D16 / app-api — P10B2-01 ONARIMI SONRASI GÜNCELLENDİ. Eski sayılar
    (yayım 9, ham düşen 13, defter 11, dürüstlük ihlali 10) kusurun ÖNCEKİ
    boyuydu; onarım altı bağımlılık/belirsizlik alanını + türetilmiş
    ``dependence`` künyesini yayımlanan yola taşıdı, ölçülen düşüş
    13 -> 7'ye, dürüstlük ihlali 10 -> 4'e indi. Bekçi kusuru koruyan
    sayıyı dondurmaya devam ETMEZ; yeni ölçülen tabanı dondurur.

    Ham sayım 7'dir; aradaki fark ADIYLA kapatılır: ``min``/``max`` çifti
    ``worst_test_id`` içinde YAŞADIĞI için defterin sayımına girmiyor
    (7 - 2 = 5). Kalan 4'ün tamamı dürüstlük alanı
    (``campaign_stats``, ``confidence_band``, ``outlier_test_ids``,
    ``stats_excl_outliers`` — P13B4-05 / P10 D-03'ün konusu, bu kalemin
    değil); 5'inci kalem ``entries`` (kozmetik, gerekçeli izinli).
    """
    ic = _s1_ic_hucre()
    yayim = _flatten_cell(ic, 'main')
    rapor = eslik_raporu('S1', ic, yayim, S1_IZINLER)
    # ÖH D27 / app-api a3 (P13B4-05) — ONARIM SONRASI TABAN.
    # Eski sayılar (yayım 16, ham düşen 7, defter 5, dürüstlük ihlali 4)
    # kusurun ÖNCEKİ boyuydu. Onarım dört dürüstlük alanını yayımlanan
    # yola taşıdı: yayım 16 -> 20, ham düşüş 7 -> 3, DÜRÜSTLÜK İHLALİ
    # 4 -> 0. Kalan üç düşüş gerekçelidir ve üçü de ``S1_IZINLER``de
    # adıyla durur (``min``/``max`` -> ``worst_test_id``; ``entries`` ham
    # satır listesi). Bekçi artık kusuru değil ONARIMI donduruyor: bir
    # dürüstlük alanı yeniden düşürülürse kırmızı verir.
    assert len(ic) == 20, f'iç hücre şekli değişmiş: {sorted(ic)}'
    assert len(yayim) == 20, f'yayımlanan hücre şekli değişmiş: {sorted(yayim)}'
    assert len(rapor.dusen) == 3, rapor.metin()
    # Başka bir adla yaşayanlar düşülünce GERÇEKTEN kaybolan sayı çıkmalı.
    baska_adla_yasayan = sum(1 for i in S1_IZINLER
                             if i.alan in rapor.dusen and i.yasadigi_yer)
    assert len(rapor.dusen) - baska_adla_yasayan == 1, rapor.metin()
    assert len(rapor.ihlaller) == 0, rapor.metin()
    assert len(rapor.durustluk_ihlalleri) == 0, rapor.metin()
    # Dört dürüstlük alanının DÖRDÜ de yayımlanan gövdede.
    for _ad in ('confidence_band', 'campaign_stats', 'outlier_test_ids',
                'stats_excl_outliers'):
        assert _ad in yayim, f'{_ad} yeniden düşürülmüş'
    # P10B2-01 bekçisi: in-sample künyesi ARTIK düşenler arasında DEĞİL.
    assert 'n_in_sample' not in rapor.dusen, rapor.metin()
    assert yayim['dependence'], yayim


def test_s1_ucta_serilestirici_son_duraktir():
    """Uç, hücreleri serileştiriciden AYNEN alıyor — kayıp geri alınamıyor.

    ``_correlation_report_body`` gövdesinde ``'cells'`` anahtarının değeri
    doğrudan ``correlation_cells(...)`` çağrısıdır: uç katmanı hücreye alan
    EKLEMİYOR. Bu yüzden S1'in düşürdüğü dürüstlük alanları için "belki
    uçta geri gelir" savunması ölçüyle kapalıdır.
    """
    dugum = fonksiyon_dugumu(_agac('hrma/app.py'), '_correlation_report_body')
    bulundu = []
    for alt in ast.walk(dugum):
        if not isinstance(alt, ast.Dict):
            continue
        for anahtar, deger in zip(alt.keys, alt.values):
            if (isinstance(anahtar, ast.Constant) and anahtar.value == 'cells'
                    and isinstance(deger, ast.Call)):
                ad = getattr(deger.func, 'id', None) or getattr(
                    deger.func, 'attr', None)
                bulundu.append(ad)
    assert bulundu == ['correlation_cells'], (
        "uç gövdesindeki 'cells' artık doğrudan correlation_cells(...) "
        f'çağrısı değil (bulunan: {bulundu}) — S1 bekçisinin "serileştirici '
        'son duraktır" dayanağı doğrulanamıyor')


# ===========================================================================
# 3. S2 — tank_blowdown._pack_state ⟷ hibrit blowdown bloğu (P13B4-04)
# ===========================================================================

def _s2_ic_durum() -> dict:
    """İç nesne: tankın KENDİ adım durumu (_pack_state çıktısı)."""
    tank = N2OTankBlowdown.from_oxidizer_mass(oxidizer_mass=5.0,
                                              initial_temperature=293.15)
    return tank.step(mdot_out=0.5, dt=0.05)


def _s2_yayim_blok() -> Tuple[str, ...]:
    """Yayımlanan gövde: hibrit motorun 'modelled' blowdown bloğu (AST).

    Blok gerçek bir motor koşusu ister (TransientBallistics + tam çözücü);
    envanter bu yüzden ürün KAYNAĞINDAN, ``status='modelled'`` dönüş
    sözlüğünden çıkarılır. Anahtar seti kaynağın tek doğrusudur.
    """
    return donus_sozlugu_anahtarlari(
        'hrma/engines/hybrid_rocket_engine.py',
        'HybridRocketEngine._tank_blowdown_block', 'modelled')


def _s2_zarf_kunyesi() -> str:
    """``tank_model_envelope_basis`` künyesinin METNİ (ürün kaynağından).

    Künye ürünün KENDİ dizgesidir; burada elle kopyalanmaz (kopya bayatlar
    ve iddia totolojiye döner). AST'ten okunur, böylece künye susturulursa
    ya da içi boşaltılırsa bekçi görür.
    """
    dugum = fonksiyon_dugumu(
        _agac('hrma/engines/hybrid_rocket_engine.py'),
        'HybridRocketEngine._tank_blowdown_block')
    for alt in ast.walk(dugum):
        if not isinstance(alt, ast.Dict):
            continue
        for k, v in zip(alt.keys, alt.values):
            if (isinstance(k, ast.Constant)
                    and k.value == 'tank_model_envelope_basis'
                    and isinstance(v, ast.Constant)
                    and isinstance(v.value, str)):
                return v.value
    raise AssertionError(
        'tank_model_envelope_basis künyesi ürün kaynağında bulunamadı — '
        'P13B4-04 onarımının beyan ayağı sökülmüş')


#: Faz alanının B-4 ölçümü (OH-B3-06 paketi, C-1 borcu). Üç ölçüm de ÜRÜN
#: kaynağından/koşumundan gelir; hiçbiri elle liste değildir.

def _atanan_dizgeler(gorece_yol: str, hedef) -> Set[str]:
    """Kaynakta ``hedef``e atanan DİZGE sabitlerinin kümesi (AST).

    ``hedef`` ya çıplak bir ad (``'event'``) ya da ``('self', 'phase')``
    biçiminde bir nitelik yoludur.
    """
    kume: Set[str] = set()
    for dugum in ast.walk(_agac(gorece_yol)):
        if not isinstance(dugum, ast.Assign):
            continue
        if not isinstance(dugum.value, ast.Constant) or not isinstance(
                dugum.value.value, str):
            continue
        for h in dugum.targets:
            if isinstance(hedef, tuple):
                if (isinstance(h, ast.Attribute) and h.attr == hedef[1]
                        and isinstance(h.value, ast.Name)
                        and h.value.id == hedef[0]):
                    kume.add(dugum.value.value)
            elif isinstance(h, ast.Name) and h.id == hedef:
                kume.add(dugum.value.value)
    return kume


def _s2_faz_degerleri() -> Set[str]:
    """Tankın alabildiği faz değerleri — ``self.phase`` atamalarından."""
    return _atanan_dizgeler('hrma/analysis/tank_blowdown.py',
                            ('self', 'phase'))


def _s2_end_event_degerleri() -> Set[str]:
    """``end_event``in alabildiği değerler — çözücüdeki ``event`` atamaları."""
    return _atanan_dizgeler('hrma/analysis/transient_ballistics.py', 'event')


def _s2_faz_gecisi_uyarilari() -> Tuple[str, ...]:
    """Faz GERÇEKTEN çevrilir ve ürünün ne yayımladığı ÖLÇÜLÜR.

    Tank sıvı bitene kadar koşturulur; dönen uyarı listesi ölçümdür.
    (Bugün: tek uyarı, ``IDEAL-GAS TAIL-OFF`` — 182. adımda doğuyor.)
    """
    tank = N2OTankBlowdown.from_oxidizer_mass(oxidizer_mass=5.0,
                                              initial_temperature=293.15)
    for _ in range(20000):
        if tank.step(mdot_out=0.5, dt=0.05)['phase'] == 'vapor':
            break
    else:                                             # pragma: no cover
        raise AssertionError('tank buhar fazına hiç geçmedi — fikstür bayat')
    return tuple(tank.warnings)


def _s2_faz_kaniti(ic, yayim):
    """``phase`` izninin kanıtı: bilginin yaşadığı yer ÖLÇÜLÜR.

    Eski gerekçe ("blok fazı ``end_event`` ile bildiriyor") B-4'te ölçülüp
    ÇÜRÜTÜLDÜ; ardından ölçülen tek kanal ``warnings`` METNİ idi ve o da
    bir BORÇTU (ÖH D26 / OH-B4-04). Borç ödendi. Kanıt artık dört şeyi
    birden zorlar:

    1. ``end_event`` bir SONLANMA SEBEBİ kümesidir; hiçbir üyesi tankın
       faz değerlerinden biri DEĞİLDİR (iki küme AST'ten türetilir).
    2. Faz artık DEĞER kanalı olarak yayımlanıyor: blokta ``tank_phase``
       (adım adım seri) ve ``tank_phase_final`` (çözüm sonrası tank
       durumu) alanları VARDIR. Bu ikisi kalkarsa izin ÇÖKER.
    3. Uyarı METNİ hâlâ üretilir — ama artık bilginin TEK kanalı değil,
       kuyruk fazının MODEL SINIRINI söyleyen ek beyandır.
    4. ``warnings`` kanalı blokta durmaya devam eder (sınır beyanının
       yaşadığı yer).
    """
    ortak = _s2_faz_degerleri() & _s2_end_event_degerleri()
    if ortak:
        return False, (f'end_event artık faz adı taşıyor ({sorted(ortak)}) — '
                       'iznin gerekçesi güncellenmeli')
    yayim_anahtar = set(_anahtarlar(yayim))
    eksik = {'tank_phase', 'tank_phase_final'} - yayim_anahtar
    if eksik:
        return False, (f'OH-B4-04 borcu geri açılmış: blok faz DEĞER '
                       f'kanalını yayımlamıyor (eksik: {sorted(eksik)})')
    if 'warnings' not in yayim_anahtar:
        return False, 'yayımlanan blokta warnings kanalı yok'
    uyarilar = _s2_faz_gecisi_uyarilari()
    if not any('TAIL-OFF' in u for u in uyarilar):
        return False, ('faz geçişi artık model-sınırı uyarısı üretmiyor: '
                       f'kuyruk fazının beyanı koptu ({uyarilar})')
    return True, ('faz DEĞER kanalı (tank_phase / tank_phase_final) '
                  'yayımlanıyor; model sınırı warnings metninde duruyor')


S2_IZINLER = (
    Izin(alan='time_step',
         gerekce=('adım süresi; blok seyreltilmiş zaman DİZİSİ yayımlıyor '
                  've zaman bilgisi orada tam olarak duruyor'),
         yasadigi_yer='time_s'),
    Izin(alan='P',
         gerekce=('adım tank basıncı [Pa]; blok aynı büyüklüğü birim etiketli '
                  'zaman serisi olarak yayımlıyor (bar)'),
         yasadigi_yer='tank_pressure_bar'),
    Izin(alan='T',
         gerekce=('adım tank sıcaklığı [K]; blok aynı büyüklüğü birim '
                  'etiketli zaman serisi olarak yayımlıyor'),
         yasadigi_yer='tank_temperature_K'),
    Izin(alan='mdot_delivered',
         gerekce=('adımda teslim edilen oksitleyici debisi; blok aynı '
                  'büyüklüğü mdot_ox_kg_s serisi olarak yayımlıyor'),
         yasadigi_yer='mdot_ox_kg_s'),
    Izin(alan='m_liquid',
         gerekce=('tankın iç kütle defteri; blok kütle serisi yerine itki / '
                  'toplam impuls / harcanan itici bütçesini yayımlıyor. '
                  'Beyan taşımayan durum değişkeni.')),
    Izin(alan='m_vapor',
         gerekce=('tankın iç kütle defterinin buhar kolu; aynı gerekçe — '
                  'blok kütle defterini değil enerji/itki bütçesini '
                  'yayımlıyor, beyan taşımaz.')),
    Izin(alan='phase',
         gerekce=('adımın sıvı/buhar fazı. B-4 ÖLÇÜMÜ eski gerekçeyi '
                  '("blok fazı end_event ile bildiriyor") ÇÜRÜTTÜ: '
                  'end_event bir SONLANMA SEBEBİ kümesidir '
                  '(time_limit / oxidizer_depleted / web_exhausted ...) ve '
                  'hiçbir üyesi faz adı taşımaz. ÖH D26 / OH-B4-04 BORCU '
                  'ÖDENDİ: faz artık uyarı metnine gömülü değil, blokta '
                  'ALAN olarak yayımlanıyor (tank_phase serisi + '
                  'tank_phase_final + vapor_onset_s). İç addan farklı ada '
                  'taşındığı için bu satır izin listesinde KALIR: adın '
                  'kendisi düşüyor, BİLGİ düşmüyor ve yaşadığı yer artık '
                  'metin değil DEĞER kanalıdır.'),
         yasadigi_yer='tank_phase',
         kanit=_s2_faz_kaniti),
)


# ÖH D27 / hibrit a1 — P13B4-04 BORÇ İMİ KALDIRILDI.
# İm şunu diyordu: "vapor_model_valid tankın adım durumunda var, hibrit
# motorun 40 anahtarlık blowdown bloğunda YOK — bayrağa programatik kapı
# kurulamıyor". ÖLÇÜLDÜ (``docs/scofield/raw/OH/D27/hibrit/a1/once.json``,
# taban ``709a235e``): iç 8 anahtar / bayrak VAR, blok 40 anahtar / bayrak
# YOK. SONRA (``sonra.json``): blok 43 anahtar, bayrak VAR ve değeri tankın
# KENDİ nesnesinden okunuyor. Onarım bayrağı yalnız taşımakla yetinmedi —
# ``tank_saturation_band_clamped`` ile ATEŞLENEBİLİR zarfı da değer kanalına
# çevirdi (bkz. aşağıdaki ``test_s2_zarf_kanali_deger_tasiyor``).
def test_s2_blowdown_adim_durumu_alan_esligi():
    """Tank adım durumu ⟷ hibrit sonucundaki blowdown bloğu."""
    ic = _s2_ic_durum()
    yayim = _s2_yayim_blok()
    eslik_iddiasi('S2 _pack_state -> _tank_blowdown_block', ic, yayim,
                  S2_IZINLER)


def test_s2_bayrak_ic_nesnede_var_ve_blokta_yayimlaniyor():
    """Ölçüm çapası: bayrak üretiliyor (iç) VE yayımlanıyor (blok).

    ADI DEĞİŞTİ (ÖH D27 / P13B4-04). Eski ad
    ``test_s2_bayrak_ic_nesnede_var_ve_bloktan_uzak`` idi ve o cümle artık
    DOĞRU DEĞİL. Eski bekçiler (``tests/test_tank_blowdown.py:132/:139``)
    tam olarak iç nesnenin üstünde duruyordu; onlar yeşilken kullanıcı
    bayrağı hiçbir kanaldan göremiyordu. Bu iddia kapanışı dondurur:
    bayrak düşerse ya da blok onu yeniden yutarsa kırmızı verir.
    """
    ic = _s2_ic_durum()
    blok = _s2_yayim_blok()
    assert 'vapor_model_valid' in ic, (
        'tank adım durumu artık vapor_model_valid üretmiyor — P13B4-04 '
        'kaleminin zemini değişmiş')
    # ÖH D26 / OH-B4-04: şekil 36 -> 40 (faz kanalı). ÖH D27 / P13B4-04:
    # 40 -> 43 (vapor_model_valid + tank_saturation_band_clamped +
    # tank_model_envelope_basis). ÖH D28 / OH-D27-09: 43 -> 48 — kesilen
    # payın DEĞER kanalı (vapor_phase_integrated, residual_oxidizer_kg,
    # residual_impulse_at_cutoff_rate_Ns,
    # residual_impulse_fraction_at_cutoff_rate,
    # vapor_tail_off_leaves_model_envelope); beşi de
    # ``docs/scofield/raw/OH/D28/hibrit/a1/`` ölçümüne ve
    # ``tests/test_d28_hibrit_a1.py`` bekçisine bağlıdır. Sayı bir ÇAPADIR:
    # bloğa beyansız alan eklenirse bu satır kırmızı verir.
    assert len(blok) == 48, f'blowdown bloğu şekli değişmiş: {len(blok)}'
    assert 'vapor_model_valid' in blok, (
        'blowdown bloğu bayrağı yeniden yutuyor: P13B4-04 geri açılmış — '
        'zarf bilgisi tekrar yalnız uyarı metnine gömüldü')
    # Hafifletici mekanizmanın canlılığı: uyarılar birleştiriliyor.
    assert 'warnings' in blok


def test_s2_zarf_kanali_deger_tasiyor():
    """Yayımlanan zarf kanalı GERÇEK bir kapı mı? (ÖH D27 / P13B4-04)

    Bayrağı taşımak tek başına yetmez. ÖLÇÜLDÜ (``once.json`` /
    ``probe``): ``vapor_model_valid`` bu blokta YAPISAL OLARAK True'dur —
    ``TransientBallistics.solve`` yürüyüşü ``tank.phase == 'vapor'``
    olduğu anda kırıldığı için hiçbir buhar adımı integre edilmez,
    dolayısıyla üçlü nokta tabanı bu bloktan ateşlenemez. Ateşlenebilen
    zarf doygunluk bandı kenetlenmesidir (ölçüldü: Pc = 8 bar / 245 K
    tankta 208 örneğin 70'i kenetli, nominal 20 bar / 293,15 K'de 0).

    Bu iddia iki şeyi birden zorlar: (1) ateşlenebilen zarfın kendi DEĞER
    kanalı vardır, (2) blok bu ikisini karıştırmaz — künye hangisinin
    ateşlenebildiğini ADIYLA söyler. Kanal düşerse ya da künye susarsa
    kalan tek kanal yine uyarı METNİ olurdu (kalemin ta kendisi).
    """
    blok = _s2_yayim_blok()
    for ad in ('tank_saturation_band_clamped', 'tank_model_envelope_basis'):
        assert ad in blok, (
            f'zarf kanalı eksik: {ad} — bayrak yayımlanıyor ama '
            'ateşlenebilen zarfın programatik kapısı yok')
    # Künye, bayrağın bu blokta yapısal olarak True olduğunu SÖYLEMELİ:
    # sessiz bir "hep doğru" bayrak, olmayan bir kapıyı varmış gibi
    # gösterirdi (doktrin 1).
    kunye = _s2_zarf_kunyesi()
    for parca in ('oxidizer_depleted', 'triple point', '240-306 K'):
        assert parca in kunye, (
            f'zarf künyesi {parca!r} demiyor: bayrağın neyi garanti ettiği '
            've hangi zarfın ateşlenebildiği okunamıyor')


def test_s2_faz_izninin_dayanagi_canli():
    """ÖLÇÜM ÇAPASI (B-4 → D26): ``phase`` izninin dayanağı canlı mı?

    ADI DEĞİŞTİ (ÖH D26 / OH-B4-04). Eski ad
    ``test_s2_faz_bilgisi_yalniz_uyari_metninde_yasiyor`` idi ve o cümle
    artık DOĞRU DEĞİL: faz, blokta ``tank_phase`` / ``tank_phase_final``
    alanlarıyla DEĞER olarak yayımlanıyor. Ölçülen dayanaklar aynen
    duruyor (aşağıdaki üç iddia bit-aynı), yalnız uyarı metninin ROLÜ
    değişti: bilginin TEK kanalı değil, kuyruk fazının MODEL SINIRINI
    söyleyen beyandır.

    Bu iddia ölçümü xfail'in ARKASINDAN ÇIKARIR:
    :func:`test_s2_blowdown_adim_durumu_alan_esligi` hâlâ
    ``vapor_model_valid`` (P13B4-04) yüzünden xfail olduğu için oradaki
    kanıt kırılsa bile sessiz kalırdı.
    """
    fazlar = _s2_faz_degerleri()
    olaylar = _s2_end_event_degerleri()
    assert fazlar >= {'two_phase', 'vapor'}, (
        f'tankın faz değerleri değişmiş: {sorted(fazlar)}')
    assert len(olaylar) >= 5, (
        f'end_event değer kümesi çıkarımı zayıfladı: {sorted(olaylar)}')
    assert not (fazlar & olaylar), (
        'end_event artık faz adı taşıyor — S2 izin gerekçesi güncellenmeli: '
        f'{sorted(fazlar & olaylar)}')
    uyarilar = _s2_faz_gecisi_uyarilari()
    assert any('TAIL-OFF' in u for u in uyarilar), (
        'faz geçişi artık model-sınırı uyarısı üretmiyor: kuyruk fazının '
        f'geçerlilik beyanı koptu ({uyarilar})')


#: Alan ADINDA faz kanalı arayan desenler. ``vapor_model_valid`` KASTEN
#: dışarıda: o P13B4-04'ün AYRI borcudur (hâlâ açık) ve bu deseni
#: kapatmamalıdır — iki borç birbirinin kapanışını taklit etmesin. Faz
#: borcu (OH-B4-04) D26'da ödendi; bu desen artık geri açılmayı ölçer.
_FAZ_KANALI_DESENLERI = ('phase', 'tail_off', 'vapor_transition')


def test_s2_faz_kanali_alan_olarak_yayimlaniyor():
    """Faz bilgisi yayımlanan blokta ALAN olarak var mı?

    ÖH D26 / OH-B4-04 — BORÇ İMİ KALDIRILDI. İm şunu diyordu: "tank adım
    durumundaki `phase` (two_phase | vapor) hibrit blowdown bloğunun 36
    anahtarının HİÇBİRİNDE alan olarak yayımlanmıyor; bilgi yalnız geçiş
    anında bir uyarı METNİ olarak sızıyor (IDEAL-GAS TAIL-OFF)".

    ÖLÇÜLDÜ (``docs/scofield/raw/OH/D26/hibrit/a1/once.json``): 36 anahtar,
    faz deseni eşleşen alan sayısı **0**; çözücünün (``TransientBallistics.
    solve``) dönüşünde de faz anahtarı yoktu, oysa döngü yanmayı tam olarak
    ``tank.phase == 'vapor'`` okumasıyla bitiriyordu. SONRA (``sonra.json``):
    40 anahtar, faz alanları ``tank_phase`` / ``tank_phase_final`` /
    ``tank_phase_basis`` (+ ``vapor_onset_s`` geçiş anı).

    Bekçi artık VARLIKLA yetinmez: kanalın DEĞER taşıdığını, zaman ekseniyle
    hizalı olduğunu ve ``end_event`` ile tutarlı olduğunu da ölçer — boş bir
    liste ya da künye-metni tek başına borcu ödemez.
    """
    blok = _s2_yayim_blok()
    kanallar = [ad for ad in blok
                if any(d in ad.lower() for d in _FAZ_KANALI_DESENLERI)]
    assert kanallar, (
        'blowdown bloğu faz kanalı yayımlamıyor — kuyruk fazı yalnız '
        f'uyarı metninde görünüyor (blok anahtarları: {sorted(blok)})')
    # Künye/gerekçe alanları TEK BAŞINA kanal sayılmaz: en az bir DEĞER
    # alanı olmak zorunda (adı '_basis' ile bitmeyen).
    deger_kanallari = [a for a in kanallar if not a.endswith('_basis')]
    assert deger_kanallari, (
        'faz deseniyle eşleşen tek alan bir künye metni — DEĞER kanalı yok: '
        f'{sorted(kanallar)}')


# ===========================================================================
# 4. S3 — fuel_thermal.ThermalProperty.as_dict (P13B4-05, P10 D-03)
# ===========================================================================

def _s3_ic_kayit():
    """İç nesne: ürünün KENDİ sınıfıyla kurulmuş bir termal özellik kaydı."""
    return fuel_thermal_mod.ThermalProperty(
        quantity='specific_heat',
        value=1500.0,
        phase='solid',
        reference_temperature_K=(293.0, 298.0),
        reference_basis=('bekçi fikstürü: kaydın referans koşulu kaydın '
                         'parçasıdır (karar 4)'),
        source='ÖH FAZ B-3 bekçi fikstürü')


def _s3_yayim_kapsami() -> Set[str]:
    """Yayımlanan gövde kapsamı: modülü İTHAL EDEN ürün dosyalarının anahtarları.

    Kapsam kasten tüketiciyle sınırlı: ``source`` gibi genel adlar depoda
    başka gövdelerde de geçiyor, ama o gövdeler bu kaydı yayımlamıyor.
    Tüketici yoksa yayımlanan gövde de yoktur.
    """
    return govde_anahtarlari(
        tuketici_dosyalari('hrma/stability/fuel_thermal.py', 'fuel_thermal'))


def test_s3_serilestirici_ic_nesneyi_tam_tasiyor():
    """Katman 1 (bugün SAĞLAM): __slots__ ⟷ as_dict tam eşlik.

    Bu iddia yeşil doğar ve S3'ün kusurunun serileştiricide DEĞİL onun
    üstünde olduğunu ölçüyle gösterir (P10 D-03 sınıfı).
    """
    kayit = _s3_ic_kayit()
    ic = {ad: getattr(kayit, ad)
          for ad in fuel_thermal_mod.ThermalProperty.__slots__}
    eslik_iddiasi('S3 ThermalProperty.__slots__ -> as_dict', ic,
                  kayit.as_dict())


@pytest.mark.xfail(strict=True, reason=(
    'ÖH defter P13B4-05 (+P10 D-03): hrma/stability/fuel_thermal.py\'nin '
    'ürün tüketicisi 0 — serileştirici kusursuz çalışıyor ama ürettiği '
    'gövde hiçbir yayımlanan gövdeye girmiyor; referans sıcaklık, '
    'referans dayanağı ve kaynak künyesi kullanıcıya HİÇ ulaşmıyor. '
    'Kayıt bir ürün gövdesine bağlanınca XPASS olur.'))
def test_s3_termal_kayit_yayimlanan_govdeye_ulasiyor():
    """as_dict ⟷ ürün gövdesi: kayıt yayımlanan bir gövdeye giriyor mu?"""
    kayit = _s3_ic_kayit()
    tuketiciler = tuketici_dosyalari(
        'hrma/stability/fuel_thermal.py', 'fuel_thermal')
    assert tuketiciler, (
        'hrma/ altında fuel_thermal modülünü ithal eden TEK ürün dosyası '
        'yok: yayımlanan gövde kümesi boş, dolayısıyla as_dict\'in ürettiği '
        'her alan (değer dahil) düşüyor')
    eslik_iddiasi('S3 as_dict -> ürün gövdesi', kayit.as_dict(),
                  _s3_yayim_kapsami())


def test_s3_kunye_alanlari_urun_govdelerinde_hic_gecmiyor():
    """Ölçüm çapası: karar-4 alanları ürün gövdelerinde 0 kez.

    ``reference_temperature_K`` ve ``reference_basis`` deponun HİÇBİR ürün
    sözlüğünde anahtar değil (``hrma/`` taraması). Onarım bu sayıyı
    kaçınılmaz olarak değiştirir; o gün bu iddia kırmızı verir ve bekçi
    "kayıt artık yayımlanıyor" haline taşınır.
    """
    bulgu = anahtar_gecisleri(
        ['reference_temperature_K', 'reference_basis'],
        haric=['hrma/stability/fuel_thermal.py'])
    assert bulgu['reference_temperature_K'] == [], bulgu
    assert bulgu['reference_basis'] == [], bulgu


# ===========================================================================
# 5. S4 — response.QSHODBand.as_dict (bugün SAĞLIKLI olan tek serileştirici)
# ===========================================================================

def _s4_band() -> QSHODBand:
    return QSHODBand(
        a_range=(6.0, 8.0), b_range=(0.5, 0.7), pressure_exponent_n=0.35,
        formulation_class='ÖH FAZ B-3 bekçi fikstürü',
        pressure_range_Pa=(1.0e6, 1.0e7),
        temperature_range_K=(290.0, 300.0),
        source='ÖH FAZ B-3 bekçi fikstürü (sentetik bant)')


#: Çalışma noktası + tek boyuna mod: ürünün KENDİ blok fonksiyonu bununla
#: koşturulur (``_pure_longitudinal_modes`` saf bir statik metottur).
_S4_OMEGA = 2.0 * 3.141592653589793 * 500.0
_S4_KAPPA = 1.5e-7
_S4_RB = 0.005
_S4_PC_BAR = 50.0
_S4_TC = 295.0


def _s4_blok(band: Optional[QSHODBand] = None) -> dict:
    """Yayımlanan gövde: SolidRocketEngine._qshod_band_block gerçek çıktısı."""
    motor = object.__new__(SolidRocketEngine)
    motor.combustion_response_band = band if band is not None else _s4_band()
    motor.propellant_thermal_diffusivity_m2_s = _S4_KAPPA
    motor.rho_p = 1750.0
    motor.T_c = _S4_TC
    motor.P_c = _S4_PC_BAR
    akustik = {'modes': [{'label': 'L1', 'frequency_hz': 500.0,
                          'indices': {'tangential_m': 0, 'radial_n': 0,
                                      'longitudinal_q': 1}}]}
    # ṙ_b = ṁ/(ρ_p·S_b) = 4.375/(1750·0.5) = 0.005 m/s (fikstür çapası).
    egri = {'burn_area': [0.5, 0.4], 'mass_flow': [4.375, 4.0]}
    blok = motor._qshod_band_block(akustik, egri)
    assert blok.get('status') == 'modelled', (
        f'S4 fikstürü bloğu değerlendiremedi: {blok}')
    return blok


def _kunye_kaniti(ic_anahtar: str, yayim_anahtar: str):
    """Künye metninin (yazar & yazar + yıl) yayımlanan metinde yaşadığını ölçer."""
    def kanit(ic: Mapping, yayim: Mapping) -> Tuple[bool, str]:
        kaynak = str(ic[ic_anahtar])
        hedef = str(yayim.get(yayim_anahtar, ''))
        yazarlar = set(re.findall(r'[A-Z][a-zA-Z]+ & [A-Z][a-zA-Z]+', kaynak))
        yillar = set(re.findall(r'\b(?:18|19|20)\d{2}\b', kaynak))
        eksik = sorted((yazarlar | yillar) - {k for k in (yazarlar | yillar)
                                              if k in hedef})
        if not (yazarlar and yillar):
            return False, (f'{ic_anahtar!r} metninden künye çıkarılamadı — '
                           f'kanıt kurulamıyor')
        if eksik:
            return False, (f'{yayim_anahtar!r} metni {ic_anahtar!r} '
                           f'künyesini taşımıyor; eksik: {eksik}')
        return True, ''
    return kanit


def test_s4_band_serilestiricisi_ic_nesneyi_tam_tasiyor():
    """Katman 1: QSHODBand.__slots__ ⟷ as_dict tam eşlik (bugün yeşil)."""
    band = _s4_band()
    ic = {ad: getattr(band, ad) for ad in QSHODBand.__slots__}
    eslik_iddiasi('S4 QSHODBand.__slots__ -> as_dict', ic, band.as_dict())


def test_s4_band_yayimlanan_govdede_tam_duruyor():
    """Katman 2: as_dict ⟷ katı motorun yayımladığı ``band`` alt gövdesi.

    Kampanyanın SAĞLIKLI deseni: zarf üstverisi (formülasyon sınıfı,
    basınç/sıcaklık aralığı, kaynak künyesi) uçtan uca taşınıyor. Bu iddia
    yeşil doğar; bir alan gövdeden düşerse KIRMIZI verir (mutasyonla
    kanıtlandı — bkz. paket raporu).
    """
    band = _s4_band()
    blok = _s4_blok(band)
    eslik_iddiasi('S4 as_dict -> _qshod_band_block["band"]',
                  band.as_dict(), blok['band'])
    for alan, deger in band.as_dict().items():
        assert blok['band'][alan] == deger, (
            f'{alan!r} yayımlanan gövdede DEĞİŞMİŞ: '
            f'{blok["band"][alan]!r} != {deger!r}')


def test_s4_mod_satiri_alan_esligi():
    """Çekirdek tepki sonucu ⟷ yayımlanan mod satırı (bugün yeşil).

    Kapsam kasten satır ∪ blok: bir alanın satırdan düşüp blok düzeyinde
    yaşaması meşru, ama GÖSTERİLMEK zorunda.
    """
    band = _s4_band()
    cekirdek = qshod_response_band(band, _S4_OMEGA, _S4_KAPPA, _S4_RB,
                                   _S4_PC_BAR * 1e5, _S4_TC)
    blok = _s4_blok(band)
    satir = blok['modes'][0]
    yayim = dict(blok)
    yayim.update(satir)
    izinler = (
        Izin(alan='basis',
             gerekce=('çekirdeğin künyesi mod satırı başına tekrarlanmıyor; '
                      'blok düzeyindeki _basis aynı künyeyi (yazar + yıl) '
                      'taşıyor — kanıtla ölçülüyor'),
             yasadigi_yer='_basis',
             kanit=_kunye_kaniti('basis', '_basis')),
    )
    eslik_iddiasi('S4 qshod_response_band -> mod satırı', cekirdek, yayim,
                  izinler)


def test_s4_kose_satiri_alan_esligi():
    """Köşe tepki sonucu ⟷ yayımlanan köşe satırı (bugün yeşil).

    Karmaşık sayılar (R_p ve λ) JSON gövdesine giremez; düşmelerine ancak
    bilginin gerçekten yaşadığı DEĞERLE gösterilirse izin verilir.
    """
    band = _s4_band()
    cekirdek = qshod_response(band.a_range[0], band.b_range[0],
                              band.pressure_exponent_n, _S4_OMEGA,
                              _S4_KAPPA, _S4_RB)
    blok = _s4_blok(band)
    satir = blok['modes'][0]
    kose = satir['corners'][0]
    yayim = dict(blok)
    yayim.update(satir)
    yayim.update(kose)

    def _karmasik_kaniti(ic: Mapping, yayim_govde: Mapping):
        r = ic['response']
        if (abs(yayim_govde['response_real'] - r.real) > 1e-12
                or abs(yayim_govde['response_imag'] - r.imag) > 1e-12):
            return False, ('karmaşık R_p\'nin gerçel/sanal parçaları '
                           'yayımlanan satırda birebir değil')
        return True, ''

    izinler = (
        Izin(alan='response',
             gerekce=('karmaşık R_p JSON gövdesinde taşınamaz; gerçel ve '
                      'sanal parçaları AYNEN yayımlanıyor (değerle '
                      'kanıtlanıyor)'),
             kanit=_karmasik_kaniti),
        Izin(alan='lambda',
             gerekce=('karmaşık λ ara değişkendir ve yayımlanan boyutsuz '
                      'frekans Ω\'dan ürünün kendi bağıntısıyla yeniden '
                      'türetilir; bağımsız bilgi taşımaz'),
             yasadigi_yer='omega_nondim'),
        Izin(alan='basis',
             gerekce=('köşe satırı künyeyi tekrarlamıyor; blok düzeyindeki '
                      '_basis aynı künyeyi (yazar + yıl) taşıyor — kanıtla '
                      'ölçülüyor'),
             yasadigi_yer='_basis',
             kanit=_kunye_kaniti('basis', '_basis')),
    )
    eslik_iddiasi('S4 qshod_response -> köşe satırı', cekirdek, yayim,
                  izinler)


# ===========================================================================
# 6. S5 — bands.QSHODBandRecord.as_dict (P13B4-03)
# ===========================================================================

def _s5_kayit():
    """İç nesne: katalogdaki GERÇEK kayıt (fikstür uydurulmuyor)."""
    dolu = [k for k in bands_mod.QSHOD_BAND_RECORDS.values()
            if isinstance(k, bands_mod.QSHODBandRecord)]
    assert dolu, 'bands.QSHOD_BAND_RECORDS içinde dolu kayıt kalmamış'
    return sorted(dolu, key=lambda k: k.record_id)[0]


def test_s5_kayit_serilestiricisi_ic_nesneyi_tam_tasiyor():
    """Katman 1 (bugün SAĞLAM): __slots__ ⟷ as_dict; ad değişimleri ispatlı."""
    kayit = _s5_kayit()
    ic = {ad: getattr(kayit, ad)
          for ad in bands_mod.QSHODBandRecord.__slots__}
    yayim = kayit.as_dict()
    izinler = (
        Izin(alan='confidence',
             gerekce=('serileştirici kayıt düzeyi olduğunu belli etmek için '
                      'record_ önekiyle yayımlıyor; DEĞER aynı, birebir '
                      'ölçülüyor'),
             yasadigi_yer='record_confidence', deger_esit=True),
        Izin(alan='confidence_note',
             gerekce=('aynı önek kuralı: kayıt düzeyi not record_confidence_'
                      'note adıyla yayımlanıyor; değer birebir ölçülüyor'),
             yasadigi_yer='record_confidence_note', deger_esit=True),
        Izin(alan='band',
             gerekce=('bant nesnesi gövdeye kendi as_dict\'iyle giriyor; '
                      'zarf üstverisi orada tam olarak yayımlanıyor'),
             yasadigi_yer='band'),
    )
    eslik_iddiasi('S5 QSHODBandRecord.__slots__ -> as_dict', ic, yayim,
                  izinler)
    assert yayim['band'] == kayit.band.as_dict()


def _kunye_yollari(govde: Any, ad: str) -> Tuple[str, ...]:
    """``ad``ın gövdede ANAHTAR olarak geçtiği yolları döndürür."""
    bulunan = []

    def gez(dugum, p):
        if isinstance(dugum, Mapping):
            for k, v in dugum.items():
                if k == ad:
                    bulunan.append(f'{p}.{k}')
                gez(v, f'{p}.{k}')
        elif isinstance(dugum, (list, tuple)):
            for i, v in enumerate(dugum):
                gez(v, f'{p}[{i}]')

    gez(govde, '')
    return tuple(bulunan)


def _yoldaki_deger(govde: Any, yol: str) -> Any:
    """``_kunye_yollari``ın ürettiği '.a.b[0].c' yolunu izler."""
    dugum, parca, i = govde, '', 0
    while i < len(yol):
        ch = yol[i]
        if ch == '.':
            if parca:
                dugum = dugum[parca]
            parca = ''
        elif ch == '[':
            if parca:
                dugum, parca = dugum[parca], ''
            j = yol.index(']', i)
            dugum = dugum[int(yol[i + 1:j])]
            i = j
        else:
            parca += ch
        i += 1
    return dugum[parca] if parca else dugum


def _kayit_kunyesi_kaniti(alan: str):
    """Künye alanının ``band_source.record`` altında AYNEN yaşadığı kanıtı.

    ``Izin``in kanıt sözleşmesi: alan yayımlanan gövdenin ÜST düzeyinde
    yoksa, başka bir kanalda yaşadığı DEĞERLE gösterilmelidir. Burada
    gösterilen kanal kaydın kendi künye zarfıdır.
    """
    def kanit(ic: Mapping, yayim: Mapping) -> Tuple[bool, str]:
        kaynak = yayim.get('band_source')
        if not isinstance(kaynak, Mapping):
            return False, 'band_source yayımlanan gövdede sözlük değil'
        kayit = kaynak.get('record')
        if not isinstance(kayit, Mapping):
            return False, ('band_source.record YOK — kaydın künye zarfı '
                           'yayımlanan gövdeye hiç girmiyor')
        if alan not in kayit:
            return False, f'band_source.record içinde {alan!r} anahtarı yok'
        if kayit[alan] != ic[alan]:
            return False, (f'band_source.record.{alan} değeri kaymış: '
                           f'{kayit[alan]!r} != {ic[alan]!r}')
        return True, ''
    return kanit


#: Künye zarfının izin gerekçesi — dördü de aynı kanalda yaşar.
_S5_KUNYE_GEREKCESI = (
    'kayıt düzeyi künye bloğun ÜST düzeyine çıkarılmaz: orada zaten mod '
    'başına bir ``confidence`` (zarf rozeti) yayımlanıyor ve iki AYRI güven '
    'ekseni kardeş anahtar olarak durursa okuyucu kaydın güvenini sonucun '
    'güveni sanar. Künye, bandın nereden geldiğini söyleyen kanalda — '
    '``band_source.record`` — tam olarak ve AYNI DEĞERLE yayımlanır; '
    'kanıt bunu ölçer.')


# ÖH D27 / kati a2 — P13B4-03 BORÇ İMİ KALDIRILDI (ürün onarımı bu dalgada).
# İm şunu diyordu: "kaydın künye zarfı hiçbir ürün gövdesine girmiyor;
# bandı yayımlayan TEK ürün yolu ÇIPLAK bir QSHODBand yayımlıyor".
# ÖLÇÜLDÜ (docs/scofield/raw/OH/D27/kati/a2/once.json K1, taban 709a235e):
# imin İDDİASI BUGÜN İKİYE AYRILIYOR —
#   * KATALOG yolunda (motor bandı kendi yakıtından çözüyor) künye zaten
#     yayımlanıyordu: 4/4 alan, ``band_source.record`` altında. Bunu D22
#     (P6B4-08) bağlamıştı, yani imin "hiçbir gövdeye girmiyor" cümlesi
#     P13 ölçümünden BU YANA bayatlamıştı;
#   * ÇAĞIRAN bandı elden verdiğinde (bu bekçinin fikstür yolu) 0/4 idi —
#     üstelik verilen band KATALOĞUN KENDİ kaydının bandı olsa bile.
# Onarım ikinci yarıyı kapattı (solid_rocket_engine._qshod_record_for_band
# + _qshod_band_block çağıran dalı): 0/4 -> 4/4, değerler birebir eşit
# (sonra.json K1a). İddia artık İZİN + KANIT ile yeşil koşar: alanın
# düşmesine izin verilir, ama yaşadığı kanalda AYNI DEĞERLE durduğu
# ölçülür — kanıt tutmazsa bekçi kırmızıya döner.
def test_s5_kayit_kunyesi_yayimlanan_govdede():
    """as_dict ⟷ bandı yayımlayan TEK ürün gövdesi (katı motor bloğu)."""
    kayit = _s5_kayit()
    blok = _s4_blok(kayit.band)
    izinler = (
        Izin(alan='band',
             gerekce=('bant alt gövdesi blokta aynı adla yayımlanıyor; zarf '
                      'üstverisi orada tam duruyor (S4 bekçisi ölçüyor)'),
             yasadigi_yer='band'),
    ) + tuple(
        Izin(alan=ad, gerekce=_S5_KUNYE_GEREKCESI,
             yasadigi_yer='band_source', kanit=_kayit_kunyesi_kaniti(ad))
        for ad in ('record_id', 'record_confidence',
                   'record_confidence_note', 'retrieved'))
    eslik_iddiasi('S5 as_dict -> _qshod_band_block', kayit.as_dict(), blok,
                  izinler)


# ÖH D27 / kati a2 — P13B4-03'ün İKİNCİ borç imi de kaldırıldı, ama ÖLÇÜM
# DEĞİŞTİRİLDİ ve bu bilerek yapıldı. Eski iddia, künye adlarının ``hrma/``
# altında KAYNAK METNİNDE sözlük anahtarı olup olmadığına bakıyordu (AST
# taraması). O bir VEKİL ölçüttü ve onarımın doğru biçimini cezalandırıyor:
# ürün künyeyi ``QSHODBandRecord.as_dict()``ten OLDUĞU GİBİ taşır (tek
# kaynak, Doktrin 4); adları ikinci kez elle yazmak bu ölçütü yeşile
# çevirirdi ama serileştiriciyi İKİ yerde tanımlamak olurdu — yani vekil
# ölçüt, deponun kendi kuralıyla çelişiyordu. ÖLÇÜLDÜ: onarımdan SONRA da
# AST sayacı 0 (once/sonra.json K1c), buna karşılık künye yayımlanan
# gövdede 4/4 (K1a). Testin KENDİ docstring'i zaten "ürünün YAYIMLADIĞI
# gövdelerde" diyordu; iddia o cümleye çekildi ve GÜÇLENDİ: artık yalnız
# adın varlığı değil, DEĞERİN kaydınkiyle aynı olduğu da çakılıyor.
# Kaynak taraması kaybolmadı — kırmızı mesajına bağlam olarak basılır.
def test_s5_kunye_alanlari_urun_govdelerinde_yayimlaniyor():
    """Künye alanları ürünün yayımladığı gövdelerde anahtar olarak geçiyor mu?"""
    kayit = _s5_kayit()
    kunye = [a for a in kayit.as_dict() if a != 'band']
    blok = _s4_blok(kayit.band)
    bulgu = {a: _kunye_yollari(blok, a) for a in kunye}
    kaynak_sayaci = anahtar_gecisleri(kunye, haric=['hrma/stability/bands.py'])
    bos = sorted(a for a, yerler in bulgu.items() if not yerler)
    assert not bos, (
        'kayıt künyesinin şu alanları ürünün YAYIMLADIĞI gövdede anahtar '
        f'değil: {bos}\n  yayım ölçümü: '
        + '; '.join(f'{a}={len(y)}' for a, y in sorted(bulgu.items()))
        + '\n  (bağlam) kaynak taraması: '
        + '; '.join(f'{a}={len(y)}' for a, y in sorted(kaynak_sayaci.items())))
    beklenen = kayit.as_dict()
    for ad in kunye:
        for yol in bulgu[ad]:
            assert _yoldaki_deger(blok, yol) == beklenen[ad], (
                f'{yol} kaydın değerini taşımıyor: '
                f'{_yoldaki_deger(blok, yol)!r} != {beklenen[ad]!r}')


# ===========================================================================
# 7. İZİN LİSTELERİNİN KENDİ BEKÇİSİ (xfail'lerin altında sessizce çürümesin)
# ===========================================================================

def test_izin_listeleri_urun_envanterinden_sapmamis():
    """xfail'li iddiaların izin listeleri ürünle uyumlu mu?

    Gerekçe: S1 ve S2 iddiaları bugün ``xfail`` — yani onların İÇİNDEKİ
    izin denetimi kırmızı olsa GÖRÜNMEZDİ (xfail her sebeple düşen testi
    yutar). Bu YEŞİL iddia o iki izin listesini ayrıca koşar: bir alan
    üründen kalkarsa, gerekçe silinirse, dürüstlük alanı kanıtsız izinliye
    çevrilirse ya da gösterilen yaşam yeri gövdeden kalkarsa burada
    kırmızı verir. (S3/S4/S5 izin listeleri zaten yeşil iddiaların içinde
    koşuyor.)
    """
    hatalar = []
    hatalar += list(izin_denetimi(
        'S1', _s1_ic_hucre(), _flatten_cell(_s1_ic_hucre(), 'main'),
        S1_IZINLER))
    hatalar += list(izin_denetimi(
        'S2', _s2_ic_durum(), _s2_yayim_blok(), S2_IZINLER))
    assert not hatalar, 'izin listeleri sözleşmeyi çiğniyor:\n  ' + '\n  '.join(
        hatalar)
