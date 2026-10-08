import os
from sqlalchemy.orm import Session

from ..models import FruitImage, FruitSample, FusionResult, SensorReading
from .physical_validation import evaluate_physical_evidence
from .sensor_assessment import assess_sensors, age_seconds
from .inspection_events import record_assessment_changes

RESULT_KEEP = max(40, int(os.getenv("FUSION_KEEP", "200")))


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _view_name(angle: str) -> str:
    value = (angle or "unknown").lower()
    return value[5:] if value.startswith("live-") else value


def _usable_images(images: list[FruitImage], sample: FruitSample) -> list[FruitImage]:
    quality_aware = [row for row in images if row.analysis and "quality" in row.analysis]
    if quality_aware:
        valid = [row for row in quality_aware if row.analysis.get("quality", {}).get("fruit_present") is True]
    else:
        valid = [row for row in images if row.analysis]

    expected = (sample.fruit_type or "").strip().lower()
    if expected in {"apple", "banana"}:
        matched = []
        for row in valid:
            identity = (row.analysis or {}).get("identity", {})
            detected = str(identity.get("fruit") or "").lower()
            confidence = float(identity.get("confidence") or 0.0)
            if not detected or detected == "unknown" or confidence < 58.0 or detected == expected:
                matched.append(row)
        if matched:
            valid = matched
    return valid


def evaluate_fusion(db: Session, sample: FruitSample) -> dict:
    """Read-only evaluation; persistence is confined to compute_fusion."""
    sensors = (
        db.query(SensorReading)
        .filter(SensorReading.sample_id == sample.sample_id)
        .order_by(SensorReading.captured_at.desc())
        .limit(20)
        .all()
    )
    images = (
        db.query(FruitImage)
        .filter(FruitImage.sample_id == sample.sample_id)
        .order_by(FruitImage.uploaded_at.desc())
        .all()
    )

    sensor_evidence = assess_sensors(sensors)
    sensor_score = sensor_evidence["score"]
    sensor_components = sensor_evidence["components"]
    hardware_present = bool(sensor_evidence.get("physical_present"))

    validation = evaluate_physical_evidence(db, sample, images=images, sensors=sensors)

    vision_score = None
    vision_components = {}
    valid_images = _usable_images([i for i in images if -5 <= age_seconds(i.uploaded_at) <= 180], sample)
    if valid_images:
        healthy_values = []
        brown_values = []
        dark_values = []
        identities = []
        reference_matches = []
        for image in valid_images:
            analysis = image.analysis or {}
            color = analysis.get("color", {})
            defects = analysis.get("defects", {})
            healthy_values.append(float(defects.get("healthy_surface_estimate_pct", 70.0)))
            brown_values.append(float(color.get("brown_pct", 0.0)))
            dark_values.append(float(color.get("dark_pct", 0.0)))
            identity = analysis.get("identity", {})
            if identity.get("fruit") and identity.get("fruit") != "Unknown":
                identities.append(identity.get("fruit"))
            reference = analysis.get("reference_match", {})
            if reference.get("status") == "ready":
                reference_matches.append(reference)

        healthy = sum(healthy_values) / len(healthy_values)
        brown = sum(brown_values) / len(brown_values)
        dark = sum(dark_values) / len(dark_values)
        angles = {_view_name(i.angle) for i in valid_images if _view_name(i.angle) in {"front", "back", "left", "right", "top"}}
        coverage = min(1.0, len(angles) / 5.0)
        provisional_vision_score = _clamp(healthy - brown * 0.20 - dark * 0.35)

        ai_ready = [i.analysis.get("ai", {}) for i in valid_images if i.analysis.get("ai", {}).get("status") == "ready"]
        ai_component = None
        if ai_ready:
            freshness_map = {"fresh": 95.0, "ripe": 78.0, "overripe": 48.0, "spoiled": 15.0}
            ai_scores = [freshness_map.get(x.get("prediction", "").lower(), 50.0) for x in ai_ready]
            ai_component = sum(ai_scores) / len(ai_scores)
            provisional_vision_score = _clamp(provisional_vision_score * 0.58 + ai_component * 0.42)

        top_reference = None
        if reference_matches:
            top_reference = max(reference_matches, key=lambda row: float(row.get("similarity") or 0.0))

        if validation.get("vision_verified"):
            vision_score = provisional_vision_score

        vision_components = {
            "healthy_surface": round(healthy, 2),
            "brown_pct": round(brown, 2),
            "dark_pct": round(dark, 2),
            "angles": len(angles),
            "coverage_pct": round(coverage * 100, 1),
            "usable_images": len(valid_images),
            "ignored_images": max(0, len(images) - len(valid_images)),
            "detected_identity": max(set(identities), key=identities.count) if identities else None,
            "ai_score": round(ai_component, 2) if ai_component is not None else None,
            "provisional_vision_score": round(provisional_vision_score, 2),
            "public_reference": top_reference,
        }

    from .investigation_core.critic import evaluate_critic
    from .datasets import reference_index_status
    latest_analysis = (images[0].analysis or {}) if images else {}
    critic = evaluate_critic(latest_analysis, validation, sensor_evidence, vision_score, reference_index_status()["ready"], sample.fruit_type)
    verdict_ready = bool(validation.get("verdict_ready")) and hardware_present and vision_score is not None and not critic["blocking"]
    validation["verdict_ready"] = verdict_ready

    fusion_mode = "vision_plus_scored_sensors" if sensor_score is not None else "vision_plus_unscored_hardware"
    if verdict_ready:
        if sensor_score is not None:
            score = sensor_score * 0.48 + vision_score * 0.52
        else:
            # Moisture-only hardware proves that physical telemetry is live, but is
            # intentionally not assigned an uncalibrated freshness weight.
            score = vision_score
        angles = {_view_name(i.angle) for i in valid_images if _view_name(i.angle) in {"front", "back", "left", "right", "top"}}
        coverage = min(1.0, len(angles) / 5.0)
        confidence = min(0.94, 0.62 + coverage * 0.20 + float(validation.get("confidence") or 0.0) / 100.0 * 0.10)
        if score >= 82:
            label, risk = "fresh", "low"
        elif score >= 62:
            label, risk = "ripe", "low-medium"
        elif score >= 38:
            label, risk = "overripe", "medium-high"
        else:
            label, risk = "spoiled-suspected", "high"
    else:
        score = 50.0
        if validation.get("status") in {"suspected_2d_display", "suspected_flat_reference"}:
            label, risk = "physical-verification-failed", "unverified"
        elif critic["contradictions"]:
            label, risk = "conflicting-evidence", "unverified"
        elif validation.get("physical_likely") and not hardware_present:
            label, risk = "waiting-for-hardware", "unverified"
        elif validation.get("status") == "no_fruit":
            label, risk = "waiting-for-fruit", "unverified"
        else:
            label, risk = "collecting-physical-evidence", "unverified"
        confidence = max(0.05, min(0.55, float(validation.get("confidence") or 0.0) / 100.0 * 0.55))

    return dict(
        freshness_score=round(score, 2),
        sensor_score=round(sensor_score, 2) if sensor_score is not None else None,
        vision_score=round(vision_score, 2) if vision_score is not None else None,
        label=label,
        confidence=round(confidence * 100, 1),
        risk=risk,
        explanation=(
            "Final output requires multi-view physical-fruit verification and recent physical hardware telemetry. "
            "Legacy DHT11/MQ135 telemetry may contribute an experimental sensor score. Moisture-only ESP8266 telemetry "
            "is shown as hardware evidence but is not assigned a freshness weight until labelled calibration exists. "
            "The physical check is probabilistic because a single phone camera has no true depth sensor."
        ),
        components={
            "fusion_mode": fusion_mode,
            "sensor": sensor_components,
            "sensor_evidence": sensor_evidence,
            "vision": vision_components,
            "validation": validation,
            "critic": critic,
        },
    )


def compute_fusion(db: Session, sample: FruitSample) -> FusionResult:
    assessment = evaluate_fusion(db, sample)
    result = FusionResult(sample_id=sample.sample_id, **assessment)
    sample.status = result.label
    db.add(result)
    db.flush()
    record_assessment_changes(db, result)
    stale = db.query(FusionResult).filter_by(sample_id=sample.sample_id).order_by(
        FusionResult.created_at.desc(), FusionResult.id.desc()
    ).offset(RESULT_KEEP).all()
    for row in stale:
        db.delete(row)
    db.commit()
    db.refresh(result)
    return result
