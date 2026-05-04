# API Tests

Copy-paste PowerShell checks for the FastAPI backend.

Start backend first:

```powershell
$env:SQLITE_DB_PATH="D:/PropScore/data/propscore.sqlite"
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
$env:OLLAMA_MODEL="qwen2.5:7b"
$env:OLLAMA_FALLBACK_MODEL="llama3.2:3b"
$env:OLLAMA_FAST_MODEL="llama3.2:3b"
$env:OLLAMA_TIMEOUT_SECONDS="150"
$env:OLLAMA_FAST_TIMEOUT_SECONDS="300"
$env:LLM_DEBUG="true"
python -m uvicorn backend.main:app --reload --port 8000
```

## A. Health Endpoint

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

Expected fields:

- `status`
- backend/database health details if configured

## B. Stage 1 Context

```powershell
$body = @{
  lat = 19.1136
  lon = 72.8697
  propertyType = "Residential"
  subtype = "2BHK"
} | ConvertTo-Json -Depth 6

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/stage1/resolve-context" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Expected fields:

- `source`
- `locality`
- `bucketAssignment`
- `marketNorms`
- `circleRate`

## C. Historical Similar Cases

```powershell
$body = @{
  microMarketId = "MM-MUM-ANDHERI-E"
  localityName = "Andheri East"
  propertyType = "Residential"
  subtype = "2BHK"
  sizeSqft = 200
  ageBucket = "Mid-age"
  legalProfile = "Unknown"
  baseConfidence = 0.68
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/historical/similar-cases" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Expected fields:

- `source = sqlite_historical_cases`
- `overallSignal`
- `confidenceAdjustment`
- `similarCases`
- `finalConfidence`

## D. Portfolio Concentration Risk

```powershell
$body = @{
  microMarketId = "MM-MUM-ANDHERI-E"
  localityName = "Andheri East"
  propertyType = "Residential"
  subtype = "2BHK"
  estimatedMarketValue = 12000000
  baseLtv = 0.65
  liquidityTier = "High"
  liquidityIndex = 0.756
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/portfolio/concentration-risk" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Expected fields:

- `source = sqlite_portfolio_exposure`
- `portfolioSummary.portfolioRiskScore`
- `portfolioSummary.riskLevel`
- `portfolioSummary.recommendedLtv`
- `riskFlags`
- `decisionImpact`

## E. LLM Underwriter Summary

This test uses `mode = "fast"` so the backend calls `llama3.2:3b` first.

```powershell
$body = @{
  mode = "fast"
  caseId = "TEST-001"
  stage1 = @{
    normalizedPropertyProfile = @{
      address = "Andheri East, Mumbai"
      propertyType = "Residential"
      subtype = "2BHK"
      sizeSqft = 200
      ageBucket = "Mid-age"
      legalStatus = "unknown"
      titleClarity = "weak"
      imageCount = 0
    }
    bucketAssignment = @{
      microMarketBucket = @{
        label = "Andheri East"
        commonSizeBand = "653-1272 sqft"
        liquidityNorm = "High"
        localPriceBand = "INR 19,976-27,254/sqft"
      }
    }
  }
  stage2Output = @{
    decision = "MANUAL_REVIEW"
    scores = @{
      dataSufficiencyScore = 0.82
      anomalyScore = 72
      suspicionScore = 48
    }
    flags = @("Property size is much smaller than similar homes here")
  }
  valuation = @{
    marketValue = 12000000
    distressValue = 9300000
    timeToLiquidateDays = 120
    confidenceScore = 0.68
  }
  historicalCaseSummary = @{
    source = "sqlite_historical_cases"
    confidenceAdjustment = 0.037
    overallSignal = "Positive"
    displayedCount = 2
  }
  portfolioRiskSummary = @{
    source = "sqlite_portfolio_exposure"
    portfolioSummary = @{
      riskLevel = "Moderate"
      portfolioRiskScore = 45
      recommendedLtv = 0.61
      reviewRecommendation = "Proceed with portfolio watch."
    }
    riskFlags = @("Property type exposure materially exceeds internal policy cap")
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/llm/underwriter-summary" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

Expected fields:

- `source = ollama` if llama succeeds, or `rule_based_fallback` if local LLM is unavailable
- `modelUsed = llama3.2:3b` for successful fast mode
- `mode = fast`
- `summaryQuality`
- `summary.executiveSummary`
- `summary.keyStrengths`
- `summary.keyRisks`
- `summary.recommendedEvidence`
- `summary.reviewRoute`
- `summary.suggestedLenderAction`
- `summary.numericDecisionBoundary`
- `llmDebug` only when `LLM_DEBUG=true`
