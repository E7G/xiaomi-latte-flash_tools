param(
    [switch]$BootOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Normalize-RelativePath([string]$Path) {
    return $Path.Replace('\', '/').TrimStart([char[]]'./')
}

function Invoke-Fastboot {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )

    Write-Host ("fastboot " + ($Arguments -join ' ')) -ForegroundColor DarkGray
    & $script:Fastboot @Arguments
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "fastboot failed with exit code ${code}: $($Arguments -join ' ')"
    }
    return $code
}

function Wait-Fastboot([int]$TimeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $output = & $script:Fastboot devices 2>&1
        if ($LASTEXITCODE -eq 0 -and (($output | Out-String) -match '(?m)^\S+\s+fastboot\s*$')) {
            return
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    throw "No fastboot device appeared within $TimeoutSeconds seconds"
}

try {
    $bundledFastboot = Join-Path $Root 'platform-tools\fastboot.exe'
    if (Test-Path -LiteralPath $bundledFastboot) {
        $script:Fastboot = $bundledFastboot
    } else {
        $command = Get-Command fastboot.exe -ErrorAction SilentlyContinue
        if (-not $command) {
            throw 'Bundled platform-tools\fastboot.exe is missing and fastboot.exe is not in PATH'
        }
        $script:Fastboot = $command.Source
    }

    $loader = Join-Path $Root 'device_files\fastboot.efi'
    $bootImage = Join-Path $Root 'images\xiaomi-latte-boot.img'
    $required = @(
        'platform-tools/fastboot.exe',
        'device_files/fastboot.efi',
        'images/xiaomi-latte-boot.img'
    )
    if (-not $BootOnly) {
        $required += @(
            'device_files/oemvars.txt',
            'device_files/oemvars-battery-config-fake-disabled.txt',
            'device_files/oemvars-battery-config-fake.txt',
            'images/gpt.bin',
            'images/xiaomi-latte-rootfs.img'
        )
    }

    Write-Step 'Checking package files and SHA256 hashes'
    $manifestPath = Join-Path $Root 'SHA256SUMS'
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        throw 'SHA256SUMS is missing'
    }
    $manifest = @{}
    foreach ($line in Get-Content -LiteralPath $manifestPath) {
        if ($line -match '^([0-9a-fA-F]{64})\s+\*?(.+)$') {
            $manifest[(Normalize-RelativePath $matches[2])] = $matches[1].ToLowerInvariant()
        }
    }
    foreach ($relative in $required) {
        $normalized = Normalize-RelativePath $relative
        $file = Join-Path $Root ($normalized.Replace('/', '\'))
        if (-not (Test-Path -LiteralPath $file)) {
            throw "Required file is missing: $normalized"
        }
        if (-not $manifest.ContainsKey($normalized)) {
            throw "No SHA256 entry for: $normalized"
        }
        $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $manifest[$normalized]) {
            throw "SHA256 mismatch: $normalized"
        }
        Write-Host "OK  $normalized"
    }

    Write-Step 'Waiting for Xiaomi Mi Pad 2 in DNX/fastboot mode'
    Wait-Fastboot 90

    Write-Step 'Starting the original Mi Pad 2 EFI fastboot loader'
    # The DNX loader can drop USB before old fastboot hosts receive the final
    # acknowledgement.  Re-enumeration plus the latte product check below is
    # authoritative, so do not abort solely on this transient return code.
    Invoke-Fastboot -Arguments @('boot', $loader) -AllowFailure | Out-Null
    Start-Sleep -Seconds 3
    Wait-Fastboot 90

    $productOutput = & $script:Fastboot getvar product 2>&1
    $productCode = $LASTEXITCODE
    $productText = $productOutput | Out-String
    Write-Host $productText
    if ($productCode -ne 0 -or $productText -notmatch '(?im)product:\s*latte\b') {
        throw 'Connected device is not Xiaomi Mi Pad 2 (latte)'
    }

    Write-Step 'Unlocking flash commands'
    Invoke-Fastboot -Arguments @('oem', 'unlock') -AllowFailure | Out-Null

    if ($BootOnly) {
        Write-Step 'Flashing repaired boot image'
        Invoke-Fastboot -Arguments @('flash', 'boot', $bootImage) | Out-Null
    } else {
        Write-Step 'Applying original Mi Pad 2 OEM variables'
        foreach ($name in @(
            'oemvars.txt',
            'oemvars-battery-config-fake-disabled.txt',
            'oemvars-battery-config-fake.txt'
        )) {
            Invoke-Fastboot -Arguments @('flash', 'oemvars', (Join-Path $Root "device_files\$name")) | Out-Null
        }

        Write-Step 'Flashing original partition layout'
        Invoke-Fastboot -Arguments @('flash', 'gpt', (Join-Path $Root 'images\gpt.bin')) | Out-Null
        Start-Sleep -Seconds 2
        Wait-Fastboot 60

        Write-Step 'Flashing boot image'
        Invoke-Fastboot -Arguments @('flash', 'boot', $bootImage) | Out-Null

        Write-Step 'Flashing CachyOS KDE system image'
        Invoke-Fastboot -Arguments @('flash', 'system', (Join-Path $Root 'images\xiaomi-latte-rootfs.img')) | Out-Null
    }

    Write-Step 'Rebooting tablet'
    Invoke-Fastboot -Arguments @('reboot') | Out-Null
    Write-Host "`nFLASH COMPLETE" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "`nFLASH ABORTED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
