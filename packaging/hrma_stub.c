/* HRMA .app arm64 başlatıcı stub'ı (2026-07-13).
 *
 * Ana çalıştırılabilir bash script'i olunca macOS mimariyi belirleyemiyor
 * ve "Intel için üretilmiş / Rosetta desteği sona eriyor" uyarısı basıyordu.
 * Bu gerçek arm64 Mach-O binary'si yalnızca yanındaki hrma_baslat.sh'ı
 * çalıştırır — bütün başlatma mantığı script'te kalır.
 */
#include <mach-o/dyld.h>
#include <libgen.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(void) {
    char exe[PATH_MAX];
    uint32_t sz = sizeof(exe);
    if (_NSGetExecutablePath(exe, &sz) != 0)
        return 1;
    char real[PATH_MAX];
    if (!realpath(exe, real))
        return 1;
    char *dir = dirname(real); /* .../HRMA.app/Contents/MacOS */
    char script[PATH_MAX];
    snprintf(script, sizeof(script), "%s/hrma_baslat.sh", dir);
    execl("/bin/bash", "/bin/bash", script, (char *)NULL);
    perror("HRMA baslatilamadi");
    return 1;
}
