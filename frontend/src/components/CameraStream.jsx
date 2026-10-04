import { useEffect, useRef, useState } from "react";
import {
  Camera,
  CircleStop,
  RefreshCw,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { uploadImage, uploadStreamFrame } from "../api";

const isPhone = () =>
  /Android|iPhone|iPad|iPod/i.test(navigator.userAgent) ||
  (navigator.maxTouchPoints > 1 && /Macintosh/i.test(navigator.userAgent));
const views = ["front", "back", "left", "right", "top"];

export default function CameraStream({
  sampleId,
  groundTruth = "",
  onFrame,
  compact = false,
  autoStart = false,
}) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const busyRef = useRef(false);
  const intervalRef = useRef(2500);
  const fileRef = useRef(null);
  const mountedRef = useRef(true);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [sent, setSent] = useState(0);
  const [intervalMs, setIntervalMs] = useState(2500);
  const [view, setView] = useState("front");
  const currentRef = useRef({ sampleId, groundTruth, onFrame, view });
  currentRef.current = { sampleId, groundTruth, onFrame, view };
  const generationRef = useRef(0);
  const startingRef = useRef(false);

  const clearTimer = () => {
    clearTimeout(timerRef.current);
    timerRef.current = null;
  };

  const stop = (nextStatus = "stopped") => {
    clearTimer();
    generationRef.current += 1;
    startingRef.current = false;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    if (mountedRef.current) {
      setRunning(false);
      setStatus(nextStatus);
    }
  };

  const captureAndSend = async () => {
    const { sampleId, view, groundTruth } = currentRef.current;
    const generation = generationRef.current;
    if (
      !streamRef.current ||
      !videoRef.current ||
      busyRef.current ||
      !sampleId ||
      document.hidden
    )
      return;
    const video = videoRef.current;
    if (!video.videoWidth || !video.videoHeight) return;

    busyRef.current = true;
    setStatus("sending");
    try {
      const maxWidth = 960;
      const scale = Math.min(1, maxWidth / video.videoWidth);
      const width = Math.max(320, Math.round(video.videoWidth * scale));
      const height = Math.max(240, Math.round(video.videoHeight * scale));
      const canvas = canvasRef.current;
      canvas.width = width;
      canvas.height = height;
      canvas
        .getContext("2d", { alpha: false })
        .drawImage(video, 0, 0, width, height);
      const blob = await new Promise((resolve) =>
        canvas.toBlob(resolve, "image/jpeg", 0.82),
      );
      if (!blob) throw new Error("Could not create camera frame");
      if (generation !== generationRef.current) return;

      const file = new File([blob], `live-${view}-${Date.now()}.jpg`, {
        type: "image/jpeg",
      });
      const result = await uploadStreamFrame(sampleId, view, groundTruth, file);
      if (
        !mountedRef.current ||
        generation !== generationRef.current ||
        currentRef.current.sampleId !== sampleId
      )
        return;
      setSent((value) => value + 1);
      setStatus("live");
      setError("");
      currentRef.current.onFrame?.(result);
    } catch (e) {
      if (
        !mountedRef.current ||
        generation !== generationRef.current ||
        currentRef.current.sampleId !== sampleId
      )
        return;
      setError(
        `Frame upload failed: ${e.message || String(e)}. The camera will keep retrying.`,
      );
      setStatus("retrying");
    } finally {
      busyRef.current = false;
    }
  };

  const schedule = () => {
    clearTimer();
    if (!streamRef.current || document.hidden) return;
    const generation = generationRef.current;
    timerRef.current = setTimeout(async () => {
      await captureAndSend();
      if (generation === generationRef.current) schedule();
    }, intervalRef.current);
  };

  const start = async () => {
    if (
      streamRef.current ||
      startingRef.current ||
      !currentRef.current.sampleId
    )
      return;
    setError("");

    if (!window.isSecureContext) {
      setError(
        "Camera access requires a secure HTTPS page. Scan the FreshFusion dashboard QR on the deployed site, or use the trusted local phone link when running FreshFusion locally.",
      );
      setStatus("blocked");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setError(
        "This browser does not expose the live camera API. Try current Chrome, Edge or Safari.",
      );
      setStatus("blocked");
      return;
    }

    const generation = generationRef.current;
    try {
      startingRef.current = true;
      setStatus("requesting");
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      if (!mountedRef.current || generation !== generationRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      if (!mountedRef.current || generation !== generationRef.current) return;
      setRunning(true);
      setStatus("live");
      schedule();
    } catch (e) {
      if (!mountedRef.current || generation !== generationRef.current) return;
      const message =
        e?.name === "NotAllowedError"
          ? "Camera permission was denied. Open site permissions, allow Camera, then tap Start camera."
          : e?.name === "NotFoundError"
            ? "No usable camera was found on this device."
            : e.message || String(e);
      setError(message);
      setStatus("blocked");
    } finally {
      if (generation === generationRef.current) startingRef.current = false;
    }
  };

  const changeInterval = (e) => {
    const next = Number(e.target.value);
    setIntervalMs(next);
    intervalRef.current = next;
    if (streamRef.current) schedule();
  };

  const manualFile = async (e) => {
    const input = e.target;
    const file = input.files?.[0];
    const { sampleId, view, groundTruth } = currentRef.current;
    if (!file || !sampleId) return;
    try {
      setStatus("sending");
      const result = await uploadImage(sampleId, view, groundTruth, file);
      if (!mountedRef.current || currentRef.current.sampleId !== sampleId)
        return;
      setSent((value) => value + 1);
      setStatus(running ? "live" : "idle");
      currentRef.current.onFrame?.(result);
    } catch (e) {
      setError(e.message || String(e));
      setStatus("error");
    } finally {
      input.value = "";
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    setRunning(false);
    setStatus("idle");
    if (sampleId && (autoStart || isPhone())) {
      const id = setTimeout(start, 550);
      return () => {
        clearTimeout(id);
        mountedRef.current = false;
        stop("idle");
      };
    }
    return () => {
      mountedRef.current = false;
      stop("idle");
    };
  }, [sampleId]);

  useEffect(() => {
    const onVisibility = () => {
      if (!streamRef.current) return;
      if (document.hidden) {
        clearTimer();
        setStatus("paused");
      } else {
        setStatus("live");
        schedule();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  return (
    <div className={`cameraModule ${compact ? "compact" : ""}`}>
      <div className="cameraHead">
        <div>
          <span>PHONE VISION</span>
          <h2>
            {compact
              ? "Keep the fruit inside the guide"
              : "Continuous camera stream"}
          </h2>
        </div>
        <div className={`streamState ${status}`}>
          <i></i>
          {status === "live" ? "LIVE" : status.toUpperCase()}
        </div>
      </div>

      <div className="viewSteps" aria-label="Fruit view selector">
        {views.map((item) => (
          <button
            type="button"
            key={item}
            className={view === item ? "selected" : ""}
            onClick={() => {
              currentRef.current.view = item;
              setView(item);
            }}
          >
            {item}
          </button>
        ))}
      </div>

      <div className="videoStage">
        <video ref={videoRef} autoPlay muted playsInline />
        {!running && (
          <div className="cameraEmpty">
            <Camera size={34} />
            <b>Camera not active</b>
            <span>Allow rear-camera access when the browser asks.</span>
          </div>
        )}
        {running && (
          <>
            <div className="focusFrame"></div>
            <div className="liveCorner">
              {view.toUpperCase()} · AUTO {intervalMs / 1000}s
            </div>
          </>
        )}
      </div>
      <canvas ref={canvasRef} hidden />

      <div className="cameraControls">
        {!running ? (
          <button
            type="button"
            className="primary"
            onClick={start}
            disabled={!sampleId || status === "requesting"}
          >
            <Camera size={17} /> Start camera
          </button>
        ) : (
          <button type="button" className="danger" onClick={() => stop()}>
            <CircleStop size={17} /> Stop
          </button>
        )}
        <label className="field">
          <span>Send every</span>
          <select value={intervalMs} onChange={changeInterval}>
            <option value="1500">1.5 sec</option>
            <option value="2500">2.5 sec</option>
            <option value="5000">5 sec</option>
            <option value="10000">10 sec</option>
          </select>
        </label>
        {!compact && (
          <>
            <button
              type="button"
              className="secondary"
              onClick={() => fileRef.current?.click()}
            >
              <Upload size={16} /> Upload fallback
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              capture="environment"
              hidden
              onChange={manualFile}
            />
          </>
        )}
      </div>

      <div className="cameraMeta">
        <span>
          <ShieldCheck size={14} />
          {window.isSecureContext ? "trusted HTTPS" : "secure context required"}
        </span>
        <span>
          <RefreshCw size={14} /> {sent} frames sent
        </span>
        <span>Current view: {view}</span>
      </div>
      {error && <div className="cameraError">{error}</div>}
    </div>
  );
}
