#!/usr/bin/env python3
"""Synthesize minimal, friendly status sounds for a Bluetooth speaker.

Output: mono MP3 files, 44.1 kHz, each <= 3 seconds.
"""
import subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SR = 44100
# Global pitch shift in semitones (negative = lower)
TRANSPOSE = -12
OUT = "/mnt/user-data/outputs"


def note_freq(name):
    """Convert note name like 'C5' or 'F#4' to frequency in Hz."""
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
             "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    pitch, octave = name[:-1], int(name[-1])
    midi = 12 * (octave + 1) + names[pitch] + TRANSPOSE
    return 440.0 * 2 ** ((midi - 69) / 12)


def chime(freq, dur, decay=4.0, bright=0.35, attack=0.012):
    """Warm, full bell-like tone with sub-octave body and a detuned layer."""
    t = np.arange(int(SR * dur)) / SR
    # Partials: sub-octave for body, fundamental, octave, twelfth, soft shimmer
    partials = [(0.5, 0.55), (1.0, 1.0), (2.0, bright), (3.0, bright * 0.3), (4.07, bright * 0.08)]
    sig = np.zeros_like(t)
    for ratio, amp in partials:
        # Body decays slowest, higher partials fade faster
        env = np.exp(-t * decay * (0.6 if ratio < 1 else 1 + 0.8 * (ratio - 1)))
        sig += amp * env * np.sin(2 * np.pi * freq * ratio * t)
        # Slightly detuned twin on the lower partials for a chorus-like width
        if ratio <= 1.0:
            sig += 0.35 * amp * env * np.sin(2 * np.pi * freq * ratio * 1.004 * t + 0.7)
    # Gentle tape-style saturation adds density and harmonics
    sig = np.tanh(1.6 * sig / np.max(np.abs(sig))) / np.tanh(1.6)
    # Softer attack to avoid clicks and sound rounder
    a = int(SR * attack)
    sig[:a] *= np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    return sig


def place(buf, sig, start):
    """Mix a signal into the buffer at a given start time (seconds)."""
    i = int(SR * start)
    end = min(len(buf), i + len(sig))
    buf[i:end] += sig[: end - i]


def reverb(sig, mix=0.24, room=0.6):
    """Very small, soft room reverb using a decaying noise impulse response."""
    ir_len = int(SR * room)
    rng = np.random.default_rng(7)
    ir = rng.standard_normal(ir_len) * np.exp(-np.linspace(0, 7, ir_len))
    ir = sosfilt(butter(2, 3500, "low", fs=SR, output="sos"), ir)
    ir /= np.abs(ir).sum() / 8
    wet = np.convolve(sig, ir)[: len(sig)]
    return (1 - mix) * sig + mix * wet


def finish(sig, name, total):
    """Pad/trim to length, apply reverb, fade out, normalize, export MP3."""
    buf = np.zeros(int(SR * total))
    buf[: min(len(sig), len(buf))] = sig[: len(buf)]
    buf = reverb(buf)
    # Gentle high-pass to remove only sub-bass rumble
    buf = sosfilt(butter(2, 120, "high", fs=SR, output="sos"), buf)
    # Soft low-pass rounds off the top end
    buf = sosfilt(butter(2, 6000, "low", fs=SR, output="sos"), buf)
    fade = int(SR * 0.15)
    buf[-fade:] *= np.linspace(1, 0, fade) ** 2
    buf = buf / np.max(np.abs(buf)) * 0.89  # peak around -1 dBFS
    wav = f"/home/claude/{name}.wav"
    wavfile.write(wav, SR, (buf * 32767).astype(np.int16))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
                    "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "192k",
                    f"{OUT}/{name}.mp3"], check=True)


def sequence(notes, total, **kw):
    """Build a buffer from (note, start_time, duration, gain) tuples."""
    buf = np.zeros(int(SR * total))
    for n, start, dur, gain in notes:
        place(buf, gain * chime(note_freq(n), dur, **kw), start)
    return buf


# Startup: warm rising three-note arpeggio, resolving upward
startup = sequence([
    ("G4", 0.00, 1.4, 0.8),
    ("C5", 0.14, 1.4, 0.8),
    ("E5", 0.28, 1.6, 0.9),
], total=1.9, decay=2.6, bright=0.45)
finish(startup, "startup", 1.9)

# Shutdown: mirrored, falling arpeggio, a bit softer and darker
shutdown = sequence([
    ("E5", 0.00, 1.3, 0.75),
    ("C5", 0.16, 1.3, 0.8),
    ("G4", 0.32, 1.6, 0.9),
], total=1.9, decay=2.8, bright=0.32)
finish(shutdown, "shutdown", 1.9)

# Charging: quick, light two-note "plugged in" confirmation
charging = sequence([
    ("C5", 0.00, 0.6, 0.8),
    ("G5", 0.10, 0.9, 0.85),
], total=1.1, decay=4.0, bright=0.45)
finish(charging, "charging", 1.1)

# Low battery: two gentle descending pairs, lower register, noticeable but calm
low = sequence([
    ("E5", 0.00, 0.5, 0.85),
    ("A4", 0.16, 0.7, 0.9),
    ("E5", 0.70, 0.5, 0.85),
    ("A4", 0.86, 0.9, 0.9),
], total=1.9, decay=4.5, bright=0.38)
finish(low, "low_battery", 1.9)

# Full battery: bright rising four-note figure ending on a sustained major chord
full = sequence([
    ("C5", 0.00, 1.2, 0.7),
    ("E5", 0.11, 1.2, 0.7),
    ("G5", 0.22, 1.2, 0.7),
    ("C6", 0.33, 1.9, 0.75),
    ("E5", 0.33, 1.9, 0.35),
    ("G5", 0.33, 1.9, 0.35),
], total=2.5, decay=2.1, bright=0.5)
finish(full, "full_battery", 2.5)



def ping(freq, dur, decay=6.5):
    """Clear, single 'ping': fast attack, pure fundamental, light metallic shimmer."""
    t = np.arange(int(SR * dur)) / SR
    # Mostly fundamental, plus a quiet octave and inharmonic partials for the 'ting'
    partials = [(1.0, 1.0), (2.0, 0.18), (2.76, 0.12), (5.4, 0.04)]
    sig = np.zeros_like(t)
    for ratio, amp in partials:
        env = np.exp(-t * decay * (1 + 1.2 * (ratio - 1)))
        sig += amp * env * np.sin(2 * np.pi * freq * ratio * t)
    # Very fast attack gives the crisp 'p' of the ping without clicking
    a = int(SR * 0.002)
    sig[:a] *= np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    return sig


# Wake word detected: a single short, bright ping (A5 = 880 Hz after TRANSPOSE).
# Kept very short so it does not overlap with the user's spoken command.
wake = np.zeros(int(SR * 0.9))
place(wake, ping(note_freq("A6"), 0.9), 0.0)
finish(wake, "wake_word", 0.9)

# Timer finished: quick double-beep alarm ping. Loops via media_player.repeat_one
# with a 500ms playlist delay while timer_ringing is on, giving a classic
# alarm-clock beep-beep cadence rather than a one-shot chime.
timer_finished = np.zeros(int(SR * 0.6))
place(timer_finished, ping(note_freq("A5"), 0.35), 0.00)
place(timer_finished, ping(note_freq("A5"), 0.35), 0.28)
finish(timer_finished, "timer_finished", 0.6)
