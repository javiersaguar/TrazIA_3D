# Preserve the installed supervisor's identity and add recovery after a process stop.
param(
    [string]$TaskName = 'TrazIA-3D API',
    [Parameter(Mandatory = $true)][uri]$TunnelUrl
)

$ErrorActionPreference = 'Stop'
if (!$TunnelUrl.IsAbsoluteUri -or $TunnelUrl.Scheme -ne 'https' -or
    $TunnelUrl.AbsolutePath -ne '/' -or $TunnelUrl.Query -or $TunnelUrl.Fragment -or $TunnelUrl.UserInfo) {
    throw 'TunnelUrl debe ser el origen HTTPS de ngrok.'
}

$task = Get-ScheduledTask -TaskName $TaskName -TaskPath '\'
if ($task.Actions.Count -ne 1 -or $task.Actions[0].Arguments -notmatch 'serve_windows\.ps1') {
    throw 'La tarea indicada no ejecuta el supervisor de TrazIA-3D.'
}

$triggers = @($task.Triggers)
$periodic = $triggers | Where-Object {
    $_.Enabled -and $_.CimClass.CimClassName -eq 'MSFT_TaskTimeTrigger' -and
    $_.Repetition.Interval -eq 'PT1M' -and !$_.Repetition.Duration
}
if (!$periodic) {
    $triggers += New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes 1)
}

$action = $task.Actions[0]
$arguments = ($action.Arguments -replace '\s+-TunnelUrl\s+(?:"[^"]+"|\S+)', '').TrimEnd()
$arguments += ' -TunnelUrl ' + $TunnelUrl.GetLeftPart([System.UriPartial]::Authority)
if ($periodic -and $arguments -eq $action.Arguments) { return }

$actionParams = @{ Execute = $action.Execute; Argument = $arguments }
if ($action.WorkingDirectory) { $actionParams.WorkingDirectory = $action.WorkingDirectory }
$updatedAction = New-ScheduledTaskAction @actionParams
Set-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath `
    -Trigger $triggers -Action $updatedAction | Out-Null
