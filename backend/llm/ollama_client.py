import json
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, Optional
from loguru import logger


SUMMARY_FIELDS = [
    "executiveSummary",
    "keyStrengths",
    "keyRisks",
    "recommendedEvidence",
    "reviewRoute",
    "suggestedLenderAction",
    "confidenceNarrative",
    "portfolioNarrative",
    "numericDecisionBoundary",
]

NUMERIC_BOUNDARY_NOTE = (
    "All numeric scores, value estimates, LTV adjustments, and risk flags are computed by "
    "deterministic engines. The AI summary only explains those outputs and recommends evidence."
)

RULE_BASED_BOUNDARY_NOTE = NUMERIC_BOUNDARY_NOTE


class OllamaSummaryError(Exception):
    """Raised when an Ollama summary call or response cannot be used."""


def generate_underwriter_summary(
    payload: Dict[str, Any],
    *,
    base_url: str,
    primary_model: str,
    fallback_model: str,
    fast_model: Optional[str] = None,
    timeout_seconds: float,
    fast_timeout_seconds: float,
    mode: str = "auto",
    debug_enabled: bool = False,
) -> Dict[str, Any]:
    prompt = build_underwriter_prompt(payload)
    fast_prompt = build_fast_underwriter_prompt(payload)
    attempts: list[Dict[str, Any]] = []
    selected_mode = normalize_summary_mode(mode)
    selected_fast_model = fast_model or fallback_model
    if debug_enabled:
        logger.info(
            "AI underwriter generation mode={} payload_bytes={} primary={} fallback={} fast={} timeout={}s fast_timeout={}s",
            selected_mode,
            len(json.dumps(payload, ensure_ascii=False, default=str)),
            primary_model,
            fallback_model,
            selected_fast_model,
            timeout_seconds,
            fast_timeout_seconds,
        )

    if selected_mode == "fast":
        fast_summary, fast_error = _try_model(
            base_url=base_url,
            model=selected_fast_model,
            prompt=fast_prompt,
            timeout_seconds=fast_timeout_seconds,
            payload=payload,
            prefer_plain_json=True,
            retry_after_timeout=False,
        )
        attempts.append(_attempt_debug(selected_fast_model, fast_summary, fast_error))
        _log_attempt(debug_enabled, selected_mode, selected_fast_model, fast_timeout_seconds, fast_summary, fast_error)
        if fast_error:
            logger.warning(f"AI underwriter fast model failed: {selected_fast_model}: {fast_error}")
        if fast_summary is not None:
            logger.info(f"AI underwriter fast summary generated with model: {selected_fast_model}")
            response = _build_success_response(
                mode="fast",
                model_used=selected_fast_model,
                summary=fast_summary,
                summary_quality="fast",
                fallback_used=False,
                upgrade_available=_upgrade_possible(primary_model, selected_fast_model),
            )
            return _with_debug(
                response,
                debug_enabled,
                mode=selected_mode,
                primary_model=primary_model,
                fallback_model=fallback_model,
                fast_model=selected_fast_model,
                timeout_seconds=timeout_seconds,
                fast_timeout_seconds=fast_timeout_seconds,
                attempts=attempts,
            )

        response = _build_fallback_response(
            payload,
            mode="fast",
            upgrade_available=_upgrade_possible(primary_model, selected_fast_model),
        )
        if debug_enabled:
            logger.info("AI underwriter mode=fast using rule_based_fallback after failed fast attempt")
        return _with_debug(
            response,
            debug_enabled,
            mode=selected_mode,
            primary_model=primary_model,
            fallback_model=fallback_model,
            fast_model=selected_fast_model,
            timeout_seconds=timeout_seconds,
            fast_timeout_seconds=fast_timeout_seconds,
            attempts=attempts,
        )

    if selected_mode == "enhanced":
        enhanced_summary, enhanced_error = _try_model(
            base_url=base_url,
            model=primary_model,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            payload=payload,
        )
        attempts.append(_attempt_debug(primary_model, enhanced_summary, enhanced_error))
        _log_attempt(debug_enabled, selected_mode, primary_model, timeout_seconds, enhanced_summary, enhanced_error)
        if enhanced_error:
            logger.warning(f"AI underwriter enhanced model failed: {primary_model}: {enhanced_error}")
        if enhanced_summary is not None:
            logger.info(f"AI underwriter enhanced summary generated with model: {primary_model}")
            response = _build_success_response(
                mode="enhanced",
                model_used=primary_model,
                summary=enhanced_summary,
                summary_quality="enhanced",
                fallback_used=False,
                upgrade_available=False,
            )
            return _with_debug(
                response,
                debug_enabled,
                mode=selected_mode,
                primary_model=primary_model,
                fallback_model=fallback_model,
                fast_model=selected_fast_model,
                timeout_seconds=timeout_seconds,
                fast_timeout_seconds=fast_timeout_seconds,
                attempts=attempts,
            )

        response = _build_unavailable_response(
            mode="enhanced",
            model_used=primary_model,
            error="Enhanced summary unavailable",
        )
        if debug_enabled:
            logger.info("AI underwriter mode=enhanced returning unavailable after enhanced attempt failed")
        return _with_debug(
            response,
            debug_enabled,
            mode=selected_mode,
            primary_model=primary_model,
            fallback_model=fallback_model,
            fast_model=selected_fast_model,
            timeout_seconds=timeout_seconds,
            fast_timeout_seconds=fast_timeout_seconds,
            attempts=attempts,
        )

    primary_summary, primary_error = _try_model(
        base_url=base_url,
        model=primary_model,
        prompt=prompt,
        timeout_seconds=timeout_seconds,
        payload=payload,
    )
    attempts.append(_attempt_debug(primary_model, primary_summary, primary_error))
    _log_attempt(debug_enabled, selected_mode, primary_model, timeout_seconds, primary_summary, primary_error)
    if primary_error:
        logger.warning(f"AI underwriter primary model failed: {primary_model}: {primary_error}")
    if primary_summary is not None:
        logger.info(f"AI underwriter summary generated with primary model: {primary_model}")
        response = _build_success_response(
            mode="auto",
            model_used=primary_model,
            summary=primary_summary,
            summary_quality="enhanced",
            fallback_used=False,
            upgrade_available=False,
        )
        return _with_debug(
            response,
            debug_enabled,
            mode=selected_mode,
            primary_model=primary_model,
            fallback_model=fallback_model,
            fast_model=selected_fast_model,
            timeout_seconds=timeout_seconds,
            fast_timeout_seconds=fast_timeout_seconds,
            attempts=attempts,
        )

    fallback_summary, fallback_error = _try_model(
        base_url=base_url,
        model=fallback_model,
        prompt=prompt,
        timeout_seconds=timeout_seconds,
        payload=payload,
    )
    attempts.append(_attempt_debug(fallback_model, fallback_summary, fallback_error))
    _log_attempt(debug_enabled, selected_mode, fallback_model, timeout_seconds, fallback_summary, fallback_error)
    if fallback_error:
        logger.warning(f"AI underwriter fallback model failed: {fallback_model}: {fallback_error}")
    if fallback_summary is not None:
        logger.info(f"AI underwriter summary generated with fallback model: {fallback_model}")
        response = _build_success_response(
            mode="auto",
            model_used=fallback_model,
            summary=fallback_summary,
            summary_quality="fast",
            fallback_used=True,
            upgrade_available=False,
        )
        return _with_debug(
            response,
            debug_enabled,
            mode=selected_mode,
            primary_model=primary_model,
            fallback_model=fallback_model,
            fast_model=selected_fast_model,
            timeout_seconds=timeout_seconds,
            fast_timeout_seconds=fast_timeout_seconds,
            attempts=attempts,
        )

    response = _build_fallback_response(payload, mode="auto", upgrade_available=False)
    if debug_enabled:
        logger.info("AI underwriter mode=auto using rule_based_fallback after primary and fallback failed")
    return _with_debug(
        response,
        debug_enabled,
        mode=selected_mode,
        primary_model=primary_model,
        fallback_model=fallback_model,
        fast_model=selected_fast_model,
        timeout_seconds=timeout_seconds,
        fast_timeout_seconds=fast_timeout_seconds,
        attempts=attempts,
    )


def _try_model(
    *,
    base_url: str,
    model: str,
    prompt: str,
    timeout_seconds: float,
    payload: Dict[str, Any],
    prefer_plain_json: bool = False,
    retry_after_timeout: bool = True,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not model:
        return None, "Model name is empty"

    first_uses_json_format = not prefer_plain_json
    first_prompt = prompt if first_uses_json_format else build_no_format_retry_prompt(prompt)
    try:
        response_text = call_ollama(
            base_url=base_url,
            model=model,
            prompt=first_prompt,
            timeout_seconds=timeout_seconds,
            request_json_format=first_uses_json_format,
        )
    except OllamaSummaryError as exc:
        if _is_timeout_error(exc) or not retry_after_timeout:
            return None, str(exc)
        if "format" not in str(exc).lower() and first_uses_json_format:
            return None, str(exc)
        try:
            response_text = call_ollama(
                base_url=base_url,
                model=model,
                prompt=build_no_format_retry_prompt(prompt),
                timeout_seconds=timeout_seconds,
                request_json_format=not first_uses_json_format,
            )
        except OllamaSummaryError as retry_exc:
            return None, f"{exc}; no-format retry failed: {retry_exc}"

    try:
        return parse_model_json(response_text, payload), None
    except OllamaSummaryError as first_parse_exc:
        if not retry_after_timeout:
            return None, str(first_parse_exc)
        try:
            retry_text = call_ollama(
                base_url=base_url,
                model=model,
                prompt=build_no_format_retry_prompt(prompt),
                timeout_seconds=timeout_seconds,
                request_json_format=not first_uses_json_format,
            )
            return parse_model_json(retry_text, payload), None
        except OllamaSummaryError as retry_exc:
            return None, f"{first_parse_exc}; no-format retry failed: {retry_exc}"


def _is_timeout_error(error: Exception) -> bool:
    message = str(error).lower()
    return "timed out" in message or "timeout" in message


def _attempt_debug(
    model: str,
    summary: Optional[Dict[str, Any]],
    error: Optional[str],
) -> Dict[str, Any]:
    attempt = {
        "model": model,
        "status": "success" if summary is not None else "failed",
    }
    if error:
        attempt["error"] = error
    return attempt


def _log_attempt(
    debug_enabled: bool,
    mode: str,
    model: str,
    timeout_seconds: float,
    summary: Optional[Dict[str, Any]],
    error: Optional[str],
) -> None:
    if not debug_enabled:
        return
    logger.info(
        "AI underwriter attempt mode={} model={} timeout={}s status={} error={}",
        mode,
        model,
        timeout_seconds,
        "success" if summary is not None else "failed",
        error or "",
    )


def normalize_summary_mode(mode: Optional[str]) -> str:
    normalized = str(mode or "auto").strip().lower()
    if normalized in {"fast", "enhanced", "auto"}:
        return normalized
    return "auto"


def _upgrade_possible(primary_model: str, fast_model: str) -> bool:
    return bool(primary_model and fast_model and primary_model != fast_model)


def _build_success_response(
    *,
    mode: str,
    model_used: str,
    summary: Dict[str, Any],
    summary_quality: str,
    fallback_used: bool,
    upgrade_available: bool,
) -> Dict[str, Any]:
    return {
        "source": "ollama",
        "modelUsed": model_used,
        "fallbackUsed": fallback_used,
        "mode": mode,
        "summaryQuality": summary_quality,
        "upgradeAvailable": upgrade_available,
        "summary": summary,
    }


def _build_fallback_response(
    payload: Dict[str, Any],
    *,
    mode: str,
    upgrade_available: bool,
) -> Dict[str, Any]:
    return {
        "source": "rule_based_fallback",
        "modelUsed": None,
        "fallbackUsed": True,
        "mode": mode,
        "summaryQuality": "fallback",
        "upgradeAvailable": upgrade_available,
        "summary": build_rule_based_fallback(payload),
    }


def _build_unavailable_response(
    *,
    mode: str,
    model_used: Optional[str],
    error: str,
) -> Dict[str, Any]:
    return {
        "source": "unavailable",
        "modelUsed": model_used,
        "fallbackUsed": False,
        "mode": mode,
        "summaryQuality": "unavailable",
        "upgradeAvailable": False,
        "error": error,
        "summary": None,
    }


def _with_debug(
    response: Dict[str, Any],
    debug_enabled: bool,
    *,
    mode: str,
    primary_model: str,
    fallback_model: str,
    fast_model: str,
    timeout_seconds: float,
    fast_timeout_seconds: float,
    attempts: list[Dict[str, Any]],
) -> Dict[str, Any]:
    if not debug_enabled:
        return response
    return {
        **response,
        "llmDebug": {
            "mode": mode,
            "primaryModel": primary_model,
            "fallbackModel": fallback_model,
            "fastModel": fast_model,
            "timeoutSeconds": timeout_seconds,
            "fastTimeoutSeconds": fast_timeout_seconds,
            "attempts": attempts,
        },
    }


def call_ollama(
    *,
    base_url: str,
    model: str,
    prompt: str,
    timeout_seconds: float,
    request_json_format: bool = True,
) -> str:
    normalized_base_url = str(base_url).strip()
    if normalized_base_url.startswith("http://localhost"):
        normalized_base_url = normalized_base_url.replace("http://localhost", "http://127.0.0.1", 1)
    elif normalized_base_url.startswith("https://localhost"):
        normalized_base_url = normalized_base_url.replace("https://localhost", "https://127.0.0.1", 1)

    url = f"{normalized_base_url.rstrip('/')}/api/generate"
    logger.info(
        f"Calling Ollama underwriter model={model} "
        f"format={'json' if request_json_format else 'plain'} timeout={timeout_seconds}s"
    )
    body: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "num_predict": 850,
        },
    }
    if request_json_format:
        body["format"] = "json"

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise OllamaSummaryError(f"Ollama HTTP {exc.code}: {error_body}") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise OllamaSummaryError(f"Ollama request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OllamaSummaryError("Ollama returned invalid HTTP JSON") from exc

    response_text = response_payload.get("response")
    if not isinstance(response_text, str) or not response_text.strip():
        raise OllamaSummaryError("Ollama response text was empty")
    return response_text.strip()


def build_underwriter_prompt(payload: Dict[str, Any]) -> str:
    structured_case = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return f"""System instruction:
You are an underwriting assistant for collateral-backed lending. You explain already-computed system outputs. You must not invent numeric values. You must not override deterministic scores. Use only the structured input provided.

User/task instruction:
Given the structured collateral case, produce JSON with:
- executiveSummary
- keyStrengths
- keyRisks
- recommendedEvidence
- reviewRoute
- suggestedLenderAction
- confidenceNarrative
- portfolioNarrative
- numericDecisionBoundary

Rules:
1. Do not invent new values.
2. Refer to numbers only if they exist in the input.
3. Keep explanations clear for a lender / underwriter.
4. If risk is high or manual review is indicated, recommend the appropriate review route.
5. If legal/title evidence is missing or weak, recommend legal evidence.
6. If size anomaly exists, recommend size verification.
7. If portfolio concentration flags exist, mention them separately from property-level risks.
8. Keep response concise and useful.
9. Return valid JSON only.
10. Always produce at least 2 keyStrengths when positive signals exist in the structured input.
11. If historicalCaseSummary.overallSignal is Positive, mention it as a key strength.
12. If micro-market liquidity is High, Medium, Moderate, or liquidityIndex is at least 0.70, mention liquidity as a key strength.
13. If valuation.confidenceScore exists, mention deterministic confidence availability as a strength; do not describe it as LLM-generated confidence.
14. Do not recommend additional collateral unless the structured input explicitly says collateral is insufficient.
15. Do not use vague lender actions such as "consider additional collateral"; tie actions to the deterministic decision, review route, and evidence requirements.
16. If manual review is required, explain the review reason from Stage 2 flags or Stage 2 decision text.
17. Recommended evidence must be specific and tied to flags: size anomaly -> verify carpet/built-up area; legal/title uncertainty -> upload title/legal evidence; missing images -> upload interior/exterior images; portfolio concentration or senior review -> document senior credit review.
18. numericDecisionBoundary must state that numeric scores, value estimates, LTV adjustments, and risk flags are deterministic and that AI only explains outputs and recommends evidence.

Return exactly this JSON shape:
{{
  "executiveSummary": "string",
  "keyStrengths": ["string"],
  "keyRisks": ["string"],
  "recommendedEvidence": ["string"],
  "reviewRoute": "string",
  "suggestedLenderAction": "string",
  "confidenceNarrative": "string",
  "portfolioNarrative": "string",
  "numericDecisionBoundary": "string"
}}

Structured collateral case:
{structured_case}
"""


def build_fast_underwriter_prompt(payload: Dict[str, Any]) -> str:
    structured_case = json.dumps(_compact_fast_payload(payload), ensure_ascii=False, separators=(",", ":"), default=str)
    return f"""You are an underwriting assistant for collateral-backed lending.
Explain only the deterministic structured outputs provided below.
Do not calculate, change, or invent numeric values. Do not recommend additional collateral unless the input explicitly says collateral is insufficient.

Return one valid JSON object only with exactly these keys:
executiveSummary, keyStrengths, keyRisks, recommendedEvidence, reviewRoute, suggestedLenderAction, confidenceNarrative, portfolioNarrative, numericDecisionBoundary.

Rules:
- Write for a lender/underwriter.
- Mention high/medium liquidity and positive historical signal as strengths when present.
- Mention Stage 2 flags and portfolio concentration flags as separate risks when present.
- Evidence must be tied to flags: size anomaly -> verify carpet/built-up area; legal/title uncertainty -> upload title/legal evidence; missing images -> upload interior/exterior images; portfolio concentration -> document senior credit review.
- numericDecisionBoundary must say numeric scores, value estimates, LTV adjustments, and risk flags are deterministic; AI only explains outputs and recommends evidence.

Structured case JSON:
{structured_case}
"""


def _compact_fast_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    stage1 = payload.get("stage1") or {}
    stage2 = payload.get("stage2Output") or {}
    valuation = payload.get("valuation") or {}
    historical = payload.get("historicalCaseSummary") or {}
    portfolio = payload.get("portfolioRiskSummary") or {}
    profile = _stage1_profile(stage1)
    bucket = _stage1_micro_market_bucket(stage1)
    portfolio_summary = _portfolio_summary(portfolio)

    return {
        "caseId": payload.get("caseId"),
        "property": {
            "address": profile.get("address"),
            "propertyType": profile.get("propertyType"),
            "subtype": profile.get("subtype"),
            "sizeSqft": profile.get("sizeSqft"),
            "ageBucket": profile.get("ageBucket"),
            "legalStatus": profile.get("legalStatus") or profile.get("titleClarity"),
            "imageCount": profile.get("imageCount"),
        },
        "market": {
            "microMarket": bucket.get("label") or bucket.get("id"),
            "commonSizeBand": bucket.get("commonSizeBand"),
            "liquidityNorm": bucket.get("liquidityNorm"),
            "localPriceBand": bucket.get("localPriceBand"),
        },
        "stage2": {
            "decision": stage2.get("decision"),
            "scores": stage2.get("scores") or {},
            "flags": (stage2.get("flags") or [])[:4],
        },
        "valuation": {
            "marketValue": valuation.get("marketValue"),
            "distressValue": valuation.get("distressValue"),
            "timeToLiquidateDays": valuation.get("timeToLiquidateDays"),
            "confidenceScore": valuation.get("confidenceScore"),
        },
        "historical": {
            "source": historical.get("source"),
            "overallSignal": historical.get("overallSignal"),
            "confidenceAdjustment": historical.get("confidenceAdjustment"),
            "displayedCount": historical.get("displayedCount"),
        },
        "portfolio": {
            "source": portfolio.get("source"),
            "riskLevel": portfolio_summary.get("riskLevel"),
            "portfolioRiskScore": portfolio_summary.get("portfolioRiskScore"),
            "recommendedLtv": portfolio_summary.get("recommendedLtv"),
            "reviewRecommendation": portfolio_summary.get("reviewRecommendation"),
            "riskFlags": (portfolio.get("riskFlags") or [])[:4],
        },
    }


def build_no_format_retry_prompt(prompt: str) -> str:
    return f"""{prompt}

Critical retry instruction:
Return valid JSON only. Do not include markdown fences, prose before the JSON, or prose after the JSON.
"""


def parse_model_json(response_text: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    parsed = _parse_json_object(response_text)
    if not isinstance(parsed, dict):
        raise OllamaSummaryError("Model JSON was not an object")

    missing = [field for field in SUMMARY_FIELDS if field not in parsed]
    if missing:
        raise OllamaSummaryError(f"Model JSON missing fields: {', '.join(missing)}")

    summary: Dict[str, Any] = {}
    for field in SUMMARY_FIELDS:
        value = parsed.get(field)
        if field in {"keyStrengths", "keyRisks", "recommendedEvidence"}:
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise OllamaSummaryError(f"Model field {field} must be a string array")
            summary[field] = [item.strip() for item in value if item.strip()]
        else:
            if not isinstance(value, str):
                raise OllamaSummaryError(f"Model field {field} must be a string")
            summary[field] = value.strip()

    return sanitize_summary(summary, payload or {})


def sanitize_summary(summary: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    stage1 = payload.get("stage1") or {}
    stage2 = payload.get("stage2Output") or {}
    valuation = payload.get("valuation") or {}
    historical = payload.get("historicalCaseSummary") or {}
    portfolio = payload.get("portfolioRiskSummary") or {}
    fallback = build_rule_based_fallback(payload)

    cleaned: Dict[str, Any] = {}
    for field in SUMMARY_FIELDS:
        if field in {"keyStrengths", "keyRisks", "recommendedEvidence"}:
            value = summary.get(field)
            cleaned[field] = _dedupe([item for item in value if isinstance(item, str)]) if isinstance(value, list) else []
        else:
            value = summary.get(field)
            cleaned[field] = value.strip() if isinstance(value, str) else ""

    if not cleaned["keyStrengths"]:
        cleaned["keyStrengths"] = _derive_strengths(stage1, stage2, valuation, historical, portfolio)
    if not cleaned["keyRisks"]:
        cleaned["keyRisks"] = _derive_risks(stage2, portfolio)
    if not cleaned["recommendedEvidence"]:
        cleaned["recommendedEvidence"] = _derive_evidence(stage1, stage2, portfolio)

    for field in {"executiveSummary", "confidenceNarrative", "portfolioNarrative"}:
        if not cleaned[field]:
            cleaned[field] = fallback[field]

    derived_review_route = _derive_review_route(stage2, portfolio)
    if not cleaned["reviewRoute"] or _route_is_under_specific(cleaned["reviewRoute"]):
        cleaned["reviewRoute"] = derived_review_route
    if _contains_unsupported_lender_action(cleaned["suggestedLenderAction"], payload):
        cleaned["suggestedLenderAction"] = "Proceed only after completing the recommended review and evidence checks."
    elif not cleaned["suggestedLenderAction"]:
        cleaned["suggestedLenderAction"] = _safe_lender_action(stage2, portfolio)

    cleaned["numericDecisionBoundary"] = NUMERIC_BOUNDARY_NOTE
    return cleaned


def _parse_json_object(response_text: str) -> Any:
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(response_text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(response_text[index:])
            return parsed
        except json.JSONDecodeError:
            continue
    raise OllamaSummaryError("Could not extract JSON object from model response")


def build_rule_based_fallback(payload: Dict[str, Any]) -> Dict[str, Any]:
    stage1 = payload.get("stage1") or {}
    stage2 = payload.get("stage2Output") or {}
    valuation = payload.get("valuation") or {}
    historical = payload.get("historicalCaseSummary") or {}
    portfolio = payload.get("portfolioRiskSummary") or {}

    strengths = _derive_strengths(stage1, stage2, valuation, historical, portfolio)
    risks = _derive_risks(stage2, portfolio)
    evidence = _derive_evidence(stage1, stage2, portfolio)
    review_route = _derive_review_route(stage2, portfolio)

    return {
        "executiveSummary": (
            "AI-generated summary was unavailable. The structured collateral assessment remains available."
        ),
        "keyStrengths": strengths,
        "keyRisks": risks,
        "recommendedEvidence": evidence,
        "reviewRoute": review_route,
        "suggestedLenderAction": _derive_lender_action(stage2, portfolio),
        "confidenceNarrative": "Refer to deterministic confidence score and score breakdown.",
        "portfolioNarrative": "Refer to portfolio concentration section.",
        "numericDecisionBoundary": RULE_BASED_BOUNDARY_NOTE,
    }


def _derive_strengths(
    stage1: Dict[str, Any],
    stage2: Dict[str, Any],
    valuation: Dict[str, Any],
    historical: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> list[str]:
    strengths: list[str] = []
    profile = _stage1_profile(stage1)
    bucket = _stage1_micro_market_bucket(stage1)
    scores = _stage2_scores(stage2)
    decision = str(stage2.get("decision") or "")
    portfolio_summary = _portfolio_summary(portfolio)

    completeness = profile.get("completenessStatus") or {}
    if completeness.get("mandatoryComplete"):
        strengths.append("Mandatory intake fields are complete.")
    liquidity_norm = str(bucket.get("liquidityNorm") or stage1.get("liquidityNorm") or "").strip().lower()
    liquidity_index = _number_or_none(
        bucket.get("liquidityIndex")
        or (stage1.get("marketNorms") or {}).get("liquidityIndex")
        or stage1.get("liquidityIndex")
    )
    if liquidity_norm in {"high", "medium", "moderate", "medium-high"} or (liquidity_index is not None and liquidity_index >= 0.70):
        strengths.append("Micro-market liquidity support is strong.")
    if historical.get("overallSignal") == "Positive":
        strengths.append("Similar historical cases show a positive reliability signal.")
    if portfolio_summary.get("riskLevel") in {"Low", "Moderate"}:
        strengths.append("Portfolio risk is not classified as high at the overall level.")
    if decision in {"ACCEPT_CLEAN", "ACCEPT_WARNING"}:
        strengths.append(f"Stage 2 deterministic decision is {decision}.")
    if valuation.get("confidenceScore") is not None:
        strengths.append("A deterministic confidence score is available for review.")
    if _number_or_none(scores.get("dataSufficiencyScore")) is not None and _number_or_none(scores.get("dataSufficiencyScore")) >= 0.70:
        strengths.append("Local data sufficiency is strong enough to support screening.")

    return strengths or ["Structured valuation, verification, history, and portfolio outputs are available."]


def _derive_risks(stage2: Dict[str, Any], portfolio: Dict[str, Any]) -> list[str]:
    risks: list[str] = []
    decision = str(stage2.get("decision") or "")
    flags = stage2.get("flags") or []
    portfolio_flags = portfolio.get("riskFlags") or []
    scores = _stage2_scores(stage2)

    for flag in flags[:4]:
        if isinstance(flag, str):
            risks.append(flag)
        elif isinstance(flag, dict):
            risks.append(
                flag.get("explanation")
                or flag.get("text")
                or flag.get("title")
                or "Stage 2 review flag present."
            )

    if decision in {"MANUAL_REVIEW", "REJECT_BLOCK", "ACCEPT_CONFIDENCE_PENALTY"}:
        risks.append(f"Stage 2 deterministic decision is {decision}.")
    anomaly_score = _number_or_none(scores.get("anomalyScore") or stage2.get("anomalyScore"))
    suspicion_score = _number_or_none(scores.get("suspicionScore") or stage2.get("suspicionScore"))
    if anomaly_score is not None and anomaly_score >= 70:
        risks.append("Anomaly score is elevated and requires underwriter attention.")
    if suspicion_score is not None and suspicion_score >= 40:
        risks.append("Suspicion score is elevated and supports manual review.")

    for flag in portfolio_flags[:3]:
        if isinstance(flag, str):
            risks.append(f"Portfolio: {flag}")

    return _dedupe(risks) or ["No high-signal property or portfolio risks surfaced from supplied deterministic outputs."]


def _derive_evidence(stage1: Dict[str, Any], stage2: Dict[str, Any], portfolio: Dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    profile = _stage1_profile(stage1)
    flags_text = " ".join(_flatten_flag_text(stage2.get("flags") or [])).lower()
    completeness = profile.get("completenessStatus") or {}
    missing = " ".join(completeness.get("missingFields") or []).lower()
    legal_status = str(profile.get("legalStatus") or "").lower()
    title_clarity = str(profile.get("titleClarity") or "").lower()
    image_count = int(profile.get("imageCount") or 0)

    if any(token in flags_text for token in ["size", "area", "sqft"]) or "size" in missing:
        evidence.append("Verify carpet area / built-up area with supporting measurement evidence.")
    if stage2.get("decision") == "MANUAL_REVIEW":
        evidence.append("Complete field verification for the manual review trigger.")
    if (
        "legal" in flags_text
        or "title" in flags_text
        or "legal" in missing
        or "title" in missing
        or legal_status in {"", "not_provided", "unknown", "disputed"}
        or title_clarity in {"", "not_provided", "unknown", "unclear"}
    ):
        evidence.append("Upload title document and legal clearance evidence.")
    if image_count == 0 or "image" in flags_text or "visual" in flags_text:
        evidence.append("Upload exterior/interior property images or complete a field verification visit.")
    if portfolio.get("riskFlags") or portfolio.get("decisionImpact", {}).get("seniorReviewRequired"):
        evidence.append("Document senior credit review for portfolio concentration flags.")
    if "rental" in missing:
        evidence.append("Provide recent rental proof if rental income is part of the credit view.")

    return _dedupe(evidence) or ["Confirm standard KYC, property ownership, and field-verification evidence."]


def _derive_review_route(stage2: Dict[str, Any], portfolio: Dict[str, Any]) -> str:
    routes: list[str] = []
    decision = str(stage2.get("decision") or "")
    flags_text = " ".join(_flatten_flag_text(stage2.get("flags") or [])).lower()

    if decision in {"MANUAL_REVIEW", "REJECT_BLOCK", "ACCEPT_CONFIDENCE_PENALTY"}:
        routes.append("Field Verification")
    if "legal" in flags_text or "title" in flags_text or decision == "REJECT_BLOCK":
        routes.append("Legal Review")
    if any(token in flags_text for token in ["size", "area", "sqft"]):
        routes.append("Size Verification")
    if portfolio.get("decisionImpact", {}).get("seniorReviewRequired") or portfolio.get("riskFlags"):
        routes.append("Senior Credit Review")

    return " + ".join(_dedupe(routes)) or "Standard Underwriting Review"


def _route_is_under_specific(route: str) -> bool:
    normalized = str(route or "").strip().lower()
    return normalized in {
        "ok",
        "review",
        "manual review",
        "standard review",
        "underwriter review",
        "manual",
        "not available",
    }


def _derive_lender_action(stage2: Dict[str, Any], portfolio: Dict[str, Any]) -> str:
    return _safe_lender_action(stage2, portfolio)


def _safe_lender_action(stage2: Dict[str, Any], portfolio: Dict[str, Any]) -> str:
    decision = str(stage2.get("decision") or "")
    portfolio_summary = _portfolio_summary(portfolio)
    portfolio_level = portfolio_summary.get("riskLevel")

    if decision == "REJECT_BLOCK":
        return "Do not proceed until blocking issues are resolved."
    if decision == "MANUAL_REVIEW":
        return "Proceed only after manual review and required evidence checks."
    if portfolio.get("decisionImpact", {}).get("seniorReviewRequired") or portfolio_level in {"High", "Critical"}:
        return "Proceed only with senior credit review and conservative LTV terms."
    if decision == "ACCEPT_CONFIDENCE_PENALTY":
        return "Proceed with caution after evidence remediation and reduced confidence treatment."
    if portfolio_level == "Moderate":
        return "Proceed with portfolio watch and standard underwriting conditions."
    return "Proceed subject to standard underwriting policy and documentation."


def _contains_unsupported_lender_action(action: str, payload: Dict[str, Any]) -> bool:
    normalized_action = str(action or "").lower()
    deterministic_text = json.dumps(payload, ensure_ascii=False, default=str).lower()
    if "additional collateral" in normalized_action and not any(
        phrase in deterministic_text
        for phrase in {"collateral is insufficient", "insufficient collateral", "additional collateral required"}
    ):
        return True
    if "reject immediately" in normalized_action and (payload.get("stage2Output") or {}).get("decision") != "REJECT_BLOCK":
        return True
    if "approve automatically" in normalized_action:
        return True
    return False


def _stage1_profile(stage1: Dict[str, Any]) -> Dict[str, Any]:
    return stage1.get("normalizedPropertyProfile") or stage1


def _stage1_micro_market_bucket(stage1: Dict[str, Any]) -> Dict[str, Any]:
    bucket_assignment = stage1.get("bucketAssignment") or {}
    return bucket_assignment.get("microMarketBucket") or stage1.get("microMarketBucket") or {}


def _stage2_scores(stage2: Dict[str, Any]) -> Dict[str, Any]:
    return stage2.get("scores") or stage2


def _portfolio_summary(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    return portfolio.get("portfolioSummary") or portfolio


def _number_or_none(value: Any) -> Optional[float]:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric


def _flatten_flag_text(flags: list[Any]) -> list[str]:
    text: list[str] = []
    for flag in flags:
        if isinstance(flag, str):
            text.append(flag)
        elif isinstance(flag, dict):
            text.append(str(flag.get("explanation") or flag.get("text") or flag.get("title") or ""))
    return text


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result: list[str] = []
    for item in items:
        clean = str(item or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result
