param()

$ErrorActionPreference = "Stop"
$taskName = "mzShop win-acme 自动续期"
$wacsExe = "E:\httpserver\win-acme\wacs.exe"
$letsEncrypt = "https://acme-v02.api.letsencrypt.org/directory"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)) {
    $elevatedArgs = "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$PSCommandPath`""
    Start-Process -FilePath "powershell.exe" -ArgumentList $elevatedArgs -Verb RunAs -WindowStyle Normal
    exit
}
if (-not (Test-Path -LiteralPath $wacsExe)) {
    throw "win-acme 不存在：$wacsExe"
}

$action = New-ScheduledTaskAction -Execute $wacsExe -Argument "--renew --baseuri `"$letsEncrypt`" --closeonfinish" -WorkingDirectory (Split-Path $wacsExe)
$trigger = New-ScheduledTaskTrigger -Daily -At "09:00"
$trigger.RandomDelay = "PT4H"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "mzShop 的 Let’s Encrypt 证书自动续期；成功后由 win-acme 调用部署脚本重载 Apache。" -Force | Out-Null

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
Write-Host "续期任务已创建：$($task.TaskName)（状态：$($task.State)）" -ForegroundColor Green
