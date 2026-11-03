# 建置 T9NumPad.exe
# 用法：powershell -ExecutionPolicy Bypass -File build_exe.ps1
# 需要網路（安裝 PyInstaller）與 Python 3.10+。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "[1/3] 安裝 / 更新 PyInstaller ..."
python -m pip install --upgrade pyinstaller

Write-Host "[2/3] 產生圖示 ..."
python tools\make_icon.py

Write-Host "[3/3] 打包單檔 EXE ..."
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name T9NumPad `
    --icon assets\t9.ico `
    run.pyw

if (Test-Path "dist\T9NumPad.exe") {
    Write-Host "完成：dist\T9NumPad.exe"
} else {
    Write-Error "打包失敗，請檢查上面的訊息。"
}
