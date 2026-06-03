import React, { useState, useRef, useEffect } from 'react';

const agentColors = {
  TriageAgent: '#E74C3C',
  SpecialtyMatchAgent: '#3498DB',
  HospitalSearchAgent: '#9B59B6',
  CapacityAgent: '#2ECC71',
  RoutingAgent: '#F39C12',
  NotifyAgent: '#1ABC9C',
  Orchestrator: '#95A5A6'
};

const severityColors = {
  critical: '#E74C3C',
  urgent: '#F39C12',
  stable: '#2ECC71',
  unknown: '#95A5A6'
};

export default function App() {
  const [view, setView] = useState(1); // 1 = Input, 2 = Results
  const [language, setLanguage] = useState('English');
  
  // Form State
  const [symptoms, setSymptoms] = useState('');
  const [age, setAge] = useState(35);
  const [name, setName] = useState('');
  const [lat, setLat] = useState(16.5062);
  const [lng, setLng] = useState(80.6480);

  // Results State
  const [streamingSteps, setStreamingSteps] = useState([]);
  const [finalResult, setFinalResult] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);

  const abortControllerRef = useRef(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const handleQuickPick = (text) => {
    setSymptoms(text);
  };

  const handleToggleLanguage = () => {
    setLanguage(language === 'English' ? 'Telugu' : 'English');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!symptoms.trim()) {
      alert("Please describe symptoms.");
      return;
    }

    setView(2);
    setStreamingSteps([]);
    setFinalResult(null);
    setError(null);
    setIsStreaming(true);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch('http://127.0.0.1:8000/api/triage', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          symptoms,
          age,
          name,
          lat,
          lng
        }),
        signal: abortControllerRef.current.signal
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        
        // Keep the last part in buffer if it doesn't end with \n\n
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.replace('data: ', '').trim();
            if (dataStr) {
              try {
                const parsed = JSON.parse(dataStr);
                
                if (parsed.step === 'complete') {
                  setFinalResult(parsed.final_result);
                  setIsStreaming(false);
                } else if (parsed.step === 'error') {
                  setError(parsed.status);
                  setIsStreaming(false);
                } else {
                  setStreamingSteps(prev => [...prev, parsed]);
                }
              } catch (e) {
                console.error("Error parsing SSE data", e, dataStr);
              }
            }
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError(err.message);
        setIsStreaming(false);
      }
    }
  };

  const handleNewSearch = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setView(1);
    setSymptoms('');
    setAge(35);
    setName('');
    setStreamingSteps([]);
    setFinalResult(null);
    setError(null);
  };

  // Common Styles
  const containerStyle = {
    fontFamily: 'sans-serif',
    backgroundColor: '#0A0F1E',
    color: '#FFFFFF',
    minHeight: '100vh',
    display: 'flex',
    justifyContent: 'center',
    padding: '16px',
    boxSizing: 'border-box'
  };

  const contentStyle = {
    width: '100%',
    maxWidth: '375px', // Mobile-first primary viewport
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    paddingBottom: '40px'
  };

  const headerStyle = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottom: '1px solid rgba(255,255,255,0.1)',
    paddingBottom: '12px'
  };

  const titleStyle = {
    color: '#3498DB', // Blue
    margin: 0,
    fontSize: '24px',
    fontWeight: 'bold'
  };

  const langButtonStyle = {
    background: 'none',
    border: '1px solid #3498DB',
    color: '#3498DB',
    padding: '4px 8px',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '12px'
  };

  const disclaimerBannerStyle = {
    backgroundColor: 'rgba(231, 76, 60, 0.1)',
    color: '#E74C3C',
    padding: '12px',
    borderRadius: '8px',
    border: '1px solid #E74C3C',
    fontSize: '14px',
    fontWeight: 'bold',
    textAlign: 'center'
  };

  if (view === 1) {
    return (
      <div style={containerStyle}>
        <div style={contentStyle}>
          <header style={headerStyle}>
            <h1 style={titleStyle}>CrisisRoute</h1>
            <button onClick={handleToggleLanguage} style={langButtonStyle}>
              {language}
            </button>
          </header>

          <div style={disclaimerBannerStyle}>
            ⚠️ Navigation aid only. For emergencies call 108.
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <button onClick={() => handleQuickPick('Severe chest pain radiating to arm')} style={quickPickStyle}>🫀 Chest Pain</button>
            <button onClick={() => handleQuickPick('Severe road accident injuries')} style={quickPickStyle}>🚗 Road Accident</button>
            <button onClick={() => handleQuickPick('Child with very high fever and seizures')} style={quickPickStyle}>🌡️ Child Fever</button>
            <button onClick={() => handleQuickPick('Sudden weakness on one side, slurred speech')} style={quickPickStyle}>🧠 Stroke</button>
          </div>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '14px', color: '#BDC3C7' }}>Describe symptoms... *</label>
              <textarea 
                value={symptoms}
                onChange={(e) => setSymptoms(e.target.value)}
                required
                style={{
                  minHeight: '100px',
                  backgroundColor: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.2)',
                  borderRadius: '8px',
                  color: 'white',
                  padding: '12px',
                  fontSize: '16px',
                  resize: 'vertical'
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
                <label style={{ fontSize: '14px', color: '#BDC3C7' }}>Age</label>
                <input 
                  type="number" 
                  value={age}
                  onChange={(e) => setAge(parseInt(e.target.value) || 0)}
                  style={inputStyle}
                />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 2 }}>
                <label style={{ fontSize: '14px', color: '#BDC3C7' }}>Name (Optional)</label>
                <input 
                  type="text" 
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={inputStyle}
                />
              </div>
            </div>

            <button 
              type="submit" 
              style={{
                backgroundColor: '#E74C3C',
                color: 'white',
                border: 'none',
                padding: '16px',
                borderRadius: '8px',
                fontSize: '18px',
                fontWeight: 'bold',
                cursor: 'pointer',
                marginTop: '8px',
                boxShadow: '0 4px 6px rgba(231, 76, 60, 0.3)'
              }}
            >
              Find Hospital Now
            </button>
          </form>
        </div>
      </div>
    );
  }

  // VIEW 2: Results Screen
  return (
    <div style={containerStyle}>
      <div style={contentStyle}>
        <header style={headerStyle}>
          <h1 style={titleStyle}>CrisisRoute</h1>
        </header>

        {/* Agent Streaming Steps */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
          {streamingSteps.map((step, idx) => (
            <div key={idx} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              backgroundColor: 'rgba(255,255,255,0.05)',
              padding: '10px 16px',
              borderRadius: '8px',
              borderLeft: `4px solid ${agentColors[step.agent] || '#FFFFFF'}`
            }}>
              <div style={{
                backgroundColor: agentColors[step.agent] || '#FFFFFF',
                color: 'white',
                borderRadius: '50%',
                width: '24px',
                height: '24px',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                fontSize: '12px'
              }}>
                ✓
              </div>
              <div style={{ flex: 1, fontSize: '14px' }}>
                <span style={{ fontWeight: 'bold' }}>{step.agent}</span>
                <span style={{ color: '#BDC3C7', marginLeft: '8px' }}>Complete</span>
              </div>
            </div>
          ))}
          {isStreaming && (
            <div style={{ textAlign: 'center', color: '#BDC3C7', fontSize: '14px', padding: '12px' }}>
              Processing...
            </div>
          )}
          {error && (
            <div style={{ color: '#E74C3C', fontSize: '14px', padding: '12px', border: '1px solid #E74C3C', borderRadius: '8px' }}>
              Error: {error}
            </div>
          )}
        </div>

        {/* Final Result */}
        {finalResult && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', animation: 'fadeIn 0.5s ease-in' }}>
            
            {/* Severity Banner */}
            <div style={{
              backgroundColor: severityColors[finalResult.severity?.toLowerCase()] || severityColors.unknown,
              color: 'white',
              padding: '12px',
              borderRadius: '8px',
              textAlign: 'center',
              fontWeight: 'bold',
              textTransform: 'uppercase',
              letterSpacing: '1px'
            }}>
              {finalResult.severity} SEVERITY
            </div>

            {/* Complaint & Action */}
            <div style={{ backgroundColor: '#1B4F72', padding: '16px', borderRadius: '8px' }}>
              <div style={{ fontSize: '14px', color: '#BDC3C7', marginBottom: '4px' }}>Chief Complaint</div>
              <div style={{ fontSize: '16px', marginBottom: '16px', fontWeight: 'bold' }}>{finalResult.chief_complaint}</div>
              
              <div style={{ fontSize: '14px', color: '#BDC3C7', marginBottom: '4px' }}>Immediate Action</div>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#F1C40F' }}>{finalResult.immediate_action || 'Proceed to hospital immediately.'}</div>
            </div>

            <h2 style={{ fontSize: '20px', margin: '8px 0 0 0', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '8px' }}>
              Top 3 Hospitals
            </h2>

            {/* Hospital Cards */}
            {finalResult.top_hospitals?.map((hospital, idx) => (
              <div key={idx} style={{
                backgroundColor: 'rgba(255,255,255,0.05)',
                border: idx === 0 ? '2px solid #2ECC71' : '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px',
                padding: '16px',
                position: 'relative'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                  <div>
                    <span style={{ 
                      backgroundColor: idx === 0 ? '#2ECC71' : '#95A5A6', 
                      color: 'white', 
                      padding: '2px 8px', 
                      borderRadius: '12px', 
                      fontSize: '12px', 
                      fontWeight: 'bold',
                      marginRight: '8px'
                    }}>
                      {idx + 1}{idx === 0 ? 'st' : idx === 1 ? 'nd' : 'rd'}
                    </span>
                    <span style={{ fontSize: '18px', fontWeight: 'bold' }}>{hospital.name}</span>
                  </div>
                  {idx === 0 && finalResult.hospital_notified && (
                    <span style={{ backgroundColor: 'rgba(46, 204, 113, 0.2)', color: '#2ECC71', padding: '4px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold' }}>
                      ✓ Notified
                    </span>
                  )}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', marginBottom: '16px', fontSize: '14px' }}>
                  <div style={metricStyle}>
                    <div style={metricLabelStyle}>Distance</div>
                    <div style={metricValueStyle}>{hospital.distance_km?.toFixed(1)} km</div>
                  </div>
                  <div style={metricStyle}>
                    <div style={metricLabelStyle}>ETA</div>
                    <div style={{...metricValueStyle, color: '#E74C3C'}}>{hospital.eta_minutes} min</div>
                  </div>
                  <div style={metricStyle}>
                    <div style={metricLabelStyle}>Beds</div>
                    <div style={metricValueStyle}>{hospital.beds_available}</div>
                  </div>
                </div>

                <a 
                  href={hospital.maps_directions_url} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  style={{
                    display: 'block',
                    backgroundColor: idx === 0 ? '#3498DB' : 'rgba(255,255,255,0.1)',
                    color: 'white',
                    textAlign: 'center',
                    padding: '12px',
                    borderRadius: '8px',
                    textDecoration: 'none',
                    fontWeight: 'bold'
                  }}
                >
                  Get Directions
                </a>
              </div>
            ))}

            <div style={{ fontSize: '12px', color: '#BDC3C7', textAlign: 'center', marginTop: '8px', fontStyle: 'italic' }}>
              {finalResult.disclaimer}
            </div>

            <button 
              onClick={handleNewSearch}
              style={{
                backgroundColor: 'transparent',
                color: 'white',
                border: '1px solid rgba(255,255,255,0.2)',
                padding: '16px',
                borderRadius: '8px',
                fontSize: '16px',
                cursor: 'pointer',
                marginTop: '16px'
              }}
            >
              Start New Search
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// Shared helper styles
const quickPickStyle = {
  backgroundColor: 'rgba(255,255,255,0.05)',
  border: '1px solid rgba(255,255,255,0.1)',
  color: 'white',
  padding: '12px 8px',
  borderRadius: '8px',
  cursor: 'pointer',
  fontSize: '14px',
  textAlign: 'center',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '8px'
};

const inputStyle = {
  backgroundColor: 'rgba(255,255,255,0.05)',
  border: '1px solid rgba(255,255,255,0.2)',
  borderRadius: '8px',
  color: 'white',
  padding: '12px',
  fontSize: '16px'
};

const metricStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: '4px'
};

const metricLabelStyle = {
  color: '#BDC3C7',
  fontSize: '12px'
};

const metricValueStyle = {
  fontWeight: 'bold',
  fontSize: '16px'
};
