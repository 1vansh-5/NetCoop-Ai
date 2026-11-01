# Four-minute demo: evidence before confidence

## Preparation

- Start the app locally and check the congestion scenario once.
- If demonstrating Gemini, configure your own key and verify model access before recording. Keep `.env` and any credentials out of the recording.
- Regenerate sample files with `python make_samples.py` if importing them.
- Keep a deterministic run available if Google quota/network access is unavailable.

## 0:00–0:30 — Establish the problem

“A slow campus connection can be a congested uplink, weak wireless signal, failing interface, or service problem. Different devices expose different measurements. NetCoop turns those scattered observations into structured evidence that specialist agents can exchange.”

Show Mission control and the seeded hostel congestion scenario. State clearly that this is synthetic campus telemetry, not a live IIT network.

## 0:30–1:30 — Show real collaboration

Run the congestion investigation. Show the three specialist branches in the 3D graph and message stream. Open an infrastructure finding to display its versioned envelope, sender/recipient, sequence, units, device and support weights.

“Performance sees the symptoms; infrastructure localizes utilization and queue drops; connectivity checks competing wireless and service explanations. The correlation agent combines their independent evidence.”

Show the affected switch, latency, utilization, drops, alternative explanations and human-review actions. Export JSON.

## 1:30–2:15 — Prove interoperability

Select legacy schema interoperability. Run it and inspect the normalization event. Point out seconds-to-milliseconds, fractional-to-percentage conversion, and missing memory warnings. The same diagnosis emerges from a different source schema without pretending missing fields are present.

## 2:15–3:00 — Demonstrate honest uncertainty

Run incomplete telemetry, then malformed input rejection. Show the insufficient-evidence result and explicit input error. Explain that an empty finding list does not establish a healthy network when measurements are missing. Briefly show the competing-fault scenario and alternative causes if time allows.

## 3:00–3:40 — Explain the agentic extension

If the live key is working, use Gemini mode and show model-generated tool_call events. Gemini may choose a device inspection or a runbook lookup based on its context; tool selection is not hardcoded. If it chooses no tool, show the mocked protocol test as engineering verification, and do not claim a live tool call occurred.

“Google Gemini has a bounded read-only investigation loop over real MCP tools. Its narrative helps the operator understand the evidence, but cannot overwrite the measured facts or scored diagnosis.”

If running offline, state that the Gemini integration is implemented but the current demonstration uses deterministic agents. Never present fallback text as model output.

## 3:40–4:00 — Close with the engineering result

Show incident history and the tests. “Our contribution is interoperable, auditable collaboration with explicit uncertainty. The next integration is an authorized telemetry collector feeding the same contract.”

## Likely judge questions

**Why not use an LLM for every agent?** Specialized deterministic agents make the evidence reproducible and inspectable; the LLM adds adaptive tool use and explanation where it helps.

**Is confidence calibrated?** No. It is a documented heuristic based on evidence strength, competition, data completeness and agent success. We explicitly label it as such.

**Is MCP actually used?** Yes. Each investigation initializes a stdio MCP session, discovers tools and invokes analysis through the tool server. The application message trace records those calls separately from protocol transport.

**Does it fix the network?** No. It produces recommendations. No production configuration is changed.

**What happens when agents or Gemini fail?** Specialist failures reduce coverage; weak evidence causes abstention. Gemini failures leave the evidence-based report available and disclose the fallback.

**What is still needed for deployment?** Authorized collectors, authentication, access isolation, operational monitoring, calibrated evaluation on labelled datasets and deployment hardening.
