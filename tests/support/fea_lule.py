"""V301/PANEL (NK-12) — termal FEA ağının malzemesi (test kurgusu için).

Termal alan YALNIZ lüledir (``extract_thermal_inputs`` include_chamber =
False); köprü lüle cidarını motorun YAYIMLADIĞI lüle malzemesiyle çözer
(``hrma.fea.bridge.NOZZLE_MATERIAL_PATHS``). Zincirin iki ucu aynı malzemeyi
kullanmak zorunda olduğundan (P7B3-30 kapısı) profil de bu malzemeyle
istenir. Okuyucu köprünün KENDİSİDİR; testte ikinci bir kural yazılmaz.
"""
from hrma.fea.bridge import _lule_malzemesi


def ag_malzemesi(motor, kamara_malzemesi):
    """Termal ağın malzemesi: lüle malzemesi varsa o, yoksa kamaranınki."""
    lule = _lule_malzemesi(motor)
    return lule[0] if lule else kamara_malzemesi
