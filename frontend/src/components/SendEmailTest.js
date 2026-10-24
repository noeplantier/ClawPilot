import React, { useState } from "react";

const SendEmailTest = () => {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    const response = await fetch("/api/email/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to: email, subject: "Test", body: "This is a test email." }),
    });
    const data = await response.json();
    setStatus(data.detail || data.status);
  };

  return (
    <div>
      <h2>Send Test Email</h2>
      <form onSubmit={handleSubmit}>
        <input
          type="email"
          placeholder="Recipient Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <button type="submit">Send</button>
      </form>
      {status && <p>{status}</p>}
    </div>
  );
};

export default SendEmailTest;