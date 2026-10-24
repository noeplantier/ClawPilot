import { describeLaunch, launchErrorText, sendErrorText } from "@/lib/campaignLaunch";

test("a clean launch reports the real number of messages", () => {
  expect(describeLaunch({ dispatched: 3, not_attempted: 0, blocked: null })).toEqual({
    level: "success",
    text: "Dispatched 3 messages",
  });
  expect(describeLaunch({ dispatched: 1 }).text).toBe("Dispatched 1 message");
});

test("a refusal is a warning that says what was and was not sent", () => {
  const out = describeLaunch({ dispatched: 2, not_attempted: 3, blocked: { code: "limit_daily", message: "x" } });
  expect(out.level).toBe("warning");
  expect(out.text).toBe("Daily send limit reached: 2 messages sent, 3 leads not attempted");
});

test("the pause and the kill switch are named", () => {
  expect(describeLaunch({ dispatched: 0, not_attempted: 4, blocked: { code: "paused" } }).text).toMatch(/paused/);
  expect(describeLaunch({ dispatched: 0, not_attempted: 4, blocked: { code: "kill_switch" } }).text).toMatch(/kill switch/);
});

test("nothing sent without a refusal is an explicit empty state, not a success", () => {
  const out = describeLaunch({ dispatched: 0, not_attempted: 0, blocked: null });
  expect(out.level).toBe("info");
  expect(out.text).toMatch(/Nothing was sent/);
});

test("server errors are surfaced", () => {
  expect(launchErrorText({ response: { data: { detail: "No leads assigned to this campaign" } } })).toMatch(/No leads/);
  expect(launchErrorText({ response: { data: { detail: { message: "paused" } } } })).toBe("paused");
  expect(launchErrorText(new Error("boom"))).toBe("The campaign could not be launched");
});

test("a refused single send shows the message, never an object", () => {
  expect(sendErrorText({ response: { data: { detail: { code: "paused", message: "Sending is paused" } } } })).toBe("Sending is paused");
  expect(sendErrorText({ response: { data: { detail: "Lead not found" } } })).toBe("Lead not found");
  expect(sendErrorText({})).toBe("Send failed");
});
