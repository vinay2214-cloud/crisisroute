import React, { useState, useRef, useEffect } from 'react';
import Dashboard from './Dashboard';
import './App.css';

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

// Bilingual translations
const TRANSLATIONS = {
  en: {
    findHospital: "Find the right hospital",
    tagline: "Powered by AI · Real-time Beds · AP Hospitals",
    describeSymptoms: "Describe symptoms in detail...",
    findNow: "FIND HOSPITAL NOW →",
    critical: "CRITICAL",
    urgent: "URGENT",
    stable: "STABLE",
    immediateAction: "What to do right now",
    directions: "📍 Directions",
    callHospital: "📞 Call Hospital",
    nameLabel: "Patient name (optional)",
    ageLabel: "Patient Age",
    symptomsLabel: "Symptom Description / Trauma Complaint",
    emergencyStrip: "For life-threatening emergencies: CALL 108",
    newSearch: "← Start New Search",
    disclaimer: "CrisisRoute is a navigation aid only — not a clinical diagnosis. Always call 108 for life-threatening emergencies.",
    analyzedIn: "Analyzed in",
    hospitalNotified: "Hospital Notified ✓",
    icuAvailable: "ICU Beds: ",
    available: "available",
    triageRunning: "Analyzing Symptoms...",
    observingFlow: "Observe the multi-agent consensus validation process live."
  },
  te: {
    findHospital: "సరైన ఆసుపత్రిని కనుగొనండి",
    tagline: "AI ఆధారిత · నిజ-సమయ బెడ్స్ · AP ఆసుపత్రులు",
    describeSymptoms: "లక్షణాలను వివరంగా వివరించండి...",
    findNow: "ఇప్పుడే ఆసుపత్రి కనుగొనండి →",
    critical: "తీవ్రమైనది (CRITICAL)",
    urgent: "అత్యవసరము (URGENT)",
    stable: "స్థిరమైనది (STABLE)",
    immediateAction: "వెంటనే చేయవలసిన పనులు",
    directions: "📍 రూట్ మ్యాప్",
    callHospital: "📞 ఆసుపత్రికి కాల్ చేయండి",
    nameLabel: "రోగి పేరు (ఆప్షనల్)",
    ageLabel: "రోగి వయస్సు",
    symptomsLabel: "లక్షణాల వివరణ / గాయాల వివరాలు",
    emergencyStrip: "ప్రాణాపాయ అత్యవసర పరిస్థితుల కోసం: 108 కి కాల్ చేయండి",
    newSearch: "← కొత్త శోధనను ప్రారంభించండి",
    disclaimer: "CrisisRoute ఒక నావిగేషన్ సహాయం మాత్రమే — క్లినికల్ రోగ నిర్ధారణ కాదు. అత్యవసర సమయాల్లో ఎల్లప్పుడూ 108కి కాల్ చేయండి.",
    analyzedIn: "విశ్లేషణ సమయం",
    hospitalNotified: "ఆసుపత్రికి సమాచారం అందింది ✓",
    icuAvailable: "ICU బెడ్స్: ",
    available: "అందుబాటులో ఉన్నాయి",
    triageRunning: "లక్షణాలను విశ్లేషిస్తోంది...",
    observingFlow: "మల్టీ-ఏజెంట్ విశ్లేషణ ప్రక్రియను ప్రత్యక్షంగా చూడండి."
  }
};

const DEMO_PRESETS = [
  {
    label: "🫀 Chest Pain / గుండె నొప్పి",
    symptoms: "severe chest pain radiating to left arm, sweating, dizziness",
    age: 55,
    name: "Ravi Kumar"
  },
  {
    label: "🚗 Road Accident / రోడ్డు ప్రమాదం",
    symptoms: "major road traffic accident, unconscious, heavy bleeding from leg",
    age: 28,
    name: "Kalyan C."
  },
  {
    label: "🌡️ Child Fever / పిల్లల జ్వరం",
    symptoms: "high fever 104F, crying inconsolably, won't eat, rash on body",
    age: 2,
    name: "Baby Lakshmi"
  },
  {
    label: "🧠 Stroke Symptoms / పక్షవాతం",
    symptoms: "sudden slurred speech, cannot lift left arm, facial drooping",
    age: 62,
    name: "Srinivas Rao"
  }
];

// Steps metadata for display
const STEP_META = [
  { num: 1, name: "TriageAgent", desc: "ESI v4 clinical urgency assessment" },
  { num: 2, name: "SpecialtyMatchAgent", desc: "Elastic hybrid semantic mapping" },
  { num: 3, name: "HospitalSearchAgent", desc: "Hospital distance filtering" },
  { num: 4, name: "CapacityAgent", desc: "Real-time bed verification" },
  { num: 5, name: "RoutingAgent", desc: "Severity-adjusted ranking" },
  { num: 6, name: "AdmissionAgent", desc: "Optimistic transactional pre-booking" },
  { num: 7, name: "NotifyAgent", desc: "Hospital notifications and logging" }
];

function App() {
  const [currentHash, setCurrentHash] = useState(window.location.hash);
  
  // App view state
  const [view, setView] = useState("input"); // "input" | "pipeline" | "results"
  const [lang, setLang] = useState("en"); // "en" | "te"
  
  // Form fields
  const [symptoms, setSymptoms] = useState("");
  const [age, setAge] = useState(35);
  const [name, setName] = useState("Patient");
  const [lat] = useState(16.5062); // Hardcoded center
  const [lng] = useState(80.6480);
  
  // Streaming state
  const [steps, setSteps] = useState({});
  const [finalResult, setFinalResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  
  // Font injection
  useEffect(() => {
    const link = document.createElement("link");
    link.href = "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Space+Grotesk:wght@500;700&display=swap";
    link.rel = "stylesheet";
    document.head.appendChild(link);
    return () => {
      document.head.removeChild(link);
    };
  }, []);

  // Hash Router
  useEffect(() => {
    const handleHash = () => setCurrentHash(window.location.hash);
    window.addEventListener("hashchange", handleHash);
    return () => window.removeEventListener("hashchange", handleHash);
  }, []);

  if (currentHash === "#/dashboard") {
    return <Dashboard />;
  }

  const t = TRANSLATIONS[lang];

  const handlePreset = (preset) => {
    setSymptoms(preset.symptoms);
    setAge(preset.age);
    setName(preset.name);
    setErrorMsg("");
  };

  const handleTriage = async () => {
    if (!symptoms || symptoms.length < 5) {
      setErrorMsg(lang === "en" ? "Describe symptoms in at least 5 characters." : "కనీసం 5 అక్షరాలలో లక్షణాలను వివరించండి.");
      return;
    }
    
    setErrorMsg("");
    setSteps({});
    setFinalResult(null);
    setView("pipeline");
    
    try {
      const response = await fetch(`${API_URL}/api/triage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symptoms, age, name, lat, lng })
      });
      
      if (!response.body) {
        throw new Error("Invalid backend stream channel.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const cleanLine = line.slice(6).trim();
            try {
              const event = JSON.parse(cleanLine);
              if (event.step === "complete") {
                setFinalResult(event.final_result);
                // Pause 1 second on pipeline completion before transitioning
                setTimeout(() => {
                  setView("results");
                }, 1000);
              } else if (event.step === "error") {
                setErrorMsg(event.data.error || "A module failed during pipeline orchestration.");
                setView("input");
              } else {
                setSteps(prev => ({
                  ...prev,
                  [event.step]: event
                }));
              }
            } catch (jsonErr) {
              console.error("Error parsing SSE line:", jsonErr);
            }
          }
        }
      }
    } catch (e) {
      console.error(e);
      setErrorMsg(e.message || "Failed to establish stream connection with FastAPI.");
      setView("input");
    }
  };

  return (
    <div style={inlineStyles.app}>
      
      {/* View 1: Input Screen */}
      {view === "input" && (
        <div style={inlineStyles.wrapper}>
          {/* Top Bar */}
          <div style={inlineStyles.topBar}>
            <div style={inlineStyles.logoGroup}>
              <div style={inlineStyles.indicator}></div>
              <span style={inlineStyles.logoText}>CrisisRoute</span>
            </div>
            
            <div style={inlineStyles.langToggle}>
              <button 
                style={{...inlineStyles.langBtn, fontWeight: lang === "en" ? "bold" : "normal"}} 
                onClick={() => setLang("en")}
              >EN</button>
              <span style={{color: "#334155"}}>|</span>
              <button 
                style={{...inlineStyles.langBtn, fontWeight: lang === "te" ? "bold" : "normal"}} 
                onClick={() => setLang("te")}
              >తెలుగు</button>
              
              <button 
                style={inlineStyles.dashboardLink} 
                onClick={() => window.location.hash = "#/dashboard"}
              >Command Centre ↗</button>
            </div>
          </div>

          {/* Call 108 Red Strip */}
          <div style={inlineStyles.emergencyStrip}>
            <span>📞 {t.emergencyStrip}</span>
          </div>

          {/* Hero */}
          <div style={inlineStyles.hero}>
            <h1 style={inlineStyles.heroTitle}>{t.findHospital}</h1>
            <p style={inlineStyles.heroSubtitle}>{t.tagline}</p>
          </div>

          {/* Quick symptom presets */}
          <div style={inlineStyles.presetGrid}>
            {DEMO_PRESETS.map((p, idx) => (
              <button 
                key={idx} 
                style={inlineStyles.presetCard} 
                onClick={() => handlePreset(p)}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Form */}
          <div style={inlineStyles.form}>
            <div style={inlineStyles.formGroup}>
              <label style={inlineStyles.label}>{t.nameLabel}</label>
              <input 
                style={inlineStyles.input} 
                type="text" 
                value={name} 
                onChange={e => setName(e.target.value)} 
              />
            </div>

            {/* Age Counter (not raw input) */}
            <div style={inlineStyles.formGroup}>
              <label style={inlineStyles.label}>{t.ageLabel}</label>
              <div style={inlineStyles.counterWrapper}>
                <button 
                  style={inlineStyles.counterBtn} 
                  onClick={() => setAge(prev => Math.max(0, prev - 1))}
                >-</button>
                <span style={inlineStyles.counterVal} className="font-data">{age}</span>
                <button 
                  style={inlineStyles.counterBtn} 
                  onClick={() => setAge(prev => Math.min(120, prev + 1))}
                >+</button>
              </div>
            </div>

            <div style={inlineStyles.formGroup}>
              <label style={inlineStyles.label}>{t.symptomsLabel}</label>
              <textarea 
                style={inlineStyles.textarea} 
                rows={4} 
                placeholder={t.describeSymptoms}
                value={symptoms}
                onChange={e => setSymptoms(e.target.value)}
              />
            </div>

            {errorMsg && <div style={inlineStyles.errorText}>{errorMsg}</div>}

            <button style={inlineStyles.submitBtn} onClick={handleTriage}>
              {t.findNow}
            </button>
          </div>

          {/* Muted Disclaimer */}
          <div style={inlineStyles.mutedDisclaimer}>
            {t.disclaimer}
          </div>
        </div>
      )}

      {/* View 2: Pipeline Screen (Assessing Streaming) */}
      {view === "pipeline" && (
        <div style={inlineStyles.wrapper}>
          <div style={inlineStyles.pipelineTitle}>
            <div style={inlineStyles.spinner}></div>
            <h2>{t.triageRunning}</h2>
            <p style={{color: "#94a3b8", fontSize: "13px"}}>{t.observingFlow}</p>
          </div>

          <div style={inlineStyles.pipelineStack}>
            {STEP_META.map(step => {
              const s = steps[step.num];
              const isRunning = !s && Object.keys(steps).length === step.num - 1;
              const isPending = !s && !isRunning;
              
              let statusIcon = "⏳";
              if (isRunning) statusIcon = "🔄";
              if (s) statusIcon = s.status === "complete" ? "✅" : "⚠️";

              return (
                <div 
                  key={step.num} 
                  style={{
                    ...inlineStyles.stepCard,
                    opacity: isPending ? 0.4 : 1,
                    borderColor: isRunning ? "#c084fc" : s ? "rgba(16, 185, 129, 0.3)" : "rgba(255,255,255,0.08)"
                  }}
                >
                  <div style={inlineStyles.stepHeader}>
                    <span style={{marginRight: "10px"}}>{statusIcon}</span>
                    <div style={{flex: 1}}>
                      <strong>{step.name}</strong>
                      <div style={{color: "#94a3b8", fontSize: "11px"}}>{step.desc}</div>
                    </div>
                    {s && <span style={inlineStyles.durationBadge} className="font-data">{s.elapsed_ms}ms</span>}
                  </div>

                  {s && (
                    <div style={inlineStyles.stepData} className="font-mono">
                      {step.num === 1 && `Severity: ${s.data.severity.toUpperCase()} | ${s.data.chief_complaint}`}
                      {step.num === 2 && `Specialty: ${s.data.specialty.toUpperCase()} (${(s.data.confidence * 100).toFixed(0)}%)`}
                      {step.num === 3 && `Hospitals Found: ${s.data.hospitals_found} (${s.data.nearest})`}
                      {step.num === 4 && `Avail Beds Checked: ${s.data.total_available_beds}`}
                      {step.num === 5 && `Optimal ETA: ${s.data.eta_minutes} mins`}
                      {step.num === 6 && `Pre-registration Bed Confirmed: ${s.data.bed_reserved ? "YES" : "NO"}`}
                      {step.num === 7 && `Dispatched Out: ${s.data.case_id}`}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* View 3: Results Screen */}
      {view === "results" && finalResult && (
        <div style={inlineStyles.wrapper}>
          {/* SEVERITY BANNER */}
          <div style={{
            ...inlineStyles.severityBanner,
            backgroundColor: finalResult.severity === "critical" ? "#E74C3C" : finalResult.severity === "urgent" ? "#F39C12" : "#27AE60"
          }}>
            <span style={inlineStyles.severityLabel}>{finalResult.severity.toUpperCase()}</span>
            <h2 style={{margin: "4px 0 0 0", fontSize: "20px"}}>{finalResult.chief_complaint}</h2>
          </div>

          {/* IMMEDIATE ACTION */}
          <div style={{
            ...inlineStyles.immediateActionBox,
            borderColor: finalResult.severity === "critical" ? "#E74C3C" : finalResult.severity === "urgent" ? "#F39C12" : "#27AE60"
          }}>
            <span style={inlineStyles.actionLabel}>{t.immediateAction}</span>
            <p style={inlineStyles.actionText}>{finalResult.immediate_action}</p>
          </div>

          {/* SPECIALTY BADGE */}
          <div style={inlineStyles.specialtyAlert}>
            🚨 <b>{finalResult.specialty_needed.toUpperCase()} TEAM ALERTED</b> (Confidence: {(finalResult.specialty_confidence * 100).toFixed(0)}%)
          </div>

          {/* HOSPITAL CARDS */}
          <div style={inlineStyles.hospitalsList}>
            {finalResult.top_hospitals.map((h, idx) => {
              // Color variables for ranks
              const rankColor = idx === 0 ? "#FFD700" : idx === 1 ? "#C0C0C0" : "#CD7F32";
              
              // Bed availability logic
              const barColor = h.beds_available >= 20 ? "#27AE60" : h.beds_available >= 5 ? "#F39C12" : "#E74C3C";

              return (
                <div key={idx} style={inlineStyles.hospitalCard}>
                  {idx === 0 && (
                    <div style={inlineStyles.notifiedBanner}>{t.hospitalNotified}</div>
                  )}
                  
                  <div style={inlineStyles.hCardHeader}>
                    <div style={{...inlineStyles.rankBadge, backgroundColor: rankColor}}>#{idx + 1}</div>
                    <div style={{flex: 1, textAlign: "left"}}>
                      <h3 style={inlineStyles.hName}>{h.name}</h3>
                      <div style={inlineStyles.hMeta}>{h.district} · AP</div>
                    </div>
                  </div>

                  <div style={inlineStyles.hDetailsRow} className="font-data">
                    <span>🚗 <b>{h.distance_km} km</b></span>
                    <span>⏱️ <b>{h.eta_minutes} mins away</b></span>
                  </div>

                  {/* Bed availability bar */}
                  <div style={inlineStyles.bedBarContainer}>
                    <div style={{...inlineStyles.bedBarFill, width: `${Math.min(100, h.beds_available)}%`, backgroundColor: barColor}}></div>
                  </div>
                  <div style={{display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#94a3b8", marginTop: "4px"}}>
                    <span>Available beds: <b>{h.beds_available}</b></span>
                    <span>{t.icuAvailable}<b>{h.icu_available}</b></span>
                  </div>

                  <div style={inlineStyles.hMetaBadges}>
                    <span style={inlineStyles.badge}>{h.is_government ? "Government" : "Private"}</span>
                    <span style={inlineStyles.badge}>{h.accreditation}</span>
                    <span style={inlineStyles.badge}>⭐ {h.rating}</span>
                  </div>

                  <div style={inlineStyles.actionsRow}>
                    <a href={h.maps_directions_url} target="_blank" rel="noreferrer" style={inlineStyles.actionBtn}>
                      {t.directions}
                    </a>
                    <a href={`tel:${h.contact_phone}`} style={{...inlineStyles.actionBtn, backgroundColor: "#E74C3C"}}>
                      {t.callHospital}
                    </a>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Case audit info */}
          <div style={inlineStyles.caseInfo}>
            <span>Case ID: <b>{finalResult.case_id}</b></span> | 
            <span> {t.analyzedIn} <b>{(finalResult.pipeline_duration_ms / 1000).toFixed(1)}s</b></span>
          </div>

          {/* Search New Link */}
          <button style={inlineStyles.newSearchLink} onClick={() => setView("input")}>
            {t.newSearch}
          </button>
        </div>
      )}
    </div>
  );
}

const inlineStyles = {
  app: {
    backgroundColor: "#0A0F1E",
    minHeight: "100vh",
    color: "#F8FAFC",
    fontFamily: "'DM Sans', system-ui, sans-serif",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "20px",
    boxSizing: "border-box"
  },
  wrapper: {
    width: "100%",
    maxWidth: "500px",
    display: "flex",
    flexDirection: "column"
  },
  topBar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "16px"
  },
  logoGroup: {
    display: "flex",
    alignItems: "center",
    gap: "8px"
  },
  indicator: {
    width: "10px",
    height: "10px",
    borderRadius: "50%",
    backgroundColor: "#E74C3C",
    boxShadow: "0 0 8px #E74C3C"
  },
  logoText: {
    fontSize: "20px",
    fontWeight: "800",
    letterSpacing: "-0.5px",
    background: "linear-gradient(135deg, #fff 0%, #c084fc 100%)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent"
  },
  langToggle: {
    display: "flex",
    alignItems: "center",
    gap: "8px"
  },
  langBtn: {
    background: "none",
    border: "none",
    color: "#c084fc",
    cursor: "pointer",
    fontSize: "12px"
  },
  dashboardLink: {
    background: "rgba(255, 255, 255, 0.05)",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    color: "#94a3b8",
    padding: "4px 8px",
    borderRadius: "4px",
    fontSize: "10px",
    cursor: "pointer"
  },
  emergencyStrip: {
    backgroundColor: "#E74C3C",
    color: "#fff",
    padding: "10px",
    borderRadius: "8px",
    fontWeight: "750",
    fontSize: "13px",
    marginBottom: "20px",
    textAlign: "center"
  },
  hero: {
    textAlign: "left",
    marginBottom: "20px"
  },
  heroTitle: {
    fontSize: "28px",
    fontWeight: "800",
    margin: 0,
    letterSpacing: "-0.8px"
  },
  heroSubtitle: {
    color: "#94a3b8",
    fontSize: "13px",
    margin: "4px 0 0 0"
  },
  presetGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "10px",
    marginBottom: "20px"
  },
  presetCard: {
    background: "rgba(30, 41, 59, 0.45)",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "10px",
    padding: "14px",
    color: "#fff",
    fontSize: "12px",
    fontWeight: "600",
    cursor: "pointer",
    textAlign: "left",
    transition: "all 0.2s"
  },
  form: {
    background: "rgba(30, 41, 59, 0.3)",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "12px",
    padding: "18px",
    display: "flex",
    flexDirection: "column",
    gap: "16px",
    textAlign: "left"
  },
  formGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "6px"
  },
  label: {
    fontSize: "11px",
    color: "#94a3b8",
    textTransform: "uppercase",
    fontWeight: "600"
  },
  input: {
    background: "rgba(15, 23, 42, 0.6)",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "6px",
    padding: "8px 12px",
    color: "#fff",
    fontSize: "13px"
  },
  textarea: {
    background: "rgba(15, 23, 42, 0.6)",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "6px",
    padding: "10px",
    color: "#fff",
    fontSize: "13px",
    fontFamily: "inherit"
  },
  counterWrapper: {
    display: "flex",
    alignItems: "center",
    gap: "16px"
  },
  counterBtn: {
    width: "36px",
    height: "36px",
    borderRadius: "6px",
    backgroundColor: "#1B4F72",
    border: "none",
    color: "#fff",
    fontSize: "18px",
    fontWeight: "bold",
    cursor: "pointer"
  },
  counterVal: {
    fontSize: "18px",
    fontWeight: "bold",
    minWidth: "30px",
    textAlign: "center"
  },
  errorText: {
    backgroundColor: "rgba(231, 76, 60, 0.1)",
    border: "1px solid #E74C3C",
    color: "#E74C3C",
    padding: "8px 12px",
    borderRadius: "6px",
    fontSize: "12px"
  },
  submitBtn: {
    backgroundColor: "#E74C3C",
    border: "none",
    borderRadius: "8px",
    color: "#fff",
    height: "50px",
    fontSize: "14px",
    fontWeight: "700",
    cursor: "pointer",
    textTransform: "uppercase",
    letterSpacing: "0.5px"
  },
  mutedDisclaimer: {
    fontSize: "10px",
    color: "#475569",
    marginTop: "16px",
    lineHeight: "1.4",
    textAlign: "center"
  },
  pipelineTitle: {
    textAlign: "center",
    marginBottom: "24px"
  },
  spinner: {
    width: "32px",
    height: "32px",
    border: "3px solid rgba(192, 132, 252, 0.1)",
    borderTopColor: "#c084fc",
    borderRadius: "50%",
    margin: "0 auto 12px auto",
    animation: "spin 1s infinite linear"
  },
  pipelineStack: {
    display: "flex",
    flexDirection: "column",
    gap: "10px"
  },
  stepCard: {
    background: "rgba(30, 41, 59, 0.45)",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "10px",
    padding: "12px 16px",
    textAlign: "left"
  },
  stepHeader: {
    display: "flex",
    alignItems: "center"
  },
  durationBadge: {
    fontSize: "10px",
    color: "#c084fc",
    background: "rgba(192,132,252,0.1)",
    padding: "2px 6px",
    borderRadius: "4px"
  },
  stepData: {
    fontSize: "11px",
    color: "#94a3b8",
    background: "rgba(15, 23, 42, 0.5)",
    padding: "8px",
    borderRadius: "4px",
    marginTop: "8px"
  },
  severityBanner: {
    borderRadius: "12px",
    padding: "16px",
    textAlign: "left",
    marginBottom: "16px",
    boxShadow: "0 4px 15px rgba(0,0,0,0.3)"
  },
  severityLabel: {
    fontSize: "10px",
    fontWeight: "800",
    textTransform: "uppercase",
    background: "rgba(0,0,0,0.2)",
    padding: "2px 8px",
    borderRadius: "4px"
  },
  immediateActionBox: {
    borderLeftWidth: "4px",
    borderLeftStyle: "solid",
    background: "rgba(255, 255, 255, 0.05)",
    borderTop: "1px solid rgba(255,255,255,0.08)",
    borderRight: "1px solid rgba(255,255,255,0.08)",
    borderBottom: "1px solid rgba(255,255,255,0.08)",
    borderRadius: "8px",
    padding: "16px",
    textAlign: "left",
    marginBottom: "16px"
  },
  actionLabel: {
    display: "block",
    fontSize: "11px",
    fontWeight: "700",
    color: "#c084fc",
    textTransform: "uppercase",
    marginBottom: "6px"
  },
  actionText: {
    fontSize: "14px",
    fontWeight: "600",
    lineHeight: "1.5",
    margin: 0
  },
  specialtyAlert: {
    backgroundColor: "rgba(192, 132, 252, 0.1)",
    border: "1px solid rgba(192, 132, 252, 0.3)",
    padding: "10px",
    borderRadius: "8px",
    fontSize: "12px",
    textAlign: "left",
    marginBottom: "20px"
  },
  hospitalsList: {
    display: "flex",
    flexDirection: "column",
    gap: "16px"
  },
  hospitalCard: {
    background: "rgba(30, 41, 59, 0.45)",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "12px",
    padding: "18px",
    position: "relative",
    overflow: "hidden"
  },
  notifiedBanner: {
    position: "absolute",
    top: 0,
    right: 0,
    backgroundColor: "#27AE60",
    color: "#fff",
    fontSize: "9px",
    fontWeight: "700",
    padding: "4px 10px",
    borderBottomLeftRadius: "8px"
  },
  hCardHeader: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    marginBottom: "12px"
  },
  rankBadge: {
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    color: "#0f172a",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: "800",
    fontSize: "13px"
  },
  hName: {
    fontSize: "16px",
    fontWeight: "700",
    margin: 0
  },
  hMeta: {
    fontSize: "11px",
    color: "#94a3b8",
    marginTop: "2px"
  },
  hDetailsRow: {
    display: "flex",
    gap: "16px",
    fontSize: "13px",
    borderTop: "1px solid rgba(255,255,255,0.05)",
    borderBottom: "1px solid rgba(255,255,255,0.05)",
    padding: "8px 0",
    marginBottom: "12px"
  },
  bedBarContainer: {
    height: "8px",
    backgroundColor: "rgba(255,255,255,0.05)",
    borderRadius: "4px",
    overflow: "hidden",
    marginTop: "8px"
  },
  bedBarFill: {
    height: "100%",
    borderRadius: "4px"
  },
  hMetaBadges: {
    display: "flex",
    flexWrap: "wrap",
    gap: "6px",
    margin: "12px 0 16px 0"
  },
  badge: {
    fontSize: "10px",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.08)",
    padding: "2px 6px",
    borderRadius: "4px",
    color: "#E2E8F0"
  },
  actionsRow: {
    display: "flex",
    gap: "10px"
  },
  actionBtn: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "10px",
    background: "#1B4F72",
    color: "#fff",
    borderRadius: "6px",
    fontSize: "12px",
    fontWeight: "700",
    textDecoration: "none",
    transition: "all 0.2s"
  },
  caseInfo: {
    fontSize: "11px",
    color: "#475569",
    marginTop: "24px",
    textAlign: "center"
  },
  newSearchLink: {
    background: "none",
    border: "none",
    color: "#c084fc",
    fontSize: "13px",
    fontWeight: "700",
    cursor: "pointer",
    marginTop: "16px",
    alignSelf: "center"
  }
};

export default App;
