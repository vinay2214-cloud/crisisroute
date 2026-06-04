import React, { useState, useEffect } from "react";

const API_URL =
  "https://crisisroute-backend-1091867759974.asia-south1.run.app";

function Dashboard() {
  const [stats, setStats] = useState(null);
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    try {
      // Fetch system stats
      const statsRes = await fetch(`${API_URL}/api/dashboard/stats`);
      if (!statsRes.ok) throw new Error("Failed to load statistics");
      const statsData = await statsRes.json();
      setStats(statsData);

      // Fetch recent cases
      const casesRes = await fetch(`${API_URL}/api/dashboard/cases?limit=20`);
      if (!casesRes.ok) throw new Error("Failed to load recent cases");
      const casesData = await casesRes.json();
      setCases(casesData.cases || []);

      setError(null);
    } catch (err) {
      console.error(err);
      setError("Failed to synchronize dashboard metrics.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Auto-refresh every 15 seconds for live alerts/updates
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, []);

  const navigateToHome = () => {
    window.location.hash = "";
  };

  // Live Alerts: Cases from last 10 minutes
  const now = new Date();
  const tenMinutesAgo = new Date(now.getTime() - 10 * 60 * 1000);
  const liveAlerts = cases.filter(c => {
    const caseTime = new Date(c.timestamp);
    return caseTime >= tenMinutesAgo;
  });

  return (
    <div style={styles.container}>
      {/* Header */}
      <header style={styles.header}>
        <div style={styles.logoGroup}>
          <div style={styles.beacon}></div>
          <h1 style={styles.title}>CrisisRoute Live Command</h1>
        </div>
        <button style={styles.backBtn} onClick={navigateToHome}>
          ← Back to Triage app
        </button>
      </header>

      {error && <div style={styles.error}>{error}</div>}

      {/* SECTION 1 - System Stats Bar */}
      <div style={styles.statsBar}>
        <div style={styles.statCard}>
          <span style={styles.statLabel}>Total AP Hospitals</span>
          <span style={styles.statVal}>
            {stats ? stats.total_hospitals : "..."}
          </span>
        </div>
        
        <div style={styles.statCard}>
          <span style={styles.statLabel}>Available Beds</span>
          <span style={{ 
            ...styles.statVal, 
            color: stats ? (stats.available_beds > 500 ? "#27AE60" : stats.available_beds > 100 ? "#F39C12" : "#E74C3C") : "#fff" 
          }}>
            {stats ? stats.available_beds : "..."}
          </span>
        </div>

        <div style={styles.statCard}>
          <span style={styles.statLabel}>Available ICU Beds</span>
          <span style={styles.statVal} className="font-data">
            {stats ? stats.available_icu : "..."}
          </span>
        </div>

        <div style={styles.statCard}>
          <span style={styles.statLabel}>Active Cases (24h)</span>
          <span style={styles.statVal} className="font-data">
            {cases ? cases.length : "0"}
          </span>
        </div>
      </div>

      <div style={styles.dashboardGrid}>
        
        {/* Left Side: District capacity bar chart */}
        <section style={styles.chartCard}>
          <h3 style={styles.sectionTitle}>District Capacity Distribution</h3>
          <p style={styles.sectionDesc}>Visual metrics representing available beds relative to district capacity.</p>
          
          <div style={styles.chartContainer}>
            {stats && stats.by_district && stats.by_district.length > 0 ? (
              stats.by_district.map((d, idx) => {
                // Calculate percentage capacity (max scale assumed 1500 beds)
                const maxDistrictBeds = 1500;
                const percentage = Math.min(100, (d.available_beds / maxDistrictBeds) * 100);
                
                // Color mapping: >50% available = green, 20-50% = orange, <20% = red
                const barColor = percentage > 50 ? "#27AE60" : percentage > 20 ? "#F39C12" : "#E74C3C";
                
                return (
                  <div key={idx} style={styles.chartRow}>
                    <div style={styles.districtLabel}>{d.district}</div>
                    <div style={styles.barWrapper}>
                      <div style={{
                        ...styles.barFill,
                        width: `${percentage}%`,
                        backgroundColor: barColor
                      }}></div>
                    </div>
                    <div style={styles.bedCountLabel}>{d.available_beds} beds</div>
                  </div>
                );
              })
            ) : (
              <div style={styles.emptyText}>No district statistics loaded.</div>
            )}
          </div>
        </section>

        {/* Right Side: Live Alerts (Last 10 minutes) */}
        <section style={styles.alertsCard}>
          <h3 style={styles.sectionTitle}>Live Emergency Alerts</h3>
          <p style={styles.sectionDesc}>Critical dispatches pushed within the last 10 minutes.</p>
          
          <div style={styles.alertsList}>
            {liveAlerts.length > 0 ? (
              liveAlerts.map((c, idx) => {
                const isCritical = c?.triage_severity === "critical";
                return (
                  <div key={idx} style={{
                    ...styles.alertItem,
                    borderColor: isCritical ? "#E74C3C" : "rgba(255,255,255,0.08)",
                    backgroundColor: isCritical ? "rgba(231,76,60,0.1)" : "rgba(15,23,42,0.3)"
                  }}>
                    <div style={styles.alertHeader}>
                      <span style={{
                        ...styles.alertSeverity,
                        color: isCritical ? "#E74C3C" : c?.triage_severity === "urgent" ? "#F39C12" : "#27AE60"
                      }}>{(c?.triage_severity || "unknown").toUpperCase()}</span>
                      <span style={styles.alertTime}>
                        {new Date(c?.timestamp || "").toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                    </div>
                    <div style={styles.alertBody}>
                      <strong>{c?.patient_name || "Patient"} ({c?.patient_age || 0} yo)</strong>
                      <p style={styles.alertComplaint}>{c?.chief_complaint || "Unknown Complaint"}</p>
                      <div style={styles.alertDestination}>
                        🏥 Routed to <b>{c?.hospital_selected_name || "Hospital"}</b> (ETA: {c?.eta_minutes || 0}m)
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div style={styles.emptyText}>No emergency dispatches in the last 10 minutes.</div>
            )}
          </div>
        </section>
      </div>

      {/* SECTION 3 - Recent Cases Table */}
      <section style={styles.tableCard}>
        <h3 style={styles.sectionTitle}>Triage Dispatch Log (Last 20 Cases)</h3>
        
        <div style={styles.tableResponsive}>
          <table style={styles.table}>
            <thead>
              <tr style={styles.trHead}>
                <th style={styles.th}>Time</th>
                <th style={styles.th}>Case ID</th>
                <th style={styles.th}>Severity</th>
                <th style={styles.th}>Chief Complaint</th>
                <th style={styles.th}>Specialty</th>
                <th style={styles.th}>Selected Hospital</th>
                <th style={styles.th}>ETA</th>
                <th style={styles.th}>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c, idx) => {
                const sevColor = c?.triage_severity === "critical" ? "#E74C3C" : c?.triage_severity === "urgent" ? "#F39C12" : "#27AE60";
                return (
                  <tr key={idx} style={styles.trBody}>
                    <td style={styles.td}>
                      {new Date(c?.timestamp || "").toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td style={styles.td}><b>{c?.case_id || "CR-UNKNOWN"}</b></td>
                    <td style={styles.td}>
                      <span style={{
                        ...styles.tableSeverityBadge,
                        color: sevColor,
                        borderColor: sevColor,
                        backgroundColor: `${sevColor}22`
                      }}>
                        {(c?.triage_severity || "unknown").toUpperCase()}
                      </span>
                    </td>
                    <td style={styles.td}>{c?.chief_complaint || ""}</td>
                    <td style={styles.td}>{(c?.specialty_matched || "unknown").toUpperCase()}</td>
                    <td style={styles.td}>{c?.hospital_selected_name || "Hospital"}</td>
                    <td style={styles.td} className="font-data">{c?.eta_minutes || 0} min</td>
                    <td style={styles.td}>
                      <span style={{
                        ...styles.statusBadge,
                        backgroundColor: c?.outcome_status === "dispatched" ? "rgba(124, 58, 237, 0.2)" : "rgba(16, 185, 129, 0.2)",
                        color: c?.outcome_status === "dispatched" ? "#c084fc" : "#10b981"
                      }}>
                        {c?.outcome_status || "dispatched"}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {cases.length === 0 && (
                <tr>
                  <td colSpan="8" style={styles.noDataCell}>No emergency dispatches recorded in the index.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

const styles = {
  container: {
    backgroundColor: "#0A0F1E",
    minHeight: "100vh",
    color: "#F8FAFC",
    padding: "24px",
    fontFamily: "'Inter', system-ui, sans-serif",
    boxSizing: "border-box"
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "24px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
    paddingBottom: "16px"
  },
  logoGroup: {
    display: "flex",
    alignItems: "center",
    gap: "12px"
  },
  beacon: {
    width: "12px",
    height: "12px",
    borderRadius: "50%",
    backgroundColor: "#E74C3C",
    boxShadow: "0 0 10px #E74C3C",
    animation: "pulse 2s infinite"
  },
  title: {
    fontSize: "24px",
    fontWeight: "800",
    letterSpacing: "-0.5px",
    margin: 0,
    background: "linear-gradient(135deg, #fff 0%, #c084fc 100%)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent"
  },
  backBtn: {
    background: "rgba(255, 255, 255, 0.05)",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    color: "#fff",
    padding: "8px 16px",
    borderRadius: "6px",
    fontSize: "12px",
    fontWeight: "600",
    cursor: "pointer",
    transition: "all 0.2s"
  },
  error: {
    backgroundColor: "rgba(231, 76, 60, 0.15)",
    border: "1px solid #E74C3C",
    color: "#E74C3C",
    padding: "12px",
    borderRadius: "8px",
    marginBottom: "24px",
    fontSize: "13px",
    textAlign: "left"
  },
  statsBar: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: "20px",
    marginBottom: "24px"
  },
  statCard: {
    background: "rgba(30, 41, 59, 0.45)",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "12px",
    padding: "20px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center"
  },
  statLabel: {
    fontSize: "11px",
    color: "#94A3B8",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
    marginBottom: "8px"
  },
  statVal: {
    fontSize: "28px",
    fontWeight: "850",
    color: "#fff"
  },
  dashboardGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 450px",
    gap: "24px",
    marginBottom: "24px"
  },
  chartCard: {
    background: "rgba(30, 41, 59, 0.45)",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "16px",
    padding: "24px",
    textAlign: "left"
  },
  sectionTitle: {
    fontSize: "18px",
    fontWeight: "700",
    color: "#fff",
    margin: "0 0 4px 0"
  },
  sectionDesc: {
    fontSize: "12px",
    color: "#94A3B8",
    margin: "0 0 20px 0"
  },
  chartContainer: {
    display: "flex",
    flexDirection: "column",
    gap: "16px"
  },
  chartRow: {
    display: "flex",
    alignItems: "center",
    gap: "12px"
  },
  districtLabel: {
    width: "120px",
    fontSize: "13px",
    fontWeight: "600",
    color: "#F8FAFC"
  },
  barWrapper: {
    flex: 1,
    height: "12px",
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    borderRadius: "6px",
    overflow: "hidden"
  },
  barFill: {
    height: "100%",
    borderRadius: "6px",
    transition: "width 0.5s ease-out"
  },
  bedCountLabel: {
    width: "70px",
    fontSize: "12px",
    fontWeight: "600",
    textAlign: "right",
    color: "#94A3B8"
  },
  alertsCard: {
    background: "rgba(30, 41, 59, 0.45)",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "16px",
    padding: "24px",
    textAlign: "left"
  },
  alertsList: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    maxHeight: "350px",
    overflowY: "auto"
  },
  alertItem: {
    borderLeftWidth: "4px",
    borderLeftStyle: "solid",
    borderTop: "1px solid rgba(255,255,255,0.08)",
    borderRight: "1px solid rgba(255,255,255,0.08)",
    borderBottom: "1px solid rgba(255,255,255,0.08)",
    borderRadius: "8px",
    padding: "12px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.2)"
  },
  alertHeader: {
    display: "flex",
    justifyContent: "space-between",
    fontSize: "11px",
    marginBottom: "6px"
  },
  alertSeverity: {
    fontWeight: "800"
  },
  alertTime: {
    color: "#94A3B8"
  },
  alertBody: {
    fontSize: "12px"
  },
  alertComplaint: {
    margin: "4px 0 8px 0",
    color: "#94A3B8",
    fontStyle: "italic"
  },
  alertDestination: {
    fontSize: "11px",
    background: "rgba(0,0,0,0.2)",
    padding: "6px 8px",
    borderRadius: "4px"
  },
  tableCard: {
    background: "rgba(30, 41, 59, 0.45)",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    borderRadius: "16px",
    padding: "24px",
    textAlign: "left"
  },
  tableResponsive: {
    width: "100%",
    overflowX: "auto",
    borderRadius: "8px",
    border: "1px solid rgba(255, 255, 255, 0.08)"
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "13px"
  },
  trHead: {
    background: "rgba(15, 23, 42, 0.8)"
  },
  th: {
    padding: "12px 16px",
    fontWeight: "600",
    color: "#fff",
    textTransform: "uppercase",
    fontSize: "10px",
    letterSpacing: "0.5px"
  },
  trBody: {
    borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
    background: "rgba(30, 41, 59, 0.2)"
  },
  td: {
    padding: "12px 16px",
    color: "#E2E8F0"
  },
  tableSeverityBadge: {
    padding: "2px 6px",
    fontSize: "9px",
    fontWeight: "700",
    borderRadius: "3px",
    borderWidth: "1px",
    borderStyle: "solid"
  },
  statusBadge: {
    padding: "2px 6px",
    fontSize: "9px",
    fontWeight: "700",
    borderRadius: "4px",
    textTransform: "uppercase"
  },
  noDataCell: {
    colSpan: 8,
    textAlign: "center",
    padding: "24px",
    color: "#94A3B8"
  },
  emptyText: {
    color: "#94A3B8",
    fontSize: "12px",
    textAlign: "center",
    padding: "24px"
  }
};

export default Dashboard;
