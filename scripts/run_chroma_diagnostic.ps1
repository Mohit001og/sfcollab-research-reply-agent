$ErrorActionPreference = "Stop"

# Confirmed real Render service name.
$ServiceName = "sfcollab-research-reply-agent"
$DiagnosticBranch = "chore/chroma-memory-diagnostic"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DiagnosticResultPath = Join-Path $RepoRoot "diagnostic_result.json"
$Warnings = New-Object System.Collections.Generic.List[string]
$DiagnosticSucceeded = $false
$DiagnosticResult = $null
$OriginalBranch = $null
$ServiceId = $null
$ServiceDetails = $null
$DiagnosticDeployId = $null
$RevertDeployId = $null

function Write-ApiError {
    param(
        [string]$Label,
        [object]$ErrorRecord
    )

    Write-Host "$Label"
    if ($null -ne $ErrorRecord) {
        if ($ErrorRecord.Exception -and $ErrorRecord.Exception.Message) {
            Write-Host $ErrorRecord.Exception.Message
        } else {
            Write-Host ($ErrorRecord | Out-String)
        }
    }
}

function Invoke-RenderApi {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("GET", "PATCH", "POST")] [string]$Method,
        [Parameter(Mandatory = $true)][string]$Uri,
        [object]$Body
    )

    $headers = @{
        Authorization = "Bearer $env:RENDER_API_KEY"
    }

    try {
        if ($PSBoundParameters.ContainsKey("Body")) {
            return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 20) -ErrorAction Stop
        }
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers -ErrorAction Stop
    }
    catch {
        Write-ApiError -Label "Render API call failed: $Method $Uri" -ErrorRecord $_

        $bodyPrinted = $false

        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            Write-Host "RESPONSE_BODY: $($_.ErrorDetails.Message)"
            $bodyPrinted = $true
        }

        if (-not $bodyPrinted -and $_.Exception.Response) {
            try {
                $stream = $_.Exception.Response.GetResponseStream()
                if ($stream -and $stream.CanSeek) {
                    $stream.Position = 0
                }
                $reader = New-Object System.IO.StreamReader($stream)
                $body = $reader.ReadToEnd()
                if ($body) {
                    Write-Host "RESPONSE_BODY: $body"
                    $bodyPrinted = $true
                }
            }
            catch {
                # ignore, fall through
            }
        }

        if (-not $bodyPrinted) {
            Write-Host "RESPONSE_BODY: <unavailable>"
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                Write-Host "HTTP_STATUS_CODE: $($_.Exception.Response.StatusCode.value__)"
            }
        }

        throw
    }
}

function Get-TerminalDeployStatus {
    param([string]$Status)
    return @("live", "succeeded", "build_failed", "update_failed", "canceled", "deactivated") -contains $Status
}

if (-not $env:RENDER_API_KEY) {
    Write-Host "ERROR: RENDER_API_KEY is not set. Exiting."
    exit 1
}

try {
    Write-Host "POWERSHELL_VERSION: $($PSVersionTable.PSVersion)"
    $serviceSearchUri = "https://api.render.com/v1/services?name=$([uri]::EscapeDataString($ServiceName))"
    try {
        $servicesResponse = Invoke-RenderApi -Method GET -Uri $serviceSearchUri
    }
    catch {
        throw
    }

    $serviceCandidates = @()
    if ($servicesResponse.items) {
        $serviceCandidates = @($servicesResponse.items)
    } elseif ($servicesResponse.services) {
        $serviceCandidates = @($servicesResponse.services)
    } elseif ($servicesResponse) {
        $serviceCandidates = @($servicesResponse)
    }

    $serviceMatch = $serviceCandidates | Where-Object { $_.service -and $_.service.name -eq $ServiceName } | Select-Object -First 1
    if (-not $serviceMatch) {
        Write-Host "ERROR: Service not found for name '$ServiceName'. Raw API response:"
        $servicesResponse | ConvertTo-Json -Depth 20 | Write-Host
        exit 1
    }

    $serviceMatch = $serviceMatch.service
    $ServiceId = $serviceMatch.id
    $serviceDetailsUri = "https://api.render.com/v1/services/$ServiceId"
    $ServiceDetails = Invoke-RenderApi -Method GET -Uri $serviceDetailsUri
    $OriginalBranch = $ServiceDetails.branch

    Write-Host "SERVICE_ID=$ServiceId"
    Write-Host "ORIGINAL_BRANCH=$OriginalBranch"

    $patchBody = @{ branch = $DiagnosticBranch }
    Write-Host "PATCH_REQUEST_BODY="
    $patchBody | ConvertTo-Json -Depth 20 | Write-Host
    Invoke-RenderApi -Method PATCH -Uri $serviceDetailsUri -Body $patchBody | Out-Null

    $deployResponse = Invoke-RenderApi -Method POST -Uri "$serviceDetailsUri/deploys" -Body @{}
    $DiagnosticDeployId = $deployResponse.id
    Write-Host "DIAGNOSTIC_DEPLOY_ID=$DiagnosticDeployId"

    $deployTerminal = $false
    $deploySucceeded = $false
    for ($poll = 1; $poll -le 30; $poll++) {
        Start-Sleep -Seconds 10
        $deployStatusResponse = Invoke-RenderApi -Method GET -Uri "$serviceDetailsUri/deploys/$DiagnosticDeployId"
        $status = $deployStatusResponse.status
        Write-Host "DEPLOY_POLL_$poll STATUS=$status"
        if (Get-TerminalDeployStatus -Status $status) {
            $deployTerminal = $true
            if ($status -in @("live", "succeeded")) {
                $deploySucceeded = $true
            }
            break
        }
    }

    if (-not $deployTerminal) {
        $Warnings.Add("Diagnostic deploy did not reach a terminal state within 5 minutes.")
    }

    if ($deploySucceeded) {
        $serviceDetails = Invoke-RenderApi -Method GET -Uri $serviceDetailsUri
        $serviceUrl = $serviceDetails.serviceDetails.url
        if (-not $serviceUrl) {
            $Warnings.Add("Could not determine the service public URL from the Render service details response.")
        } else {
            $diagnosticUri = ($serviceUrl.TrimEnd('/') + "/debug/chroma-memory-test")
            $lastError = $null
            for ($attempt = 1; $attempt -le 6; $attempt++) {
                Start-Sleep -Seconds 10
                try {
                    $response = Invoke-RestMethod -Method GET -Uri $diagnosticUri -ErrorAction Stop
                    $DiagnosticResult = $response
                    $DiagnosticSucceeded = $true
                    Write-Host "DIAGNOSTIC_RESPONSE_JSON="
                    $response | ConvertTo-Json -Depth 50 | Write-Host
                    $response | ConvertTo-Json -Depth 50 | Set-Content -Path $DiagnosticResultPath -Encoding UTF8
                    break
                }
                catch {
                    $lastError = $_
                    Write-Host "DIAGNOSTIC_ATTEMPT_$attempt FAILED"
                    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                        Write-Host ("STATUS_CODE=" + [int]$_.Exception.Response.StatusCode)
                    }
                    Write-Host ($_.Exception.Message)
                }
            }

            if (-not $DiagnosticSucceeded) {
                $Warnings.Add("Diagnostic endpoint did not return HTTP 200 within 6 attempts. Last error: $($lastError.Exception.Message)")
            }
        }
    }
    else {
        try {
            $failedDeploy = Invoke-RenderApi -Method GET -Uri "$serviceDetailsUri/deploys/$DiagnosticDeployId"
            Write-Host "FAILED_DEPLOY_JSON="
            $failedDeploy | ConvertTo-Json -Depth 50 | Write-Host
        }
        catch {
            $Warnings.Add("Unable to fetch failed deploy details.")
        }

        try {
            $logsUri = "$serviceDetailsUri/logs"
            $logsResponse = Invoke-RenderApi -Method GET -Uri $logsUri
            Write-Host "SERVICE_LOGS_JSON="
            $logsResponse | ConvertTo-Json -Depth 50 | Write-Host
        }
        catch {
            $Warnings.Add("Unable to fetch service logs from Render.")
        }
    }
}
catch {
    $Warnings.Add("Top-level diagnostic flow failed: $($_.Exception.Message)")
}
finally {
    Write-Host "REVERT_START"
    try {
        if ($ServiceId) {
            $revertBody = @{ branch = $OriginalBranch }
            Invoke-RenderApi -Method PATCH -Uri "https://api.render.com/v1/services/$ServiceId" -Body $revertBody | Out-Null
            $revertDeploy = Invoke-RenderApi -Method POST -Uri "https://api.render.com/v1/services/$ServiceId/deploys" -Body @{}
            $RevertDeployId = $revertDeploy.id
            Write-Host "REVERT_DEPLOY_ID=$RevertDeployId"

            $revertTerminal = $false
            $revertSucceeded = $false
            for ($poll = 1; $poll -le 30; $poll++) {
                Start-Sleep -Seconds 10
                $revertStatusResponse = Invoke-RenderApi -Method GET -Uri "https://api.render.com/v1/services/$ServiceId/deploys/$RevertDeployId"
                $revertStatus = $revertStatusResponse.status
                Write-Host "REVERT_POLL_$poll STATUS=$revertStatus"
                if (Get-TerminalDeployStatus -Status $revertStatus) {
                    $revertTerminal = $true
                    if ($revertStatus -in @("live", "succeeded")) {
                        $revertSucceeded = $true
                    }
                    break
                }
            }

            if (-not $revertTerminal -or -not $revertSucceeded) {
                $Warnings.Add("WARNING: Revert deploy did not complete successfully. Check the Render dashboard immediately.")
                Write-Host "WARNING: Revert deploy did not complete successfully. Check the Render dashboard immediately."
            }
            else {
                Write-Host "REVERT_CONFIRMED_BACK_ON_BRANCH=$OriginalBranch"
            }
        }
    }
    catch {
        $Warnings.Add("WARNING: Revert flow failed. Check the Render dashboard immediately.")
        Write-Host "WARNING: Revert flow failed. Check the Render dashboard immediately."
        Write-Host $_.Exception.Message
    }

    Write-Host "FINAL_SUMMARY"
    Write-Host "Diagnostic endpoint succeeded: $DiagnosticSucceeded"
    if ($DiagnosticSucceeded -and $DiagnosticResult) {
        Write-Host "Diagnostic JSON:"
        $DiagnosticResult | ConvertTo-Json -Depth 50 | Write-Host
    }
    Write-Host "Service branch reverted to original branch: $OriginalBranch"
    if ($Warnings.Count -gt 0) {
        Write-Host "Warnings:"
        foreach ($warning in $Warnings) {
            Write-Host "- $warning"
        }
    } else {
        Write-Host "Warnings: none"
    }
}
