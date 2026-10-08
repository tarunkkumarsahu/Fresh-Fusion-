"""Evidence checks, not an LLM. Rules are explicit and shared with fusion."""
def evaluate_critic(analysis, physical, sensors, vision_score, reference_ready, expected_fruit=None):
    missing, contradictions, warnings, supporting = [], [], [], []
    present = analysis.get("quality", {}).get("fruit_present") is True
    identity = analysis.get("identity", {})
    if not present:
        missing.append("No fruit detected in the latest frame.")
    elif identity.get("fruit") not in {"Apple", "Banana"} or float(identity.get("confidence") or 0) < 58:
        missing.append("A supported fruit identity with sufficient heuristic confidence is required.")
    else:
        supporting.append(f"Visual identity: {identity.get('fruit')} (CV/reference heuristics).")
        if expected_fruit in {"Apple", "Banana"} and identity.get("fruit") != expected_fruit:
            contradictions.append("Latest visual identity differs from the inspection fruit; confirm or start a new inspection.")
    if physical.get("status") in {"suspected_2d_display", "suspected_flat_reference"}:
        contradictions.append("Screen/photo or flat-reference evidence is suspected.")
    if physical.get("views_count", 0) < 3:
        missing.append("Capture at least three changed viewpoints.")
    if not physical.get("physical_likely"):
        missing.append("Physical fruit not verified; four usable recent frames and changed appearance are required.")
    else:
        supporting.append("Multi-view evidence is consistent with a physical fruit (probabilistic).")
    consistency = physical.get("identity_consistency_pct", 0)
    if physical.get("views_count", 0) >= 3 and consistency < 66:
        contradictions.append("Fruit identity is inconsistent or unknown across views.")

    latest = sensors.get("latest")
    if not latest:
        missing.append("Waiting for hardware: no sensor readings.")
    elif not sensors.get("physical_present"):
        missing.append("Waiting for hardware: a valid physical reading within 45 seconds is required.")
    else:
        if latest.get("moisture") is not None and latest.get("mq135_raw") is None:
            supporting.append("Recent ESP8266 moisture telemetry is available as physical hardware evidence.")
        else:
            supporting.append("Recent physical sensor telemetry is available.")
    if latest and latest.get("source") != "hardware":
        warnings.append("Latest telemetry is simulator/test data; it cannot unlock a physical verdict.")
    if latest and (sensors.get("age_seconds") is None or sensors["age_seconds"] > 45):
        warnings.append("Latest sensor data is stale.")
    if not reference_ready:
        warnings.append("Public reference index is not built; reference comparison is unavailable.")
    elif analysis.get("reference_match", {}).get("status") == "ready":
        supporting.append("A published reference comparison is available; similarity is not accuracy.")

    score = sensors.get("score")
    if score is not None and vision_score is not None and (
        (score >= 82 and vision_score < 38) or (vision_score >= 82 and score < 38)
    ):
        contradictions.append("Visual and sensor assessments fall in opposing fresh/spoilage bands; human review required.")
    if latest and latest.get("moisture") is not None and score is None:
        warnings.append("Moisture is displayed as hardware evidence only and is not assigned an uncalibrated freshness weight.")
    else:
        warnings.append("Gas contribution and fusion thresholds are experimental and require empirical calibration.")
    status = "BLOCKED" if contradictions else "NEEDS MORE DATA" if missing else "WARNING" if warnings else "PASSED"
    return {"status": status, "blocking": bool(missing or contradictions), "supporting_evidence": supporting,
            "missing_evidence": missing, "contradictions": contradictions, "warnings": warnings}
