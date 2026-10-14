<#
  «كاتب» على Windows — تشغيل بأمر واحد (أو بالنقر المزدوج على Kateb.cmd في مجلد المشروع).

  أول مرة: يتحقق من Python وNode.js، ويثبّت الخادم، ويبني لوحة التحكم، وينشئ مفتاح التشفير في
  %APPDATA%\Kateb\master.key (لحسابك وحده)، ويحفظ البيانات في %LOCALAPPDATA%\Kateb (خارج OneDrive)،
  ثم يفحص الجاهزية ويفتح المتصفح على http://127.0.0.1:8000

  الخيارات:
    -Lan          يجعله متاحاً لأجهزتك الأخرى في الشبكة (يتطلب وجود حسابك، ويغلق التسجيل)
    -Port 8080    منفذ آخر
    -NoBrowser    لا يفتح المتصفح تلقائياً
    -CreateShortcut  يضع أيقونة «كاتب» على سطح المكتب وفي قائمة ابدأ (تُنشأ تلقائياً في أول تشغيل)
    -NoShortcut   لا ينشئ الأيقونة تلقائياً
    -SmokeTest    فحص كامل آلي ثم إيقاف (للتكامل المستمر): تثبيت، تشغيل، حساب، رواية، نص، تصدير Word وPDF
#>
param([switch]$Lan, [switch]$NoBrowser, [switch]$SmokeTest, [switch]$CreateShortcut, [switch]$NoShortcut,
      [int]$Port = 8000)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Say([string]$msg, [string]$color = "Gray") { Write-Host $msg -ForegroundColor $color }
function Fail([string]$msg) { Say $msg "Red"; exit 1 }

# ── أيقونة سطح المكتب وقائمة ابدأ ──────────────────────────────────
function New-KatebShortcut([string]$Name, [string]$Launcher, [string]$Description) {
  $icon = Join-Path $Root "infra\windows\kateb.ico"
  $made = @()
  foreach ($folder in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    if (-not $folder) { continue }
    $lnk = Join-Path $folder "$Name.lnk"
    # WScript.Shell cannot save a non-ASCII file name («كاتب» became «????»): save under an ASCII name,
    # then let PowerShell (full Unicode) give it the Arabic name.
    $tmp = Join-Path $folder ("kateb-" + [guid]::NewGuid().ToString("N").Substring(0, 8) + ".lnk")
    $shell = New-Object -ComObject WScript.Shell
    $s = $shell.CreateShortcut($tmp)
    $s.TargetPath = Join-Path $Root $Launcher
    $s.WorkingDirectory = $Root
    $s.IconLocation = "$icon,0"
    $s.Description = $Description
    $s.WindowStyle = 1
    $s.Save()
    Move-Item -LiteralPath $tmp -Destination $lnk -Force
    $made += $lnk
  }
  return $made
}
function New-KatebShortcuts {
  # descriptions stay ASCII for the same WScript.Shell reason; the visible names are Arabic
  New-KatebShortcut "كاتب" "Kateb.cmd" "Kateb - Arabic novel studio" | Out-Null
  New-KatebShortcut "كاتب — عدة أجهزة" "Kateb-multi-device.cmd" "Kateb for your other computers on the network" | Out-Null
}

if ($CreateShortcut) {
  New-KatebShortcuts
  Say "أُضيفت أيقونة «كاتب» إلى سطح المكتب وقائمة ابدأ." "Green"
  exit 0
}

# Already running (a second click on the icon): just open it instead of starting a second copy.
if (-not $SmokeTest -and -not $Lan) {
  try {
    $alive = Invoke-RestMethod "http://127.0.0.1:$Port/v1/health" -TimeoutSec 2
    if ($alive.status -eq "ok") {
      Say "«كاتب» يعمل بالفعل على http://127.0.0.1:$Port" "Green"
      if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
      exit 0
    }
  } catch { }
}

# ── Python (3.11 أو أحدث) ───────────────────────────────────────────
function Find-Python {
  foreach ($cand in @(@("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("python"), @("python3"))) {
    $exe = $cand[0]; $args0 = @($cand | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    try {
      # the Microsoft Store alias «python» exists but only opens the Store: it fails this probe
      $ok = & $exe @args0 -c "import sys; print(int(sys.version_info >= (3, 11)))" 2>$null
      if ($LASTEXITCODE -eq 0 -and "$ok".Trim() -eq "1") { return ,$cand }
    } catch { }
  }
  return $null
}

$py = Find-Python
if (-not $py) {
  Say "Python 3.11 أو أحدث غير مثبّت على هذا الجهاز." "Yellow"
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Say "يمكن تثبيته الآن بالأمر:  winget install -e --id Python.Python.3.12" "Yellow"
    if (-not $SmokeTest -and (Read-Host "هل أثبّته الآن؟ (y/n)") -match "^(y|yes|ن|نعم)$") {
      winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
      Say "ثُبّت Python. أغلق هذه النافذة وشغّل Kateb.cmd من جديد." "Green"; exit 0
    }
  } else { Say "نزّله من https://www.python.org/downloads/windows/ (فعّل خيار Add python.exe to PATH)." "Yellow" }
  exit 1
}

# ── بيئة بايثون وتثبيت الخادم ───────────────────────────────────────
$vpy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) {
  Say "إنشاء بيئة بايثون للمشروع…"
  $exe = $py[0]; $pargs = @($py | Select-Object -Skip 1)
  & $exe @pargs -m venv (Join-Path $Root ".venv"); if ($LASTEXITCODE) { Fail "تعذّر إنشاء بيئة بايثون." }
}
Say "تثبيت الخادم أو تحديثه…"
# WeasyPrint needs GTK/Pango, which Windows lacks: exports use the built-in ReportLab engine instead
& $vpy -m pip install -q --disable-pip-version-check -e (Join-Path $Root "apps\api")
if ($LASTEXITCODE) { Fail "تعذّر تثبيت الخادم — راجع اتصال الإنترنت ثم أعد المحاولة." }

# ── لوحة التحكم (تحتاج Node.js مرة واحدة فقط) ───────────────────────
$panel = Join-Path $Root "apps\api\nis\static\index.html"
if (-not (Test-Path $panel)) {
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Say "يلزم Node.js مرة واحدة لبناء لوحة التحكم." "Yellow"
    Say "ثبّته بالأمر:  winget install -e --id OpenJS.NodeJS.LTS   أو من https://nodejs.org ثم أعد التشغيل." "Yellow"
    exit 1
  }
  Say "بناء لوحة التحكم (مرة واحدة، قد تستغرق دقيقتين)…"
  Push-Location (Join-Path $Root "apps\web")
  try {
    & npm ci --no-audit --no-fund; if ($LASTEXITCODE) { Fail "تعذّر تثبيت حزم الواجهة." }
    & npx vite build; if ($LASTEXITCODE) { Fail "تعذّر بناء لوحة التحكم." }
  } finally { Pop-Location }
}

# ── مكان البيانات ومفتاح التشفير ────────────────────────────────────
if ($SmokeTest) {
  $HomeDir = Join-Path ([System.IO.Path]::GetTempPath()) ("kateb-smoke-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
  $KeyFile = Join-Path $HomeDir "master.key"
} else {
  $HomeDir = if ($env:KATEB_HOME) { $env:KATEB_HOME } else { Join-Path $env:LOCALAPPDATA "Kateb" }
  $KeyFile = if ($env:KATEB_KEY_FILE) { $env:KATEB_KEY_FILE } else { Join-Path $env:APPDATA "Kateb\master.key" }
}
New-Item -ItemType Directory -Force -Path $HomeDir | Out-Null
if (-not $env:NIS_MASTER_KEY) {
  if (-not (Test-Path $KeyFile)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $KeyFile) | Out-Null
    $newKey = (& $vpy -m nis.cli new-key).Trim()
    [System.IO.File]::WriteAllText($KeyFile, $newKey)
    # only this Windows account may read the key
    & icacls $KeyFile /inheritance:r /grant:r "$($env:USERDOMAIN)\$($env:USERNAME):(R,W)" | Out-Null
    Say "أُنشئ مفتاح التشفير: $KeyFile" "Green"
    Say "احفظ نسخة منه في مكان آمن منفصل (مثل مدير كلمات المرور)؛ من دونه لا تُقرأ المخطوطات." "Yellow"
  }
  $env:NIS_MASTER_KEY = ([System.IO.File]::ReadAllText($KeyFile)).Trim()
}
$dbPath = (Join-Path $HomeDir "nis.db") -replace "\\", "/"
if (-not $env:NIS_DATABASE_URL) { $env:NIS_DATABASE_URL = "sqlite:///$dbPath" }
if (-not $env:NIS_DATA_DIR) { $env:NIS_DATA_DIR = Join-Path $HomeDir "data" }

& $vpy -m nis.cli migrate | Out-Null; if ($LASTEXITCODE) { Fail "تعذّر تحديث قاعدة البيانات." }
& $vpy -m nis.cli encrypt-existing | Out-Null

$BindHost = "127.0.0.1"
if ($Lan) {
  $users = (& $vpy -c "from sqlalchemy import func, select; from nis.db import SessionLocal; from nis.models import User; print(SessionLocal().scalar(select(func.count()).select_from(User)))").Trim()
  if ($users -eq "0") { Fail "أنشئ حسابك أولاً بتشغيل عادي (Kateb.cmd) ثم أعد التشغيل بوضع عدة أجهزة؛ لا يُفتح التطبيق للشبكة قبل وجود حسابك." }
  $env:NIS_ALLOW_REGISTRATION = "false"; $env:KATEB_LAN = "1"; $BindHost = "0.0.0.0"
  Say "────────────────────────────────────────────────────────────" "Cyan"
  Say " وضع عدة أجهزة: التسجيل مغلق، وتصل إليه أجهزتك عبر:" "Cyan"
  Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    ForEach-Object { $tag = if ($_.IPAddress -like "100.*") { "  ← شبكة Tailscale الخاصة" } else { "" }; Say ("   http://{0}:{1}{2}" -f $_.IPAddress, $Port, $tag) "Cyan" }
  Say " إن ظهر تنبيه جدار حماية Windows فاسمح بالشبكات الخاصة فقط، لا العامة." "Yellow"
  Say " الاتصال غير مشفّر داخل الشبكة: استعمله في شبكة موثوقة أو عبر شبكة خاصة مشفّرة (مثل Tailscale)." "Yellow"
  Say "────────────────────────────────────────────────────────────" "Cyan"
}
$url = "http://127.0.0.1:$Port"

function Wait-Health([int]$seconds) {
  for ($i = 0; $i -lt $seconds; $i++) {
    try { Invoke-RestMethod "$url/v1/health" -TimeoutSec 2 | Out-Null; return $true } catch { Start-Sleep -Seconds 1 }
  }
  return $false
}

if ($SmokeTest) {
  $env:NIS_RUNS_INLINE = "true"
  $out = Join-Path $HomeDir "server.out"; $err = Join-Path $HomeDir "server.err"
  $proc = Start-Process -FilePath $vpy -ArgumentList @("-m", "nis.cli", "serve", "--host", $BindHost, "--port", "$Port") `
          -PassThru -NoNewWindow -RedirectStandardOutput $out -RedirectStandardError $err
  try {
    if (-not (Wait-Health 90)) { Get-Content $out, $err -ErrorAction SilentlyContinue; Fail "SMOKE: الخادم لم يستجب." }
    function Post($path, $body, $headers = @{}) {
      $bytes = [System.Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 12 -Compress))
      return Invoke-RestMethod -Method Post "$url$path" -Headers $headers -ContentType "application/json; charset=utf-8" -Body $bytes
    }
    $reg = Post "/v1/auth/register" @{ email = "smoke@example.test"; password = "smoke-password-1"; display_name = "smoke" }
    $h = @{ Authorization = "Bearer $($reg.token)" }
    $p = Post "/v1/projects" @{ title = "رواية فحص Windows" } $h
    $ch = Post "/v1/projects/$($p.id)/nodes" @{ type = "chapter"; title = "الأول"; meta = @{} } $h
    $doc = Invoke-RestMethod "$url/v1/documents/$($ch.document_id)" -Headers $h
    $content = @{ type = "doc"; content = @(@{ type = "paragraph"; content = @(@{ type = "text"; text = "كان البحر هادئاً، وقال نادر: «سأعود في 10:30»." }) }) }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes((@{ content_json = $content; kind = "checkpoint" } | ConvertTo-Json -Depth 12 -Compress))
    $saved = Invoke-RestMethod -Method Put "$url/v1/documents/$($ch.document_id)" -Body $bytes -ContentType "application/json; charset=utf-8" `
             -Headers @{ Authorization = "Bearer $($reg.token)"; "If-Match" = "W/`"$($doc.version)`"" }
    if ($saved.word_count -lt 5) { Fail "SMOKE: لم يُحفظ النص ($($saved.word_count) كلمة)." }
    foreach ($fmt in @("docx", "pdf", "epub")) {
      $e = Post "/v1/projects/$($p.id)/exports" @{ format = $fmt } $h
      $file = Join-Path $HomeDir "book.$fmt"
      Invoke-WebRequest "$url/v1/exports/$($e.id)/download" -Headers $h -OutFile $file -UseBasicParsing
      $size = (Get-Item $file).Length
      if ($size -lt 2000) { Fail "SMOKE: تصدير $fmt صغير على غير المتوقع ($size بايت)." }
      Say "SMOKE: $fmt — $size بايت" "Green"
    }
    $panelPage = Invoke-WebRequest "$url/" -UseBasicParsing
    if ($panelPage.StatusCode -ne 200) { Fail "SMOKE: لوحة التحكم لا تُخدم." }
    & $vpy -m nis.cli verify-data; if ($LASTEXITCODE) { Fail "SMOKE: verify-data فشل." }
    # a second click on the icon while it runs must return at once, without starting another server
    $t0 = Get-Date
    & powershell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -Port $Port -NoBrowser | Out-Null
    if ($LASTEXITCODE -ne 0 -or ((Get-Date) - $t0).TotalSeconds -gt 30) { Fail "SMOKE: النقرة الثانية لم تتعرّف على التطبيق العامل." }
    Say "SMOKE: النقرة الثانية فتحت التطبيق العامل دون تشغيل نسخة أخرى." "Green"
    Say "SMOKE: نجح التشغيل الكامل على Windows." "Green"
  } finally {
    if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
  }
  exit 0
}

if (-not $NoShortcut -and -not (Test-Path (Join-Path ([Environment]::GetFolderPath("Desktop")) "كاتب.lnk"))) {
  try { New-KatebShortcuts; Say "أُضيفت أيقونة «كاتب» إلى سطح المكتب وقائمة ابدأ؛ من الآن يكفي النقر عليها." "Green" }
  catch { Say "تعذّر إنشاء أيقونة سطح المكتب ($($_.Exception.Message)) — يمكن تشغيل Kateb.cmd مباشرة." "Yellow" }
}

if (-not $NoBrowser) {
  # open the browser once the server answers, while the server runs in this window
  Start-Job -ScriptBlock {
    param($u)
    for ($i = 0; $i -lt 120; $i++) {
      try { Invoke-RestMethod "$u/v1/health" -TimeoutSec 2 | Out-Null; Start-Process $u; return } catch { Start-Sleep -Seconds 1 }
    }
  } -ArgumentList $url | Out-Null
}
Say "«كاتب» يعمل على $url — أبقِ هذه النافذة مفتوحة أثناء الكتابة، وأغلقها (أو Ctrl+C) للإيقاف." "Green"
& $vpy -m nis.cli serve --host $BindHost --port $Port
