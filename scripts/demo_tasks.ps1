# Run while python app.py is running in a DIFFERENT terminal.
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:5000'
$email = 'member2_' + (Get-Date -Format 'yyyyMMddHHmmssfff') + '@example.com'
$password = 'TestPass123!'
Write-Host "Using local demo account: $email"
$signup = @{ name='Member 2 Tester'; email=$email; password=$password } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/api/signup" -Method POST -ContentType 'application/json' -Body $signup | Out-Host
$login = @{ email=$email; password=$password } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/api/login" -Method POST -ContentType 'application/json' -Body $login -SessionVariable webSession | Out-Host
$body = @{ title='Member 2 CRUD task'; description='Full workflow'; category='Work'; priority='High'; due_date='2026-10-30' } | ConvertTo-Json
$t = Invoke-RestMethod -Uri "$base/api/tasks" -Method POST -ContentType 'application/json' -Body $body -WebSession $webSession
Write-Host "CREATED task ID $($t.id)"; $t | Format-List
Invoke-RestMethod -Uri "$base/api/tasks" -Method GET -WebSession $webSession | Format-Table
Invoke-RestMethod -Uri "$base/api/tasks/$($t.id)" -Method GET -WebSession $webSession | Format-List
$update = @{ title='Member 2 UPDATED task'; priority='Medium' } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/api/tasks/$($t.id)" -Method PUT -ContentType 'application/json' -Body $update -WebSession $webSession | Format-List
$status = @{ status='completed' } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/api/tasks/$($t.id)/status" -Method PATCH -ContentType 'application/json' -Body $status -WebSession $webSession | Format-List
Invoke-RestMethod -Uri "$base/api/tasks/$($t.id)" -Method DELETE -WebSession $webSession | Format-List
Write-Host 'PASS: login, create, list, detail, edit, complete and delete. Manager-only assignment covered by automated tests.'
