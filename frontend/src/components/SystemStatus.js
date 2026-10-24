import React, { useEffect, useState } from "react";

const SystemStatus = () => {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    fetch("/api/system/status")
      .then((response) => response.json())
      .then((data) => setStatus(data));
  }, []);

  if (!status) return <p>Loading...</p>;

  return (
    <div>
      <h2>System Status</h2>
      <ul>
        <li>Sandbox Active: {status.sandbox_active ? "Yes" : "No"}</li>
        <li>Recipient Allowed: {status.recipient_allowed ? "Yes" : "No"}</li>
        <li>Kill Switch Active: {status.kill_switch_active ? "Yes" : "No"}</li>
        <li>SMTP Connected: {status.smtp_connected ? "Yes" : "No"}</li>
        <li>IMAP Connected: {status.imap_connected ? "Yes" : "No"}</li>
        <li>AI Provider Connected: {status.ai_provider_connected ? "Yes" : "No"}</li>
      </ul>
    </div>
  );
};

export default SystemStatus;