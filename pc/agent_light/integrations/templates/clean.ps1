# Keep browser launch in the caller's Windows environment. dsh.cmd applies
# the isolated runtime environment only inside its own child process.
$dshWebArguments = @($args)
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
