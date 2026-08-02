"""Dışa aktarım üreticileri için istek başına yalıtılmış geçici çalışma alanı.

Neden bu modül var — ÖLÇÜLEN iki kusur (Faz 4B, D1 ve D10):

**D1 — eşzamanlı export'lar birbirinin dosyasını veriyordu.** Üreticiler çıktı
yolunu ZAMAN DAMGASINDAN kuruyordu: ``drawing_generator`` gün çözünürlüklü
(``{ad}_profile_20260802.dxf``), ``step_export`` saniye çözünürlüklü
(``hrma_step_20260802_031505/``) ad üretiyor, ikisi de ``exist_ok=True`` ile
aynı dizini paylaşıyordu. Aynı motor adıyla gelen iki istek AYNI dosyaya
yazıyor, biri diğerinin yazması bitmeden dosyayı okuyup gönderiyordu.
Ölçüldü: 8 eşzamanlı ``/api/export-dxf`` isteğinde aynı geometriyi isteyen 4
istemcinin hiçbiri kendi dosyasını almadı; bir istemci 32796 baytlık YARIM
DXF'i HTTP 200 ile indirdi. Üretimde sunucu waitress ``threads=8`` ile koşar
(``packaging/launcher.py``), yani bu teorik bir yarış değil.

Çözüm iki parçalı:
  1. :func:`new_workspace` — her iş kendi ``mkdtemp`` dizinini alır. Zaman
     damgası değil, işletim sisteminin ürettiği benzersiz ad kullanılır.
  2. :func:`atomic_write` / :func:`atomic_produce` — dosya önce aynı dizinde
     geçici adla yazılır, sonra ``os.replace`` ile hedefe taşınır. Böylece
     bir okuyucu YA eski tam dosyayı YA yeni tam dosyayı görür; yarım dosya
     asla görünmez (POSIX rename atomiktir).

**D10 — /tmp birikmesi.** Ölçüldü: 77 dizin / 17 MB birikmiş, hiçbir temizlik
yolu yok. :func:`cleanup_workspace` işi biten dizini siler;
:func:`purge_stale_workspaces` çökme sonrası kalanları yaş sınırıyla toplar.
Temizleyici YALNIZ bu modülün açtığı önek desenine (``HRMA_TEMP_PREFIXES``)
uyan dizinlere dokunur — kullanıcının başka dosyaları asla silinmez.
"""

import os
import shutil
import tempfile
import time

#: Bu projenin ürettiği geçici dizin önekleri. Temizleyici SADECE bu öneklerle
#: başlayan dizinleri siler; başka bir şey silmesi hata sayılır (bkz.
#: tests/test_faz4_export_geometri.py).
HRMA_TEMP_PREFIXES = (
    'hrma_step_', 'hrma_tank_step_', 'hrma_dxf_', 'hrma_drawings_',
    'hrma_stl_', 'hrma_cad_', 'tank_cad_',
)

#: Çökme sonrası kalan dizinlerin silinmeden önce bekletildiği süre (saniye).
#: 24 saat: aynı anda koşan uzun bir işin dizinini silmemek için geniş pay.
STALE_WORKSPACE_MAX_AGE_S = 24 * 3600


def new_workspace(prefix):
    """İstek başına benzersiz, boş bir geçici dizin açar ve yolunu döndürür.

    ``prefix`` :data:`HRMA_TEMP_PREFIXES` içinde olmalıdır — temizleyici
    yalnız o önekleri tanır, listede olmayan bir önek sessizce birikirdi.
    """
    if prefix not in HRMA_TEMP_PREFIXES:
        raise ValueError(
            f'{prefix!r} HRMA_TEMP_PREFIXES icinde degil; temizleyici bu '
            'dizinleri tanimaz ve /tmp yeniden birikir')
    return tempfile.mkdtemp(prefix=prefix)


def cleanup_workspace(path):
    """:func:`new_workspace` ile açılmış bir dizini siler (sessiz, güvenli).

    Yalnız tanınan önekle başlayan dizinler silinir. Dönüş: silindi mi (bool).
    """
    if not path or not os.path.isdir(path):
        return False
    if not os.path.basename(os.path.normpath(path)).startswith(
            HRMA_TEMP_PREFIXES):
        return False
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.isdir(path)


def purge_stale_workspaces(max_age_s=STALE_WORKSPACE_MAX_AGE_S, root=None):
    """Çökme/kill sonrası kalan eski HRMA geçici dizinlerini toplar.

    Yalnız :data:`HRMA_TEMP_PREFIXES` öneklerine uyan ve ``max_age_s``
    saniyeden eski dizinler silinir. Kullanıcının başka dosyalarına
    DOKUNULMAZ. Dönüş: silinen dizin yollarının listesi.
    """
    root = root or tempfile.gettempdir()
    removed = []
    now = time.time()
    try:
        names = os.listdir(root)
    except OSError:
        return removed
    for name in names:
        if not name.startswith(HRMA_TEMP_PREFIXES):
            continue
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age < max_age_s:
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.isdir(path):
            removed.append(path)
    return removed


def atomic_write(path, data, mode='wb'):
    """``data``yı ``path``e ATOMİK yazar (geçici ad + ``os.replace``).

    Yarım dosyanın okunmasını engeller — D1'in "32796 baytlık kesik DXF"
    belirtisi tam olarak buydu.
    """
    directory = os.path.dirname(os.path.abspath(path)) or '.'
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix='.hrma_tmp_')
    try:
        with os.fdopen(fd, mode) as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def atomic_produce(path, writer):
    """``writer(gecici_yol)`` ile üretilen dosyayı ATOMİK olarak yerine koyar.

    Üretici kütüphaneler (ezdxf ``saveas``, reportlab ``Canvas``, build123d
    ``export_step``) yolu kendileri açtığı için baytları elimize almıyoruz;
    onlara aynı dizinde geçici bir yol veririz, iş bitince ``os.replace``
    hedefe taşır. Yazma yarıda kalırsa hedef dosya HİÇ oluşmaz — kullanıcı
    yarım dosya indirmez, hata görür.
    """
    directory = os.path.dirname(os.path.abspath(path)) or '.'
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix='.hrma_tmp_',
                               suffix=os.path.splitext(path)[1])
    os.close(fd)
    try:
        writer(tmp)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path
