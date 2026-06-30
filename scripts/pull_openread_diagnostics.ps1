param(
    [string]$HostName = "193.122.152.253",
    [string]$User = "",
    [string]$Container = "openread",
    [string]$RemoteDiagnosticsDir = "/app/backend/var/diagnostics/gemma",
    [string]$OutputRoot = "",
    [int]$PipelineTimeoutSeconds = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-JsonProperty {
    param(
        [object]$Object,
        [string]$Name
    )
    if ($null -eq $Object) {
        return $null
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Add-Count {
    param(
        [hashtable]$Table,
        [string]$Key
    )
    if ($Table.ContainsKey($Key)) {
        $Table[$Key] = [int]$Table[$Key] + 1
    } else {
        $Table[$Key] = 1
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $repoRoot "backend\var\diagnostics\server-pulls"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = if ($User) { "$User@$HostName" } else { $HostName }
$destination = Join-Path $OutputRoot "$HostName-$stamp"
New-Item -ItemType Directory -Force -Path $destination | Out-Null

$remotePython = @"
from pathlib import Path
import json

root = Path("$RemoteDiagnosticsDir")
records = []

if root.exists():
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            records.append({"filename": path.name, "parse_error": str(exc)})
            continue
        records.append({"filename": path.name, "payload": payload})

print(json.dumps({
    "source": "${HostName}:$RemoteDiagnosticsDir",
    "record_count": len(records),
    "records": records,
}, ensure_ascii=False))
"@

$encodedRemotePython = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remotePython))
$sshArgs = @(
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    $target,
    "docker exec -i $Container python -c 'import sys,base64; exec(base64.b64decode(sys.stdin.read()).decode())'"
)

$rawJsonText = $encodedRemotePython | & ssh.exe @sshArgs
if (-not $rawJsonText) {
    throw "No diagnostics payload returned from $target."
}

$rawPath = Join-Path $destination "gemma_diagnostics_raw.json"
$summaryPath = Join-Path $destination "gemma_diagnostics_summary.json"
$csvPath = Join-Path $destination "gemma_diagnostics_summary.csv"

$rawPayload = $rawJsonText | ConvertFrom-Json
$rawPayload | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $rawPath -Encoding utf8

$rows = foreach ($record in $rawPayload.records) {
    $payload = Get-JsonProperty $record "payload"
    $rawOutputs = @()
    $validationErrors = @()
    $warnings = @()
    $serviceTotalMs = $null

    if ($payload) {
        $rawGemmaOutputs = Get-JsonProperty $payload "raw_gemma_outputs"
        $payloadValidationErrors = Get-JsonProperty $payload "validation_errors"
        $storyDiagnostics = Get-JsonProperty $payload "story_diagnostics"
        $storyWarnings = Get-JsonProperty $storyDiagnostics "warnings"
        $timings = Get-JsonProperty $payload "timings"
        $serviceTotalMs = Get-JsonProperty $timings "service_total_ms"
        if ($rawGemmaOutputs) {
            $rawOutputs = @($rawGemmaOutputs)
        }
        if ($payloadValidationErrors) {
            $validationErrors = @($payloadValidationErrors)
        }
        if ($storyWarnings) {
            $warnings = @($storyWarnings)
        }
    }

    [pscustomobject]@{
        filename = Get-JsonProperty $record "filename"
        request_id = Get-JsonProperty $payload "request_id"
        created_at = Get-JsonProperty $payload "created_at"
        expires_at = Get-JsonProperty $payload "expires_at"
        client_ip = Get-JsonProperty $payload "client_ip"
        status = Get-JsonProperty $payload "status"
        fallback_used = Get-JsonProperty $payload "fallback_used"
        model = Get-JsonProperty $payload "model"
        compiler_mode = Get-JsonProperty $payload "compiler_mode"
        lang_hint = Get-JsonProperty $payload "lang_hint"
        raw_output_count = $rawOutputs.Count
        raw_output_chars = ($rawOutputs | ForEach-Object { [string]$_ } | Measure-Object -Character).Characters
        validation_error_count = $validationErrors.Count
        warning_count = $warnings.Count
        final_spoken_script_chars = if (Get-JsonProperty $payload "final_spoken_script") {
            ([string](Get-JsonProperty $payload "final_spoken_script")).Length
        } else {
            0
        }
        gemma_status = Get-JsonProperty $payload "status"
        pipeline_status = Get-JsonProperty $payload "pipeline_status"
        effective_status = if (Get-JsonProperty $payload "pipeline_status") {
            Get-JsonProperty $payload "pipeline_status"
        } elseif ($serviceTotalMs -and ([double]$serviceTotalMs -gt ($PipelineTimeoutSeconds * 1000))) {
            "likely_failed_timeout"
        } else {
            Get-JsonProperty $payload "status"
        }
        exceeded_pipeline_timeout = if ($serviceTotalMs) {
            [double]$serviceTotalMs -gt ($PipelineTimeoutSeconds * 1000)
        } else {
            $false
        }
        service_total_ms = $serviceTotalMs
        pipeline_error = Get-JsonProperty $payload "pipeline_error"
        error = if (Get-JsonProperty $payload "pipeline_error") {
            Get-JsonProperty $payload "pipeline_error"
        } elseif ($payload) {
            Get-JsonProperty $payload "error"
        } else {
            Get-JsonProperty $record "parse_error"
        }
    }
}

$statusCounts = @{}
$clientIpCounts = @{}
$modeCounts = @{}
foreach ($row in $rows) {
    $statusKey = [string]$row.effective_status
    $clientIpKey = [string]$row.client_ip
    $modeKey = [string]$row.compiler_mode
    Add-Count $statusCounts $statusKey
    Add-Count $clientIpCounts $clientIpKey
    Add-Count $modeCounts $modeKey
}

$createdAtValues = @($rows | Where-Object { $_.created_at } | ForEach-Object { $_.created_at })
$summary = [pscustomobject]@{
    source = $rawPayload.source
    pulled_at = (Get-Date).ToUniversalTime().ToString("o")
    record_count = @($rows).Count
    status_counts = $statusCounts
    client_ip_counts = $clientIpCounts
    compiler_mode_counts = $modeCounts
    first_created_at = if ($createdAtValues.Count) { ($createdAtValues | Sort-Object | Select-Object -First 1) } else { $null }
    last_created_at = if ($createdAtValues.Count) { ($createdAtValues | Sort-Object | Select-Object -Last 1) } else { $null }
    records = @($rows)
}

$summary | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $summaryPath -Encoding utf8
$rows | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding utf8

Write-Host "Pulled OpenRead diagnostics from $target"
Write-Host "Raw:     $rawPath"
Write-Host "Summary: $summaryPath"
Write-Host "CSV:     $csvPath"
Write-Host ""
Write-Host "Record count: $($summary.record_count)"
Write-Host "Status counts:"
$statusCounts.GetEnumerator() | Sort-Object Name | ForEach-Object {
    Write-Host "  $($_.Name): $($_.Value)"
}
Write-Host "Client IP counts:"
$clientIpCounts.GetEnumerator() | Sort-Object Name | ForEach-Object {
    Write-Host "  $($_.Name): $($_.Value)"
}
