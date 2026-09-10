<#
Prepare the exact P04 instrumented upstream checkout and run the controlled CPU
benchmark from Windows PowerShell.

Usage:
  .\scripts\reproduce\p04_prepare_and_run.ps1 `
      -Upstream C:\src\tesseract-decoder `
      -Output C:\results\p04 `
      -MachineLabel windows-workstation

The upstream checkout must already be at the pinned SHA and clean. The script
never fetches or changes branches. Windows does not use Linux perf counters in
this wrapper; the decoder-internal timing remains the primary portable metric.
#>
param(
    [Parameter(Mandatory=$true)][string]$Upstream,
    [Parameter(Mandatory=$true)][string]$Output,
    [Parameter(Mandatory=$true)][string]$MachineLabel
)

$ErrorActionPreference = 'Stop'
$Expected = '024db1d3b5b038f565c476dd1b51885271f7b0bf'

$Actual = (git -C $Upstream rev-parse HEAD).Trim()
if ($Actual -ne $Expected) {
    throw "Expected upstream $Expected but found $Actual"
}

$Dirty = (git -C $Upstream status --porcelain) -join "`n"
if ($Dirty.Trim().Length -ne 0) {
    throw 'Upstream checkout must be clean before P02 instrumentation is applied.'
}

New-Item -ItemType Directory -Force -Path $Output | Out-Null

python scripts/instrument/apply_p02_layer_stats.py `
    --upstream-dir $Upstream `
    --report (Join-Path $Output 'p02a-patch-report.json')
if ($LASTEXITCODE -ne 0) { throw 'P02a instrumentation failed.' }

python scripts/instrument/apply_p02b_layer_trace_cli.py `
    --upstream-dir $Upstream `
    --report (Join-Path $Output 'p02b-patch-report.json')
if ($LASTEXITCODE -ne 0) { throw 'P02b instrumentation failed.' }

git -C $Upstream diff --check
if ($LASTEXITCODE -ne 0) { throw 'git diff --check failed.' }
git -C $Upstream diff | Set-Content -Encoding utf8 (Join-Path $Output 'instrumentation.patch')

Push-Location $Upstream
try {
    bazel test //src:tesseract_trellis_tests --test_output=errors
    if ($LASTEXITCODE -ne 0) { throw 'Focused Trellis tests failed.' }
    bazel build -c opt //src:tesseract_trellis
    if ($LASTEXITCODE -ne 0) { throw 'Optimized Trellis build failed.' }
}
finally {
    Pop-Location
}

# The Python harness is deliberately cross-platform. On Windows we do not pass
# --with-perf because Linux perf is not the portable counter source here. The
# environment manifest records the platform so these results cannot be silently
# mixed with a Linux counter run.
python scripts/reproduce/p04_controlled_cpu_benchmark.py `
    --mode benchmark `
    --machine-label $MachineLabel `
    --upstream-dir $Upstream `
    --output-dir (Join-Path $Output 'benchmark') `
    --event-block-repeats 250 `
    --warmups 2 `
    --repetitions 10
if ($LASTEXITCODE -ne 0) { throw 'P04 controlled benchmark failed.' }

# PowerShell computes a deterministic checksum manifest without requiring GNU
# sha256sum. Paths are made relative to the output directory for portability.
$Root = (Resolve-Path $Output).Path
$ChecksumPath = Join-Path $Root 'SHA256SUMS'
$Lines = Get-ChildItem -Path $Root -File -Recurse |
    Where-Object { $_.FullName -ne $ChecksumPath } |
    Sort-Object FullName |
    ForEach-Object {
        $Hash = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLowerInvariant()
        $Relative = $_.FullName.Substring($Root.Length).TrimStart('\\','/').Replace('\\','/')
        "$Hash  $Relative"
    }
$Lines | Set-Content -Encoding ascii $ChecksumPath

Write-Host "P04 controlled benchmark completed: $Output"
