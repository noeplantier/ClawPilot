import React, { useEffect, useState } from "react";

const EmailDiagnostics = () => {
  const [diagnostics, setDiagnostics] = useState(null);

  useEffect(() => {
    fetch("/api/email/diagnostics")
      .then((response) => response.json())
      .then((data) => setDiagnostics(data));
  }, []);

  if (!diagnostics) return <p>Loading...</p>;

  return (
    <div>
      <h2>Email Deliverability Diagnostics</h2>
      <ul>
        <li>SPF Status: {diagnostics.spf_status}</li>
        <li>DKIM Status: {diagnostics.dkim_status}</li>
        <li>DMARC Status: {diagnostics.dmarc_status}</li>
        <li>From Domain: {diagnostics.from_domain}</li>
        <li>Alignment Status: {diagnostics.alignment_status}</li>
        <li>Recommendations: {diagnostics.recommendations}</li>
      </ul>
    </div>
  );
};

export default EmailDiagnostics;