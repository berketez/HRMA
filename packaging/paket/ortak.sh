# packaging/paket/ortak.sh — mac.sh ve win.sh'in ortak ön denetimi (kaynak olarak okunur).
#
# 3.0.6 yayın günü (10 Kas) paket worktree'si ayrık HEAD'deydi; yayın kapısı 2/10
# ("üst akış dalı yok — push edilmemiş") paketler ~10 dk derlendikten SONRA kapandı.
# Kapı 2/10'un istediği üç şart burada derlemeden ÖNCE ölçülür:
#   - HEAD bir dalda (ayrık değil) ve dalın üst akışı var,
#   - HEAD == @{u} (yayınlanacak commit uzakta, CI onu koşturmuş olabilir),
#   - çalışma ağacı temiz (kirli ağaçtan derlenen paket BUILD_INFO'da kirli görünür).
# Paket ağacı aday dalında durur:  git -C <paket-worktree> switch aday/vX.Y.Z-rc.N
# (packaging/aday_uret.sh --push dalın üst akışını ayarlar).
paket_agaci_denetle() {
    local dal yerel uzak
    dal="$(git symbolic-ref -q --short HEAD || true)"
    if [ -z "$dal" ]; then
        echo "PAKET AĞACI: HEAD ayrık — kapı 2/10 üst akışlı dal ister. 'git switch aday/vX.Y.Z-rc.N' ile dala geçin."
        return 1
    fi
    if ! uzak="$(git rev-parse -q --verify '@{u}' 2>/dev/null)"; then
        echo "PAKET AĞACI: '$dal' dalının üst akışı yok — önce 'git push -u origin $dal' (aday_uret.sh --push)."
        return 1
    fi
    yerel="$(git rev-parse HEAD)"
    if [ "$yerel" != "$uzak" ]; then
        echo "PAKET AĞACI: HEAD ${yerel:0:12} üst akıştan (${uzak:0:12}) farklı — push edilmemiş ya da geride."
        return 1
    fi
    if [ -n "$(git status --porcelain)" ]; then
        echo "PAKET AĞACI: çalışma ağacı kirli — kirli ağaçtan paket derlenmez."
        return 1
    fi
    echo "paket ağacı: $dal @ ${yerel:0:12} (üst akışla aynı, temiz)"
    return 0
}
