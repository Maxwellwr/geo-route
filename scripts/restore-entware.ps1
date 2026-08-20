# Восстановление только Entware на Netcraze Ultra (192.168.117.1)
# Usage: .\restore-entware.ps1 [-RouterHost 192.168.117.1] [-BackupDir ..\backup\netcraze-ultra]

param(
    [string]$RouterHost = "192.168.117.1",
    [string]$BackupDir = (Join-Path $PSScriptRoot "..\backup\netcraze-ultra"),
    [string]$SshUser = "root"
)

$ErrorActionPreference = "Stop"
$sshTarget = "${SshUser}@${RouterHost}"
$remoteDir = "/tmp/entware-restore"

$required = @(
    "entware-etc-backup.tar.gz",
    "opt-root-backup.tar.gz",
    "installed_packages.txt",
    "restore-entware-remote.sh"
)

foreach ($name in $required) {
    $path = Join-Path $BackupDir $name
    if (-not (Test-Path $path)) {
        Write-Error "Не найден: $path"
    }
}

function Copy-ToRouter {
    param([string]$LocalPath, [string]$RemotePath)
    # Dropbear на Netcraze не имеет sftp-server — нужен legacy scp (-O)
    scp -O -o BatchMode=yes $LocalPath "${sshTarget}:${RemotePath}"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "scp не удался: $LocalPath -> $RemotePath"
    }
}

Write-Host "Проверка SSH: $sshTarget ..."
ssh -o BatchMode=yes -o ConnectTimeout=10 $sshTarget @"
if [ -d /opt/bin ]; then echo 'OK: /opt смонтирован'; else
  echo 'WARN: /opt нет — сначала в веб-UI: USB-диск + компонент OPKG + привязка раздела Entware';
  exit 1;
fi
"@

Write-Host "Подготовка $remoteDir ..."
ssh $sshTarget "mkdir -p $remoteDir && rm -f $remoteDir/*"

Write-Host "Загрузка файлов (scp -O) ..."
foreach ($name in $required) {
    $local = Join-Path $BackupDir $name
    Write-Host "  $name"
    Copy-ToRouter $local "$remoteDir/$name"
}

ssh $sshTarget "chmod +x $remoteDir/restore-entware-remote.sh"

Write-Host "Запуск восстановления (10–30 мин.) ..."
ssh -t $sshTarget "sh $remoteDir/restore-entware-remote.sh"

Write-Host ""
Write-Host "Готово. Проверка:"
Write-Host "  ssh $sshTarget '/opt/bin/opkg list-installed | wc -l'"
Write-Host "  ssh $sshTarget 'ls /opt/etc/init.d/'"
