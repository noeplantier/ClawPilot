// What the server really did when a campaign step was launched or run. No invented numbers: the counters come from
// the response, and a refusal (pause, limit, kill switch) is shown as a refusal, not as a success.

const BLOCK_REASON = {
  paused: "Sending is paused for this organisation",
  kill_switch: "Sending is halted by the kill switch",
  limit_daily: "Daily send limit reached",
  limit_hourly: "Hourly send limit reached",
  limit_delay: "Minimum delay between messages not elapsed",
};

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

export function describeLaunch(data) {
  const dispatched = data.dispatched ?? 0;
  const notAttempted = data.not_attempted ?? 0;
  if (data.blocked) {
    const reason = BLOCK_REASON[data.blocked.code] || data.blocked.message || data.blocked.code;
    return {
      level: "warning",
      text: `${reason}: ${plural(dispatched, "message")} sent, ${plural(notAttempted, "lead")} not attempted`,
    };
  }
  if (dispatched === 0) {
    return { level: "info", text: "Nothing was sent (no eligible lead: missing contact or consent)" };
  }
  return { level: "success", text: `Dispatched ${plural(dispatched, "message")}` };
}

// The server answers a refused send with `detail: {code, message, retry_at}` and other errors with a string.
export function sendErrorText(err, fallback = "Send failed") {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  return detail?.message || fallback;
}

export const launchErrorText = (err) => sendErrorText(err, "The campaign could not be launched");
