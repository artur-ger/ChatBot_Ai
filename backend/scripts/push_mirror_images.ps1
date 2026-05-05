<#
.SYNOPSIS
  Скачивает postgres/redis/chroma с Docker Hub и пушит копии в ваш registry (например Yandex CR).

.PARAMETER RegistryPrefix
  Адрес реестра + id без завершающего слэша. В Yandex CR: cr.yandex.net/<registry-id>
  В консоли Yandex создай пустые Docker-репозитории: postgres, redis, chroma (имена должны совпасть).

.EXAMPLE
  .\scripts\push_mirror_images.ps1 -RegistryPrefix "cr.yandex.net/crpg06m95ia30f7q8f5a"
#>
param(
    [Parameter(Mandatory = $true)]
    [string] $RegistryPrefix
)

$RegistryPrefix = $RegistryPrefix.TrimEnd("/")

$pairs = @(
    @{ Src = "postgres:15-alpine"; Dst = "$RegistryPrefix/postgres:15-alpine" },
    @{ Src = "redis:7-alpine"; Dst = "$RegistryPrefix/redis:7-alpine" },
    @{ Src = "chromadb/chroma:1.5.8"; Dst = "$RegistryPrefix/chroma:1.5.8" }
)

foreach ($p in $pairs) {
    Write-Host ">>> pull $($p.Src)"
    docker pull $p.Src
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host ">>> tag $($p.Dst)"
    docker tag $p.Src $p.Dst
    Write-Host ">>> push $($p.Dst)"
    docker push $p.Dst
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Done. Добавь в backend/.env (файл рядом с docker-compose.yml — compose подхватит переменные):"
Write-Host "POSTGRES_IMAGE=$RegistryPrefix/postgres:15-alpine"
Write-Host "REDIS_IMAGE=$RegistryPrefix/redis:7-alpine"
Write-Host "CHROMA_IMAGE=$RegistryPrefix/chroma:1.5.8"
