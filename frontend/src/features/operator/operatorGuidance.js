const normalize = (value) => String(value || "").trim().toLowerCase();

const GUIDANCE = {
  fresh: {
    status: "Fresh",
    action: "Normal sale / storage",
    risk: "Low",
    sellWindow: "Not yet calibrated",
    tone: "good",
  },
  ripe: {
    status: "Ripe",
    action: "Priority sale",
    risk: "Moderate",
    sellWindow: "Not yet calibrated",
    tone: "warning",
  },
  overripe: {
    status: "Overripe",
    action: "Quick sale / processing",
    risk: "High",
    sellWindow: "Not yet calibrated",
    tone: "warning",
  },
  spoiled: {
    status: "Spoiled",
    action: "Remove / reject",
    risk: "Critical",
    sellWindow: "Do not use a shelf-life estimate",
    tone: "danger",
  },
};

export function operatorGuidance(report) {
  const decision = report?.decision || {};
  const critic = report?.critic || {};
  const label = normalize(decision.label);

  if (!decision.verdict_ready || critic.blocking || !GUIDANCE[label]) {
    return {
      status: "More evidence required",
      action: "Reinspect before taking action",
      risk: "Unknown",
      sellWindow: "Unavailable until evidence is sufficient",
      tone: "neutral",
      reason:
        decision.reason ||
        critic.missing_evidence?.[0] ||
        "The current evidence is not strong enough for a reliable quality decision.",
    };
  }

  return {
    ...GUIDANCE[label],
    reason:
      decision.reason ||
      "The current recommendation is based on the available verified evidence.",
  };
}

export function evidenceMetrics(report) {
  const sensor = report?.analysts?.sensor || {};
  const reading = sensor.latest || {};
  const vision = report?.analysts?.vision || {};
  const multiview = report?.analysts?.multiview || {};

  return [
    ["Moisture", reading.moisture == null ? "—" : `${Number(reading.moisture).toFixed(0)}%`],
    ["Signal", reading.rssi == null ? "—" : `${Math.round(Number(reading.rssi))} dBm`],
    ["MQ135", reading.mq135_raw == null ? "—" : `${Math.round(Number(reading.mq135_raw))}`],
    ["Damage", vision.defects?.visible_damage_estimate_pct == null ? "—" : `${Number(vision.defects.visible_damage_estimate_pct).toFixed(0)}%`],
    ["Views", `${multiview.views?.length || 0}/${multiview.required_views ?? 3}`],
  ];
}

export function proactiveMessages(report, fruitType) {
  if (!report) {
    return [
      {
        level: "info",
        title: "Start an inspection",
        text: "Capture three changed views and wait for a recent hardware sensor reading.",
      },
    ];
  }

  const guidance = operatorGuidance(report);
  const critic = report.critic || {};
  const sensor = report.analysts?.sensor || {};
  const multiview = report.analysts?.multiview || {};
  const vision = report.analysts?.vision || {};
  const messages = [];

  if (critic.blocking) {
    messages.push({
      level: "critical",
      title: "Assessment is blocked",
      text:
        critic.missing_evidence?.[0] ||
        critic.contradictions?.[0] ||
        "Collect more reliable evidence before using this result.",
    });
  } else {
    messages.push({
      level: guidance.risk === "High" || guidance.risk === "Critical" ? "warning" : "info",
      title: `${fruitType || "Fruit"}: ${guidance.status}`,
      text: `${guidance.action}. ${guidance.reason}`,
    });
  }

  if ((multiview.views?.length || 0) < (multiview.required_views ?? 3)) {
    messages.push({
      level: "warning",
      title: "More views needed",
      text: `Capture ${multiview.required_views ?? 3} changed views. Current: ${multiview.views?.length || 0}/${multiview.required_views ?? 3}.`,
    });
  }

  if (sensor.age_seconds != null && sensor.age_seconds > 45) {
    messages.push({
      level: "warning",
      title: "Sensor evidence is stale",
      text: "Wait for a fresh hardware reading before relying on the assessment.",
    });
  }

  if (vision.usable_images === 0) {
    messages.push({
      level: "warning",
      title: "No usable image evidence",
      text: "Retake the fruit image with the fruit fully visible and evenly lit.",
    });
  }

  messages.push({
    level: "info",
    title: "Internal quality",
    text: "Internal texture is not measured by the current prototype. A firmness/NIR module is future work.",
  });

  return messages.slice(0, 4);
}
