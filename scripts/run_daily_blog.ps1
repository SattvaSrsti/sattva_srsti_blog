# Daily blog reconcile — 23:11 local time via Task Scheduler.
# PC must be on (or able to wake). Uses Firebase CLI login, not env secrets.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("blog-daily-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))

$node = $null
$cmd = Get-Command node -ErrorAction SilentlyContinue
if ($cmd) { $node = $cmd.Source }
if (-not $node) {
  $guess = "C:\Program Files\nodejs\node.exe"
  if (Test-Path $guess) { $node = $guess }
}
if (-not $node) {
  "node.exe not found on PATH" | Tee-Object -FilePath $log
  exit 1
}

"$(Get-Date -Format o) starting $node functions/run_reconcile_once.js" | Tee-Object -FilePath $log
& $node (Join-Path $Root "functions\run_reconcile_once.js") *>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE
"$(Get-Date -Format o) exit $code" | Tee-Object -FilePath $log -Append
exit $code
