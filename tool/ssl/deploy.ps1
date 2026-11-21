param(
    [string]$CertCommonName = "admin.monozex.com"
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$apacheRoot = "E:\httpserver\apache24-php8"
$apacheConf = Join-Path $apacheRoot "conf\httpd.conf"
$vhostConf = Join-Path $apacheRoot "conf\extra\mzshop-admin.conf"
$httpdExe = Join-Path $apacheRoot "bin\httpd.exe"
$certRoot = "E:\httpserver\certs\mzshop"
$certChain = Join-Path $certRoot "$CertCommonName-chain.pem"
$certKey = Join-Path $certRoot "$CertCommonName-key.pem"
$restartScript = Join-Path $projectRoot "tool\admin\restart.ps1"
$envFile = Join-Path $projectRoot "admin\.env"
$publicBaseUrl = "https://admin.monozex.com:10086"

foreach ($path in @($apacheConf, $httpdExe, $certChain, $certKey, $restartScript, $envFile)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "部署所需文件不存在：$path"
    }
}

function Save-Utf8NoBom([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

# 只在首次部署时启用 Apache 反向代理模块并加入项目专用配置。
$confText = [System.IO.File]::ReadAllText($apacheConf)
$originalConf = $confText
$confText = $confText -replace '(?m)^\s*#\s*(LoadModule\s+proxy_module\s+modules/mod_proxy\.so)\s*$', '$1'
$confText = $confText -replace '(?m)^\s*#\s*(LoadModule\s+proxy_http_module\s+modules/mod_proxy_http\.so)\s*$', '$1'
$confText = $confText -replace '(?m)^\s*#\s*(LoadModule\s+headers_module\s+modules/mod_headers\.so)\s*$', '$1'
if ($confText -notmatch '(?m)^\s*Listen\s+8000\s*$') {
    $confText += "`r`nListen 8000`r`n"
}
if ($confText -notmatch '(?m)^\s*IncludeOptional\s+conf/extra/mzshop-admin\.conf\s*$') {
    $confText += "IncludeOptional conf/extra/mzshop-admin.conf`r`n"
}
if ($confText -ne $originalConf) {
    $backup = "$apacheConf.mzshop-backup"
    if (-not (Test-Path -LiteralPath $backup)) {
        Copy-Item -LiteralPath $apacheConf -Destination $backup
    }
    Save-Utf8NoBom $apacheConf $confText
}

$chainPath = $certChain.Replace('\', '/')
$keyPath = $certKey.Replace('\', '/')
$vhost = @"
# mzShop 管理后台：公网 10086 转发到本机 TLS 8000，应用仅监听 127.0.0.1:8001。
<VirtualHost *:8000>
    ServerName admin.monozex.com
    SSLEngine on
    SSLProtocol all -SSLv2 -SSLv3 -TLSv1 -TLSv1.1
    SSLCertificateFile "$chainPath"
    SSLCertificateKeyFile "$keyPath"

    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
    RequestHeader set X-Forwarded-Port "10086"
    ProxyPass / http://127.0.0.1:8001/ connectiontimeout=5 timeout=120
    ProxyPassReverse / http://127.0.0.1:8001/

    ErrorLog "logs/mzshop-admin-error.log"
    CustomLog "logs/mzshop-admin-access.log" common
</VirtualHost>
"@
Save-Utf8NoBom $vhostConf $vhost

# 回调公网根地址属于运行环境配置，保留 .env 中其它敏感项且不输出文件内容。
$envText = [System.IO.File]::ReadAllText($envFile)
if ($envText -match '(?m)^SHOPIFY_WEBHOOK_BASE_URL=.*$') {
    $envText = $envText -replace '(?m)^SHOPIFY_WEBHOOK_BASE_URL=.*$', "SHOPIFY_WEBHOOK_BASE_URL=$publicBaseUrl"
} else {
    $envText = $envText.TrimEnd() + "`r`nSHOPIFY_WEBHOOK_BASE_URL=$publicBaseUrl`r`n"
}
Save-Utf8NoBom $envFile $envText

$syntaxResult = & $httpdExe -t 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Apache 配置检查失败，未重启服务：$($syntaxResult -join '；')"
}
Write-Host ($syntaxResult -join "`r`n")

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restartScript -Port 8001
if ($LASTEXITCODE -ne 0) {
    throw "Uvicorn 切换到内部端口 8001 失败。"
}

Restart-Service -Name "apache24-php8" -Force
Start-Sleep -Seconds 2

$result = & curl.exe --silent --show-error --fail --resolve "admin.monozex.com:8000:127.0.0.1" "https://admin.monozex.com:8000/login" --output NUL --write-out "%{http_code}"
if ($LASTEXITCODE -ne 0 -or $result -ne "200") {
    throw "本机 HTTPS 验证失败，HTTP 状态：$result"
}

Write-Host "mzShop HTTPS 部署成功：$publicBaseUrl" -ForegroundColor Green
