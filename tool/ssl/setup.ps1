param()

$ErrorActionPreference = "Stop"

$domain = "admin.monozex.com"
$publicBaseUrl = "https://admin.monozex.com:10086"
$wacsExe = "E:\httpserver\win-acme\wacs.exe"
$certRoot = "E:\httpserver\certs\mzshop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$deployScript = Join-Path $projectRoot "tool\ssl\deploy.ps1"
$renewalTaskScript = Join-Path $projectRoot "tool\ssl\setup-renewal-task.ps1"
$letsEncrypt = "https://acme-v02.api.letsencrypt.org/directory"
$apiIdVault = "vault://json/mzshop-aliyun-id"
$apiSecretVault = "vault://json/mzshop-aliyun-secret"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)) {
    $elevatedArgs = "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$PSCommandPath`""
    Start-Process -FilePath "powershell.exe" -ArgumentList $elevatedArgs -Verb RunAs -WindowStyle Normal
    exit
}
foreach ($path in @($wacsExe, $deployScript, $renewalTaskScript)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "所需文件不存在：$path"
    }
}
New-Item -ItemType Directory -Path $certRoot -Force | Out-Null

Write-Host "将为 $domain 配置 Let’s Encrypt DNS-01 自动签发。"
Write-Host "阿里云 RAM 用户只需云解析 DNS 的记录查询和修改权限；凭据不会写入项目。"
$apiId = (Read-Host "阿里云 AccessKey ID").Trim()
$secureSecret = Read-Host "阿里云 AccessKey Secret" -AsSecureString
$email = (Read-Host "Let’s Encrypt 到期通知邮箱").Trim()
if (-not $apiId -or -not $email -or $secureSecret.Length -eq 0) {
    throw "AccessKey ID、Secret 和通知邮箱都不能为空。"
}

$secretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSecret)
try {
    $apiSecret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPtr)

    & $wacsExe --baseuri $letsEncrypt --vaultstore --vaultkey $apiIdVault --vaultsecret $apiId --closeonfinish
    if ($LASTEXITCODE -ne 0) { throw "保存 AccessKey ID 失败。" }
    & $wacsExe --baseuri $letsEncrypt --vaultstore --vaultkey $apiSecretVault --vaultsecret $apiSecret --closeonfinish
    if ($LASTEXITCODE -ne 0) { throw "保存 AccessKey Secret 失败。" }

    $wacsArgs = @(
        '--baseuri', $letsEncrypt,
        '--source', 'manual',
        '--host', $domain,
        '--friendlyname', 'mzShop admin.monozex.com',
        '--validationmode', 'dns-01',
        '--validation', 'aliyun',
        '--aliyunapiid', $apiIdVault,
        '--aliyunapisecret', $apiSecretVault,
        '--csr', 'ec',
        '--store', 'pemfiles',
        '--pemfilespath', $certRoot,
        '--pemfilesname', $domain,
        '--installation', 'script',
        '--script', $deployScript,
        '--scriptparameters', "-CertCommonName '$domain'",
        '--emailaddress', $email,
        '--accepttos',
        '--setuptaskscheduler',
        '--closeonfinish'
    )
    & $wacsExe @wacsArgs
    if ($LASTEXITCODE -ne 0) { throw "证书申请失败，请查看上方 win-acme 错误。" }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $renewalTaskScript
    if ($LASTEXITCODE -ne 0) { throw "自动续期任务创建失败。" }
} finally {
    if ($secretPtr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPtr)
    }
    $apiSecret = $null
    $secureSecret.Dispose()
}

Write-Host "自动签发、部署和续期已配置：$publicBaseUrl" -ForegroundColor Green
