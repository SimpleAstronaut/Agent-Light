# Keep browser launch in the caller's Windows environment. dsh.cmd applies
# the isolated runtime environment only inside its own child process.
$dshWebArguments = @($args)
# Agent Light local integration. Keep this outside dsh.cmd so its isolated
# environment and the browser launch behavior below stay owned by this wrapper.
$agentLightPatchPath = 'C:/Example/Agent Light/agent-light.patch.yml'
$agentLightAlreadyIncluded = $false
for ($argumentIndex = 0; $argumentIndex -lt $dshWebArguments.Count; $argumentIndex++) {
    $argument = [string]$dshWebArguments[$argumentIndex]
    $candidatePatch = $null
    if ($argument -eq '--patch' -and $argumentIndex + 1 -lt $dshWebArguments.Count) {
        $candidatePatch = [string]$dshWebArguments[$argumentIndex + 1]
    } elseif ($argument.StartsWith('--patch=')) {
        $candidatePatch = $argument.Substring(8)
    }
    if ($candidatePatch) {
        try {
            if ([IO.Path]::GetFullPath($candidatePatch) -eq [IO.Path]::GetFullPath($agentLightPatchPath)) {
                $agentLightAlreadyIncluded = $true
            }
        } catch {}
    }
}
if (-not $agentLightAlreadyIncluded) {
    if (Test-Path -LiteralPath $agentLightPatchPath -PathType Leaf) {
        $dshWebArguments = @('--patch', $agentLightPatchPath) + $dshWebArguments
    } else {
        Write-Warning 'Agent Light overlay was not found; starting DSH without the status-light plugin.'
    }
}
$dshShouldOpen = $dshWebArguments -notcontains '--no-open'
$dshBrowserOpened = $false

& "$PSScriptRoot\dsh.cmd" web @dshWebArguments --no-open | ForEach-Object {
    $dshOutputLine = [string]$_
    Write-Output $dshOutputLine
    if ($dshShouldOpen -and -not $dshBrowserOpened -and
        $dshOutputLine -match '^dsh web: (https?://\S+)$') {
        $dshBrowserOpened = $true
        try {
            Start-Process -FilePath $Matches[1] -ErrorAction Stop
        } catch {
            Write-Warning 'Could not open the default browser. Open the dsh web URL printed above manually.'
        }
    }
}
exit $LASTEXITCODE
