# 压缩 Docker Desktop 的 WSL 虚拟磁盘,把已清理的空间还给宿主盘
Stop-Process -Name 'Docker Desktop', 'com.docker.backend', 'com.docker.build' -Force -ErrorAction SilentlyContinue
wsl --shutdown
Start-Sleep -Seconds 5

$vhdx = 'D:\DockerData\DockerDesktopWSL\disk\docker_data.vhdx'
$before = [math]::Round((Get-Item $vhdx).Length / 1GB, 2)
Write-Output "压缩前 vhdx: $before GB"

$ok = $false
try {
    Optimize-VHD -Path $vhdx -Mode Full -ErrorAction Stop
    $ok = $true
    Write-Output 'Optimize-VHD 成功'
} catch {
    Write-Output "Optimize-VHD 不可用: $($_.Exception.Message.Split([char]10)[0])"
}

if (-not $ok) {
    # diskpart 兜底(同样需要管理员)
    $script = "select vdisk file=`"$vhdx`"`nattach vdisk readonly`ncompact vdisk`ndetach vdisk`n"
    $tmp = "$env:TEMP\compact_vhdx.txt"
    $script | Out-File -FilePath $tmp -Encoding ascii
    diskpart /s $tmp
}

$after = [math]::Round((Get-Item $vhdx).Length / 1GB, 2)
Write-Output "压缩后 vhdx: $after GB(归还 $($before - $after) GB)"
Get-PSDrive D | ForEach-Object { Write-Output ("D 盘剩余: " + [math]::Round($_.Free / 1GB, 1) + " GB") }
