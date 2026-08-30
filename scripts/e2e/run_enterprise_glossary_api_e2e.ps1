$ErrorActionPreference = 'Stop'

$workspaceId = '22222222-2222-4222-8222-222222222222'
$dataSourceId = '44444444-4444-4444-8444-444444444444'
$tenantId = '11111111-1111-4111-8111-111111111111'
$userId = '33333333-3333-4333-8333-333333333333'
$userEmail = 'e2e.user@enterprise.test'

$token = docker compose exec -T backend python -c "from jose import jwt; import time; payload={'sub':'$userId','email':'$userEmail','type':'access','exp':int(time.time())+3600,'actor_id':'$userId','actor_role':'workspace_administrator','tenant_id':'$tenantId'}; print(jwt.encode(payload, 'your-jwt-secret-key-here-change-in-production', algorithm='HS256'))"
$token = $token.Trim()
$headers = @{ Authorization = "Bearer $token"; 'Content-Type' = 'application/json' }

Write-Host "Token generated for user $userEmail"

$datasets = @(
  @{ dataset_name='customer_master'; dataset_type='table'; physical_identifier='enterprise_qa.customer_master'; schema_name='enterprise_qa'; business_domain='Customer'; criticality='high' },
  @{ dataset_name='order_fact'; dataset_type='table'; physical_identifier='enterprise_qa.order_fact'; schema_name='enterprise_qa'; business_domain='Finance'; criticality='high' },
  @{ dataset_name='invoice_fact'; dataset_type='table'; physical_identifier='enterprise_qa.invoice_fact'; schema_name='enterprise_qa'; business_domain='Finance'; criticality='high' }
)

foreach ($ds in $datasets) {
  $body = @{
    data_source_id = $dataSourceId
    dataset_name = $ds.dataset_name
    dataset_type = $ds.dataset_type
    physical_identifier = $ds.physical_identifier
    schema_name = $ds.schema_name
    description = "E2E enterprise dataset for rule-builder validation"
    business_domain = $ds.business_domain
    criticality = $ds.criticality
  } | ConvertTo-Json

  try {
    $resp = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/workspaces/$workspaceId/datasets" -Headers $headers -Body $body
    $createdName = if ($resp.dataset_name) { $resp.dataset_name } elseif ($resp.dataset -and $resp.dataset.dataset_name) { $resp.dataset.dataset_name } else { $ds.dataset_name }
    Write-Host "Created dataset: $createdName"
  } catch {
    $raw = $_.ErrorDetails.Message
    if ($raw -and ($raw -match 'already exists' -or $raw -match 'DUPLICATE' -or $raw -match '409')) {
      Write-Host "Dataset already exists: $($ds.dataset_name)"
    } else {
      throw
    }
  }
}

Write-Host "Importing enterprise glossary CSV"
$csvPath = (Resolve-Path 'scripts/e2e/enterprise_glossary.csv').Path
$importOut = curl.exe -s -X POST "http://localhost:8000/api/v1/workspaces/$workspaceId/glossary/import-csv" -H "Authorization: Bearer $token" -F "file=@$csvPath"
Write-Host $importOut

Write-Host "Listing glossary terms"
$listOut = curl.exe -s -X GET "http://localhost:8000/api/v1/workspaces/$workspaceId/glossary?page=1&page_size=50" -H "Authorization: Bearer $token"
Write-Host $listOut

Write-Host "Running parse API (clear case)"
$parseBody1 = @{
  rule_text = 'Customer email must not be null'
  domain = 'Customer'
  severity = 'high'
} | ConvertTo-Json
$parseOut1 = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/workspaces/$workspaceId/rule-builder/parse" -Headers $headers -Body $parseBody1
$parseOut1 | ConvertTo-Json -Depth 8 | Write-Host

Write-Host "Running parse API (ambiguous/clarification case)"
$parseBody2 = @{
  rule_text = 'amount should match total'
  domain = 'Finance'
  severity = 'high'
} | ConvertTo-Json
$parseOut2 = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/workspaces/$workspaceId/rule-builder/parse" -Headers $headers -Body $parseBody2
$parseOut2 | ConvertTo-Json -Depth 8 | Write-Host
