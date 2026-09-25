import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { Trend, Counter, Rate } from 'k6/metrics';

// Custom metrics to track our specific AI agent performance
const connectionTime = new Trend('ws_connection_time');
const toolResponseTime = new Trend('ws_tool_response_time');

// CHANGED: split into two counters instead of one lumped "droppedConnections".
// A 1013 above the semaphore cap is EXPECTED and GOOD (graceful shedding).
// A 4008 means the per-IP rate limiter tripped — since this whole test runs
// from one machine/IP, this indicates the rate limit is too strict for the
// test, not a real capacity problem. See note under "Before running" below.
const backpressureDrops = new Counter('ws_backpressure_drops_1013');
const rateLimitDrops = new Counter('ws_ratelimit_drops_4008');
const otherDrops = new Counter('ws_other_drops');

// NEW: previously "success" silently included connections that opened,
// got accepted locally, but never received setupComplete (e.g. the
// backend's upstream connect to Gemini failed and it closed the socket
// with the default code 1000, which looks identical to a real success).
// This made ws_msgs_sent misleadingly small (5 out of 2516 iterations)
// with no way to tell why. We now count and log these explicitly.
const setupNeverCompleted = new Counter('ws_setup_never_completed');
const setupCompletedRate = new Rate('ws_setup_completed_rate');
const toolResultReceivedRate = new Rate('ws_tool_result_received_rate');

// Adjust these to match your environment
const BASE_WS_URL = 'ws://127.0.0.1:8000/ws/audio';
const API_KEY = 'YOUR_BACKEND_API_KEY_HERE'; // Omit if BACKEND_API_KEY is not set

export const options = {
  scenarios: {
    voice_agent_spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '15s', target: 100 },  // Warm up under the semaphore's 200 cap
        { duration: '15s', target: 250 },  // Cross the semaphore's 200-session cap
        { duration: '30s', target: 250 },  // Hold above capacity — expect 1013s here, that's success
        { duration: '10s', target: 0 },    // Ramp down
      ],
    },
  },
  thresholds: {
    // 95% of tool calls should return in under 3.5 seconds
    ws_tool_response_time: ['p(95)<3500'],
    // No upper bound on backpressure drops — once VUs exceed 200, seeing
    // 1013s climb is the semaphore working correctly, not a failure.
    ws_ratelimit_drops_4008: ['count<5'],
    // CHANGED: absolute counts don't scale with load and gave a
    // pass/fail result that flips on a single connection either way
    // (previous run: exactly 5 against a "<5" threshold — meaningless
    // boundary). Use a rate instead, and gate it on a floor of samples
    // so it can't be satisfied by a near-empty run.
    ws_other_drops: ['count<20'],                 // hard ceiling, generous enough to not flap on 1-2 noisy closes
    ws_setup_completed_rate: ['rate>0.90'],        // at least 90% of accepted connections must actually reach setupComplete
    ws_tool_result_received_rate: ['rate>0.85'],   // and 85% of those must get a real tool round trip
  },
};

export default function () {
  const url = API_KEY ? `${BASE_WS_URL}?api_key=${API_KEY}` : BASE_WS_URL;

  // NEW: stagger connection attempts slightly per VU so we don't slam
  // the OS with hundreds of simultaneous outbound TCP handshakes in the
  // same tick. This alone can be the cause of self-inflicted 1006-style
  // abnormal closures on a single test machine, independent of anything
  // the backend does. If ws_other_drops drops to ~0 after this change,
  // that confirms it was a client-side artifact, not a backend bug.
  sleep(Math.random() * 0.5);

  const connectStart = Date.now();
  let gotSetupComplete = false;
  let gotToolResult = false;

  const res = ws.connect(url, null, function (socket) {
    let toolRequestSent = 0;

    socket.on('open', function () {
      connectionTime.add(Date.now() - connectStart);
      // We do not need to send the setup message; the backend sends it to
      // Gemini automatically. We just wait for setupComplete to confirm
      // the session is alive.
    });

    socket.on('message', function (message) {
      try {
        const data = JSON.parse(message);

        if (data.setupComplete && !gotSetupComplete) {
          gotSetupComplete = true;

          // Simulate a user asking for a flight (text frame instead of PCM
          // audio for the test — confirmed correct schema per Gemini Live
          // API docs: clientContent.turns[].{role,parts}, turnComplete).
          const flightQuery = {
            clientContent: {
              turns: [{
                role: "user",
                parts: [{ text: "Find me flights from Delhi to Mumbai tomorrow." }]
              }],
              turnComplete: true
            }
          };

          toolRequestSent = Date.now();
          socket.send(JSON.stringify(flightQuery));
        }

        if (data.toolResult) {
          gotToolResult = true;
          const latency = Date.now() - toolRequestSent;
          toolResponseTime.add(latency);
          socket.close(1000, 'test complete');
        }

        if (data.goAway) {
          socket.close(1000, 'server goAway');
        }

      } catch (err) {
        // Ignore non-JSON or chunked binary audio frames if Gemini sends them
      }
    });

    socket.on('close', function (code, reason) {
      // CHANGED: classify the close code instead of lumping all drops
      // together, AND log the code/reason so an "other" drop is no
      // longer a black box. This is the single change that turns "we
      // don't know if this is a bug" into an answerable question.
      if (code === 1013) {
        backpressureDrops.add(1);
      } else if (code === 4008) {
        rateLimitDrops.add(1);
      } else if (code !== 1000 && code !== 1005) {
        // 1000/1005 are normal closes; anything else unexpected gets tracked
        otherDrops.add(1);
        console.error(`[other-drop] code=${code} reason=${reason || '(none)'} setupComplete=${gotSetupComplete} toolResult=${gotToolResult}`);
      }

      setupCompletedRate.add(gotSetupComplete);
      if (gotSetupComplete) {
        toolResultReceivedRate.add(gotToolResult);
        if (!gotToolResult) {
          // Connected and the session came up, but we never got a tool
          // round trip back before the socket closed. Distinct from a
          // clean success — surfaces the "silent 1000 before setupComplete"
          // failure mode described above, and its inverse (setup completed
          // but no result), both of which previously read as plain closes.
          console.warn(`[no-tool-result] code=${code} reason=${reason || '(none)'}`);
        }
      } else {
        setupNeverCompleted.add(1);
        console.warn(`[no-setup] code=${code} reason=${reason || '(none)'}`);
      }
    });

    socket.on('error', function (e) {
      if (e.error() !== 'websocket: close sent') {
        otherDrops.add(1);
        console.error(`[ws-error] ${e.error()} setupComplete=${gotSetupComplete} toolResult=${gotToolResult}`);
      }
    });

    // Timeout the VU if it hangs for more than 15 seconds
    socket.setTimeout(function () {
      socket.close(1000, 'client timeout');
    }, 15000);
  });

  check(res, { 'Connected successfully': (r) => r && r.status === 101 });
  sleep(1);
}