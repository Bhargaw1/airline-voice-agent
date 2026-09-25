import { useState, useRef, useCallback, useEffect } from 'react';

const CAPTURE_FRAME_MS = 20; 
const PLAYBACK_SAMPLE_RATE = 24000; 
const BARGE_IN_RMS_THRESHOLD = 0.12; 
const BARGE_IN_SUSTAIN_MS = 180; 

const WORKLET_SOURCE = `
class PCMCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this._frameSize = options.processorOptions.frameSize;
    this._buffer = new Float32Array(this._frameSize);
    this._offset = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (input && input[0]) {
      const channel = input[0];
      let i = 0;
      while (i < channel.length) {
        const space = this._frameSize - this._offset;
        const take = Math.min(space, channel.length - i);
        this._buffer.set(channel.subarray(i, i + take), this._offset);
        this._offset += take;
        i += take;
        if (this._offset === this._frameSize) {
          this.port.postMessage(this._buffer.slice(0));
          this._offset = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor('pcm-capture-processor', PCMCaptureProcessor);
`;

function floatTo16BitPCM(float32Array) {
  const pcm16 = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm16;
}

function base64FromInt16(pcm16) {
  const bytes = new Uint8Array(pcm16.buffer);
  let binary = '';
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

function pcm16FromBase64(base64Data) {
  const binaryString = atob(base64Data);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) bytes[i] = binaryString.charCodeAt(i);
  return new Int16Array(bytes.buffer);
}

export function useRealtimeAgent({ onFlightResults, setStatus: reportExternalStatus, isConfigured } = {}) {
  const [status, setStatus] = useState('offline');
  const [isPlaying, setIsPlaying] = useState(false);

  const captureContextRef = useRef(null);
  const playbackContextRef = useRef(null);
  const streamRef = useRef(null);
  const workletNodeRef = useRef(null);
  const workletUrlRef = useRef(null);
  const wsRef = useRef(null);

  const playbackQueueRef = useRef([]);
  const nextStartTimeRef = useRef(0);
  const isPlayingRef = useRef(false);
  const activeSourcesRef = useRef([]); 

  const setupCompleteRef = useRef(false);
  const manualStopRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);
  const sessionHandleRef = useRef(null); 
  const goAwayTimerRef = useRef(null);

  const reportStatus = useCallback(
    (message, active) => {
      if (typeof reportExternalStatus === 'function') reportExternalStatus(message, active);
    },
    [reportExternalStatus]
  );

  const stopAllPlayback = useCallback(() => {
    for (const src of activeSourcesRef.current) {
      try {
        src.onended = null;
        src.stop();
      } catch {
        /* already stopped */
      }
    }
    activeSourcesRef.current = [];
    playbackQueueRef.current = [];
    nextStartTimeRef.current = 0;
    setIsPlaying(false);
    isPlayingRef.current = false;
  }, []);

  const playNextChunk = useCallback(() => {
    const context = playbackContextRef.current;
    if (!context || playbackQueueRef.current.length === 0) {
      setIsPlaying(false);
      isPlayingRef.current = false;
      return;
    }
    setIsPlaying(true);
    isPlayingRef.current = true;

    const base64Data = playbackQueueRef.current.shift();
    const pcm16 = pcm16FromBase64(base64Data);
    const float32 = new Float32Array(pcm16.length);
    for (let i = 0; i < pcm16.length; i++) float32[i] = pcm16[i] / 32768.0;

    const buffer = context.createBuffer(1, float32.length, PLAYBACK_SAMPLE_RATE);
    buffer.copyToChannel(float32, 0);

    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);

    const startTime = Math.max(context.currentTime, nextStartTimeRef.current);
    source.start(startTime);
    nextStartTimeRef.current = startTime + buffer.duration;

    activeSourcesRef.current.push(source);
    source.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
      playNextChunk();
    };
  }, []);

  const cleanupAudioGraph = useCallback(() => {
    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.port.onmessage = null;
        workletNodeRef.current.disconnect();
      } catch {
        /* noop */
      }
      workletNodeRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (captureContextRef.current) {
      captureContextRef.current.close().catch(() => {});
      captureContextRef.current = null;
    }
    if (playbackContextRef.current) {
      playbackContextRef.current.close().catch(() => {});
      playbackContextRef.current = null;
    }
    if (workletUrlRef.current) {
      URL.revokeObjectURL(workletUrlRef.current);
      workletUrlRef.current = null;
    }
    if (goAwayTimerRef.current) {
      clearTimeout(goAwayTimerRef.current);
      goAwayTimerRef.current = null;
    }
  }, []);

  const stopSession = useCallback(() => {
    manualStopRef.current = true;
    setupCompleteRef.current = false;
    setStatus('offline');
    stopAllPlayback();
    cleanupAudioGraph();

    if (wsRef.current) {
      wsRef.current.close(1000, 'client stop');
      wsRef.current = null;
    }
    reportStatus('Agent Offline', false);
  }, [cleanupAudioGraph, reportStatus, stopAllPlayback]);

  const sendSetup = useCallback((ws) => {
    ws.send(
      JSON.stringify({
        setup: {
          sessionResumption: sessionHandleRef.current ? { handle: sessionHandleRef.current } : {},
        },
      })
    );
  }, []);

  const scheduleReconnect = useCallback(
    (startFn) => {
      if (manualStopRef.current) return;
      if (reconnectAttemptsRef.current >= 5) {
        setStatus('error');
        reportStatus('Could not reconnect — please retry manually', false);
        return;
      }
      const attempt = reconnectAttemptsRef.current + 1;
      reconnectAttemptsRef.current = attempt;
      const delay = Math.min(1000 * 2 ** attempt, 15000) + Math.random() * 400;
      reportStatus(`Reconnecting in ${Math.round(delay / 1000)}s...`, false);
      setTimeout(() => {
        if (!manualStopRef.current) startFn(true);
      }, delay);
    },
    [reportStatus]
  );

  const startSession = useCallback(
    async (isReconnect = false) => {
      if (status === 'online' || status === 'connecting') return;
      manualStopRef.current = false;
      if (!isReconnect) {
        reconnectAttemptsRef.current = 0;
        sessionHandleRef.current = null;
      }

      if (isConfigured === false) {
        reportStatus('Voice agent not configured', false);
        setStatus('error');
        return;
      }

      setStatus('connecting');
      reportStatus(isReconnect ? 'Reconnecting...' : 'Connecting...', true);

      try {
        const captureContext = new (window.AudioContext || window.webkitAudioContext)();
        captureContextRef.current = captureContext;
        const playbackContext = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: PLAYBACK_SAMPLE_RATE,
        });
        playbackContextRef.current = playbackContext;

        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        streamRef.current = stream;

        const workletBlob = new Blob([WORKLET_SOURCE], { type: 'application/javascript' });
        const workletUrl = URL.createObjectURL(workletBlob);
        workletUrlRef.current = workletUrl;
        await captureContext.audioWorklet.addModule(workletUrl);

        const frameSize = Math.round((captureContext.sampleRate * CAPTURE_FRAME_MS) / 1000);
        const sourceNode = captureContext.createMediaStreamSource(stream);
        const workletNode = new AudioWorkletNode(captureContext, 'pcm-capture-processor', {
          processorOptions: { frameSize },
        });
        workletNodeRef.current = workletNode;

        const backendHttpUrl = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';
        const wsUrl = backendHttpUrl.replace(/^http/, 'ws') + '/ws/audio';
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          reconnectAttemptsRef.current = 0;
          if (sessionHandleRef.current) sendSetup(ws);
        };

        ws.onmessage = (event) => {
          try {
            const text = typeof event.data === 'string' ? event.data : new TextDecoder().decode(event.data);
            const msg = JSON.parse(text);

            if (msg.setupComplete) {
              setupCompleteRef.current = true;
              setStatus('online');
              reportStatus('Agent Online', true);
              return;
            }

            if (msg.toolResult) {
              if (typeof onFlightResults === 'function') {
                onFlightResults(msg.toolResult.data, msg.toolResult.name);
              }
              return;
            }

            if (msg.serverContent?.interrupted) {
              stopAllPlayback();
              return;
            }

            if (msg.serverContent?.modelTurn?.parts) {
              for (const part of msg.serverContent.modelTurn.parts) {
                if (part.inlineData?.data) {
                  playbackQueueRef.current.push(part.inlineData.data);
                  if (!isPlayingRef.current) playNextChunk();
                }
              }
              return;
            }

            if (msg.goAway) {
              const seconds = msg.goAway.timeLeft ? parseFloat(msg.goAway.timeLeft) : 5;
              reportStatus('Refreshing session...', true);
              if (goAwayTimerRef.current) clearTimeout(goAwayTimerRef.current);
              goAwayTimerRef.current = setTimeout(() => {
                if (wsRef.current) wsRef.current.close(1000, 'proactive refresh');
              }, Math.max(0, (seconds - 1) * 1000));
              return;
            }

            if (msg.sessionResumptionUpdate?.resumable && msg.sessionResumptionUpdate?.newHandle) {
              sessionHandleRef.current = msg.sessionResumptionUpdate.newHandle;
              return;
            }
          } catch (err) {
            console.error('[Voice Agent] Error parsing message:', err);
          }
        };

        ws.onerror = () => {};

        ws.onclose = (event) => {
          setupCompleteRef.current = false;
          cleanupAudioGraph();
          if (manualStopRef.current || event.code === 1000) {
            setStatus('offline');
            reportStatus('Agent Offline', false);
            return;
          }
          setStatus('error');
          scheduleReconnect(startSession);
        };

        let sustainedFramesAboveThreshold = 0;
        workletNode.port.onmessage = (e) => {
          const floatFrame = e.data; 
          if (ws.readyState !== WebSocket.OPEN || !setupCompleteRef.current) return;

          let sumSq = 0;
          for (let i = 0; i < floatFrame.length; i++) sumSq += floatFrame[i] * floatFrame[i];
          const rms = Math.sqrt(sumSq / floatFrame.length);
          if (rms > BARGE_IN_RMS_THRESHOLD) {
            sustainedFramesAboveThreshold += CAPTURE_FRAME_MS;
          } else {
            sustainedFramesAboveThreshold = 0;
          }
          void sustainedFramesAboveThreshold;

          const pcm16 = floatTo16BitPCM(floatFrame);
          const base64Audio = base64FromInt16(pcm16);
          ws.send(
            JSON.stringify({
              realtimeInput: {
                audio: {
                  data: base64Audio,
                  mimeType: `audio/pcm;rate=${captureContext.sampleRate}`,
                },
              },
            })
          );
        };

        sourceNode.connect(workletNode);
      } catch (error) {
        cleanupAudioGraph();
        if (wsRef.current) {
          wsRef.current.close();
          wsRef.current = null;
        }
        const message = error.name === 'NotAllowedError' ? 'Microphone permission denied' : 'Agent Error';
        setStatus('error');
        reportStatus(message, false);
      }
    },
    [status, isConfigured, reportStatus, playNextChunk, onFlightResults, cleanupAudioGraph, scheduleReconnect, sendSetup, stopAllPlayback]
  );

  useEffect(() => {
    return () => stopSession();
  }, []);

  const handleMicClick = useCallback(() => {
    if (status === 'online' || status === 'connecting') {
      stopSession();
    } else {
      startSession(false);
    }
  }, [status, startSession, stopSession]);

  return {
    status,
    isPlaying,
    isCalling: status === 'connecting',
    realtimeConnected: status === 'online',
    isListening: status === 'online',
    startAgentCall: startSession,
    stopAgentCall: stopSession,
    handleMicClick,
  };
}