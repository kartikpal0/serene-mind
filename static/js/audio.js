/* Web Audio API generative ambient soundscapes & gentle breathing chimes */

class AmbientAudioEngine {
  constructor() {
    this.ctx = null;
    this.channels = new Map();
  }

  ensureContext() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AudioCtx();
    }
    if (this.ctx.state === "suspended") {
      this.ctx.resume();
    }
    return this.ctx;
  }

  createPinkNoiseBuffer(ctx, seconds = 4) {
    const bufferSize = ctx.sampleRate * seconds;
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const output = buffer.getChannelData(0);
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
    for (let i = 0; i < bufferSize; i++) {
      const white = Math.random() * 2 - 1;
      b0 = 0.99886 * b0 + white * 0.0555179;
      b1 = 0.99332 * b1 + white * 0.0750759;
      b2 = 0.96900 * b2 + white * 0.1538520;
      b3 = 0.86650 * b3 + white * 0.3104856;
      b4 = 0.55000 * b4 + white * 0.5329522;
      b5 = -0.7616 * b5 - white * 0.0168980;
      output[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.05;
      b6 = white * 0.115926;
    }
    return buffer;
  }

  startSound(id, volume = 0.35) {
    if (this.channels.has(id)) {
      this.setVolume(id, volume);
      return;
    }
    const ctx = this.ensureContext();
    const masterGain = ctx.createGain();
    masterGain.gain.setValueAtTime(0.001, ctx.currentTime);
    masterGain.gain.exponentialRampToValueAtTime(Math.max(0.02, volume * 0.45), ctx.currentTime + 0.8);
    masterGain.connect(ctx.destination);

    const stopCallbacks = [];

    if (id === "rain" || id === "pink" || id === "breeze") {
      const src = ctx.createBufferSource();
      src.buffer = this.createPinkNoiseBuffer(ctx, 4);
      src.loop = true;

      const filter = ctx.createBiquadFilter();
      if (id === "rain") {
        filter.type = "bandpass";
        filter.frequency.value = 950;
        filter.Q.value = 0.6;
      } else if (id === "breeze") {
        filter.type = "lowpass";
        filter.frequency.value = 520;
        const lfo = ctx.createOscillator();
        const lfoGain = ctx.createGain();
        lfo.frequency.value = 0.12;
        lfoGain.gain.value = 220;
        lfo.connect(lfoGain);
        lfoGain.connect(filter.frequency);
        lfo.start();
        stopCallbacks.push(() => lfo.stop());
      } else {
        filter.type = "lowpass";
        filter.frequency.value = 340;
      }

      src.connect(filter);
      filter.connect(masterGain);
      src.start();
      stopCallbacks.push(() => src.stop());
    } else if (id === "bowl") {
      const freqs = [216, 432, 648];
      freqs.forEach((f, idx) => {
        const osc = ctx.createOscillator();
        const oscGain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = f;
        oscGain.gain.value = idx === 0 ? 0.25 : idx === 1 ? 0.16 : 0.05;
        osc.connect(oscGain);
        oscGain.connect(masterGain);
        osc.start();
        stopCallbacks.push(() => osc.stop());
      });
    }

    this.channels.set(id, { masterGain, stopCallbacks, volume });
  }

  setVolume(id, volume) {
    const ch = this.channels.get(id);
    if (!ch || !this.ctx) return;
    ch.volume = volume;
    ch.masterGain.gain.setTargetAtTime(Math.max(0.001, volume * 0.45), this.ctx.currentTime, 0.15);
  }

  stopSound(id) {
    const ch = this.channels.get(id);
    if (!ch || !this.ctx) return;
    const ctx = this.ctx;
    ch.masterGain.gain.setTargetAtTime(0.0001, ctx.currentTime, 0.2);
    setTimeout(() => {
      ch.stopCallbacks.forEach((fn) => {
        try {
          fn();
        } catch {
          // ignore already stopped
        }
      });
      ch.masterGain.disconnect();
    }, 350);
    this.channels.delete(id);
  }

  stopAll() {
    [...this.channels.keys()].forEach((id) => this.stopSound(id));
  }

  isPlaying(id) {
    return this.channels.has(id);
  }

  playSoftChime(freq = 432) {
    try {
      const ctx = this.ensureContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, ctx.currentTime);
      gain.gain.setValueAtTime(0.001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.08, ctx.currentTime + 0.08);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 1.4);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 1.5);
    } catch {
      // Audio playback blocked before interaction
    }
  }
}

export const soundEngine = new AmbientAudioEngine();
