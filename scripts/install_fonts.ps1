# Install modern programming fonts for Windows
# Run this in PowerShell as Administrator

Write-Host "Installing Modern Programming Fonts..." -ForegroundColor Cyan

# Font URLs
$fonts = @{
    "CascadiaCode" = "https://github.com/microsoft/cascadia-code/releases/download/v2111.01/CascadiaCode-2111.01.zip"
    "FiraCode" = "https://github.com/tonsky/FiraCode/releases/download/6.2/Fira_Code_v6.2.zip"
    "JetBrainsMono" = "https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip"
    "Monaspace" = "https://github.com/githubnext/monaspace/releases/download/v1.000/monaspace-v1.000.zip"
}

$tempDir = "$env:TEMP\fonts_install"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

foreach ($fontName in $fonts.Keys) {
    Write-Host "`nDownloading $fontName..." -ForegroundColor Yellow

    $url = $fonts[$fontName]
    $zipPath = "$tempDir\$fontName.zip"
    $extractPath = "$tempDir\$fontName"

    try {
        # Download
        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing

        # Extract
        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

        # Find TTF files
        $ttfFiles = Get-ChildItem -Path $extractPath -Filter "*.ttf" -Recurse

        # Install fonts
        $fontsFolder = (New-Object -ComObject Shell.Application).Namespace(0x14)

        foreach ($font in $ttfFiles) {
            # Skip variable fonts (VF) - they're harder to work with
            if ($font.Name -match "VF") { continue }

            Write-Host "  Installing $($font.Name)..." -ForegroundColor Gray
            $fontsFolder.CopyHere($font.FullName, 0x10)
        }

        Write-Host "✓ $fontName installed!" -ForegroundColor Green

    } catch {
        Write-Host "✗ Failed to install $fontName : $_" -ForegroundColor Red
    }
}

# Cleanup
Remove-Item -Path $tempDir -Recurse -Force

Write-Host "`n✓ Font installation complete!" -ForegroundColor Cyan
Write-Host "Restart your terminal for changes to take effect." -ForegroundColor Yellow
