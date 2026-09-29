# Ikea Kallsup

**Multi-room media player and voice assistant, on the original enclosure**

An [ESPHome](https://esphome.io) replacement for the stock control board inside
an IKEA KALLSUP speaker. Plays synchronized multi-room audio via the
[Sendspin](https://esphome.io/components/sendspin/) protocol (Music
Assistant), streams arbitrary HTTP audio, and doubles as a Home Assistant
Assist voice satellite with local wake word detection. A status NeoPixel and
battery monitoring round it out for running off a LiPo. Reports to Home
Assistant over the encrypted native API.

Source: [Converting new (5€) Ikea Kallsup speaker into a ESPHome media player](https://community.home-assistant.io/t/converting-new-5-ikea-kallsup-speaker-into-a-esphome-media-player/1000870)

---

## Hardware

| Amount | Item | Notes |
|--:|---|---|
| 1 | Seeed XIAO ESP32S3 | 8 MB Flash, 8 MB Octal PSRAM |
| 1 | MAX98357A | I2S amplifier, drives the Kallsup's own speaker |
| 1 | INMP441 | I2S digital MEMS microphone, for wake word / Assist |
| 1 | WS2812 / NeoPixel | Single-LED status indicator |
| 1 | LiPo battery | Via the XIAO's onboard charge circuit |
| 2 | 220kOhm resistor | Battery voltage divider |
| 2 | Momentary buttons | Reused from the original Kallsup speaker (Play, BT) |

```
XIAO ESP32S3        MAX98357A              INMP441
─────────────        ─────────              ───────
GPIO07 (LRCLK)  ───── LRC
GPIO08 (DOUT)   ───── DIN
GPIO09 (BCLK)   ───── BCLK
3V3             ───── SD    (direct wire, not floating - see caveat below)

GPIO01 (LRCLK)  ──────────────────────────── WS
GPIO02 (BCLK)   ──────────────────────────── SCK
GPIO05 (DIN)    ──────────────────────────── SD

GPIO04  ── Button Play
GPIO43  ── Button BT
GPIO44  ── NeoPixel data in
GPIO06  ── Battery voltage divider midpoint (BAT+ ─ 220k ─ *GPIO06* ─ 220k ─ GND)
GPIO03  ── Charge LED tap (leg towards the charging IC, not the 3.3V/GND rail)
```

All pin numbers above are **GPIO numbers**, not the `D0`-`D10` silkscreen
labels printed on the XIAO board - those two numberings do not line up
1:1. Wiring by the silkscreen label instead of the GPIO number was the
actual cause of an extended "no sound, everything else looks fine"
debugging session on this build: `D7` on the board is `GPIO44`, not
`GPIO07`. The full mapping:

| Label | GPIO | | Label | GPIO |
|---|---|---|---|---|
| D0 | GPIO1 | | D6 | GPIO43 |
| D1 | GPIO2 | | D7 | GPIO44 |
| D2 | GPIO3 | | D8 | GPIO7 |
| D3 | GPIO4 | | D9 | GPIO8 |
| D4 | GPIO5 | | D10 | GPIO9 |
| D5 | GPIO6 | | | |

The microphone sits on its own I2S bus (`i2s_audio_input`, GPIO01/02/05),
separate from the speaker's (`i2s_audio_output`, GPIO07/08/09) - the ESP32S3
has two independent I2S peripherals, and sharing one bus between mic input
and speaker output is a common source of crosstalk/noise.

**MAX98357A's SD pin must be actively driven high**, not left floating: it's
a combined shutdown/channel-select input, and an unreliable float (or a weak
external pull-up fighting the pin's own input leakage) can settle low enough
to read as shutdown - measured 0.3V against a ~3.3V high on the unit built
here, despite a resistor already present from VCC to SD. Wiring SD straight
to 3V3 sidesteps the ambiguity outright. `GAIN` tied to GND (12dB) and a 4Ω
speaker both work fine and don't need any special handling.

Every GPIO on the XIAO's 11-pin header is used by this config. GPIO03 (the
charge LED tap) is the exception worth knowing about: it's the ESP32-S3's
JTAG-source strapping pin, only sampled during the reset pulse - a steady
tap there shouldn't affect boot, but this hasn't been verified against an
actual schematic (none is published for the standard, non-Plus XIAO
ESP32S3).

The board also has an onboard, orange **User LED** on GPIO21 - not part of
the 11-pin header, so it doesn't need any wiring or compete with the pins
above. It's active-low (driving the pin high turns it off) and used here as
a second status indicator (see [Status LED](#status-led)).

---

## Installation

Needs a `secrets.yaml` next to the config with:

```yaml
wifi_ssid: "..."
wifi_password: "..."
wifi_ap_password: "..."     # fallback AP, at least 8 characters
api_encryption_key: "..."   # base64, 32 bytes
ota_password: "..."
```

Sound files are played on various events (see [Sounds](#sounds) below) and
must exist under `sounds/` relative to the config - already included in this
repo.

Then:

```sh
esphome run ikea-kallsup.yaml
```

Everything after the first flash goes over the air.

---

## Entities

### Media

| Entity | Does |
|---|---|
| Ikea Kallsup Player | Plays synchronized audio (Sendspin/HTTP/local file) through the MAX98357A |
| sendspin_group_media_player | Controls a Sendspin group (volume, transport). Does not play audio itself |

### Control

| Entity | Does |
|---|---|
| Status LED | The NeoPixel, as a regular light entity - red/blue overlays (see [Status LED](#status-led)) can be overridden manually here |
| Wake Word Sensitivity | Slightly / Moderately / Very sensitive - adjusts how easily `okay_nabu`/`hey_jarvis` trigger (see [Voice assistant](#voice-assistant)) |
| User LED | The onboard GPIO21 LED, on while a wake word is being processed (see [Status LED](#status-led)) - not tied to battery state |
| Wake Sound | Toggles `wake_word.mp3` on/off - wake word detection itself is unaffected |

### Buttons

| Button | Does |
|---|---|
| Restart | |
| Restart (Safe Mode) | Reboots into WiFi + OTA only - the way back in after a bad flash |
| Factory Reset | Wipes the WiFi credentials and every stored preference |
| Button Play *(physical, GPIO04)* | Toggles play/pause on the media player |
| Button BT *(physical, GPIO43)* | Mutes the media player - still looking for a better use |

`Button Play`/`Button BT` are wired as `binary_sensor: platform: gpio` with
an `on_press` automation, not as `button:` entities - they represent the
physical buttons on the speaker, not something to click from the Home
Assistant UI.

### Sensors

| Entity | Does |
|---|---|
| Stream - Title / Artist / Album | Metadata of the currently playing Sendspin source |
| Stream - Track Duration | Duration of the current track, in ms |
| Battery Voltage | Measured via the GPIO06 divider, doubled back to actual voltage |
| Battery Low | On below 3.4V. Triggers the red LED and `low_battery_sound` |
| Charging | Tap of the onboard Charge LED. Triggers `charging_sound`/`full_battery_sound` |

### Diagnostic

`Reset Reason`, `Reset Count`, `ESPHome Version`, `Firmware Version`,
`Device Info`, `SSID`, `BSSID`, `MAC Address`, `IP Address`, `DNS Address`,
`WiFi Powersave Mode`, `Device Uptime`, `WiFi Signal (dBm)`,
`WiFi Signal (%)`, `WiFi Disconnects (since boot)`, `Free PSRAM`,
`Internal Temperature`, `Connection Status`.

`Reset Count` and `WiFi Disconnects (since boot)` are both persisted/session
counters, incremented on every restart resp. every WiFi disconnect. A rising
`WiFi Disconnects` count against a stable `Device Uptime` points at a flaky
WiFi link rather than a rebooting device; a rising `Reset Count` against a
low `Device Uptime` points at the opposite.

`Reset Reason`, `Reset Count` and `Firmware Version` are **pushed once at
boot** rather than polled - none of the three can change while the device is
up, and `publish_state` does not deduplicate, so polling them would resend
an identical value every `update_interval` for the lifetime of the device.

---

## How it works

### Audio pipeline

`sendspin:` is the hub that connects to a Sendspin server (Music Assistant)
and distributes group state. `external_media_player` (the `speaker_source`
platform) has two independent pipelines rather than one shared one:

- **`media_pipeline`** - music: `sendspin` (synchronized multi-room audio)
  and `audio_http` (plain HTTP/HTTPS streams).
- **`announcement_pipeline`** - everything in [Sounds](#sounds) below, plus
  Home Assistant's TTS responses: `audio_file` (the local sound effects) and
  a second, separate `audio_http` source for the TTS URLs.

A `media_source` can only feed one pipeline, so the two pipelines each get
their own instance even where the platform is the same (there are two
`audio_http` sources, for example).

Each pipeline feeds a `resampler` speaker (normalizing whatever the source
provides to 48kHz/32bit), which in turn feeds one of two inputs on a
`mixer` speaker (`mixing_speaker`); the mixer combines both into the single
stream that reaches the MAX98357A via `i2s_audio_speaker`. This is what lets
an announcement duck the music instead of interrupting or fighting it for
the I2S bus - see [Ducking](#ducking) below.

`sendspin_group_media_player` only controls the Sendspin group (volume,
transport) and produces no audio of its own; the actual playback and group
control both live on `external_media_player`.

### Ducking

Both `external_media_player: on_announcement`/`on_state` and
`voice_assistant: on_start`/`on_end` call `mixer_speaker.apply_ducking` on
`media_mixing_input` - the former for local sound effects (battery/charging/
wake word), the latter for the voice assistant's TTS response. Two triggers
because they fire at different points: `voice_assistant: on_start` ducks the
instant wake word listening begins, while `on_announcement` only fires once
audio actually starts streaming - applying to both keeps the duck instant
for VA sessions while still covering announcements that happen outside one
(e.g. a low-battery beep while music is playing). Music drops 20dB instantly
and comes back over 1s, once nothing's announcing and the voice assistant
isn't running.

### Sounds

| File | Plays when |
|---|---|
| `startup.mp3` | Once the Sendspin media player pipeline is up (`esphome: on_boot`, priority 220) |
| `low_battery.mp3` | `Battery Low` transitions false → true |
| `charging.mp3` | `Charging` transitions false → true |
| `full_battery.mp3` | `Charging` transitions true → false - see the caveat below |
| `wake_word.mp3` | Fresh wake word detection (see [Wake word priority](#wake-word-priority)), if `Wake Sound` is on |
| `timer_finished.mp3` | Loops (`repeat_one`, 500ms gap) while `timer_ringing` is on - see [Timers](#timers) |
| `shutdown.mp3` | Defined, not wired to anything yet |

### Status LED

The NeoPixel shows two overlapping states, arbitrated by the
`update_status_led` script:

- **Red** while `Battery Low` is on - the script is the single source of
  truth for the idle/red split, called from that binary sensor's
  `on_press`/`on_release`.
- **Blue** while a wake word is being processed - set directly in the
  "fresh detection" branch of `micro_wake_word: on_wake_word_detected` (see
  [Wake word priority](#wake-word-priority)), and cleared by
  `update_status_led` running again from `voice_assistant: on_idle`/
  `on_end`, which is why blue always falls back to whatever
  `update_status_led` currently says rather than a hardcoded off.

The onboard **User LED** (GPIO21, active-low - see [Hardware](#hardware))
only tracks the blue/wake-word state, not red/battery: on together with the
NeoPixel's blue in `micro_wake_word: on_wake_word_detected`'s fresh-detection
branch, off again in `voice_assistant: on_idle`/`on_end` - independently of
`update_status_led`, which only ever touches the NeoPixel.

### Battery monitoring

Two independent, unofficial hardware taps, since the XIAO ESP32S3 exposes
neither a voltage-monitoring pin nor a charge-status pin:

- **Voltage**: a 2x220kOhm divider from battery+ to GND, midpoint on
  GPIO06. `attenuation: 12db` reads the ADC's full 0-3.3V range;
  `filters: multiply: 2.0` undoes the 1:2 divider ratio.
- **Charge state**: a direct tap on the onboard Charge LED's node - the LED
  is wired straight to the charging IC's STAT output, not to any GPIO, so
  this is the only way to read it in software. `inverted: true` assumes an
  active-low STAT signal (common, but unverified for this board - flip it if
  `Charging` reads backwards).

`Charging`'s `on_release` (used for `full_battery_sound`) can't distinguish
"charging finished" from "someone unplugged the cable" - the STAT tap only
reports whether charging is active, not whether a charger is present at all.

### Voice assistant

`microphone:` (the INMP441) feeds `micro_wake_word:`, running three wake
word models locally on-device - `alexa`, `okay_nabu`, `hey_jarvis`
(`task_stack_in_psram` keeps their tensor arena out of internal RAM). The
`Wake Word Sensitivity` select adjusts each model's `probability_cutoff`
(how strict a match has to be) between three preset levels; the underlying
values and False-Accepts-Per-Hour figures in the code comments come from
ESPHome's own Home Assistant Voice PE reference config, and only cover
`okay_nabu`/`hey_jarvis` - `alexa` isn't included in that calibration, so it
stays on its built-in default cutoff regardless of the select's position.

`voice_assistant: micro_wake_word: wake_word_id` does *not* auto-start
anything on detection - despite its name, it only reports the configured
models to Home Assistant's wake-word-selection UI (confirmed against
ESPHome's own source; a config with wake word models but no explicit start
action never opens a pipeline). The actual trigger is
`micro_wake_word: on_wake_word_detected`, which explicitly calls
`voice_assistant.start: wake_word: !lambda return wake_word;` - the
`wake_word` variable (which model fired) is only available on
`micro_wake_word`'s own trigger, not `voice_assistant`'s. See
[Wake word priority](#wake-word-priority) below for the full logic.
`stop_after_detection: false` keeps the detector running continuously
(rather than needing an explicit `micro_wake_word.start` to re-arm it after
every detection), which that logic also depends on.

On detection, `voice_assistant:` opens an Assist pipeline to Home Assistant
and plays the response back through `external_media_player`'s announcement
pipeline - so a TTS reply ducks whatever music was playing rather than
interrupting it (see [Ducking](#ducking) above).

### Wake word priority

A single wake word detection does exactly one of four mutually exclusive
things (`micro_wake_word: on_wake_word_detected`), checked in this order -
it never starts a new conversation on the same detection that stopped
something else:

1. **A timer is ringing** (`timer_ringing` is on) - silence it
   (`switch.turn_off: timer_ringing`) and stop there. Any wake word works,
   not just "stop" - see [Timers](#timers) below.
2. **The voice assistant is already running** - `voice_assistant.stop:`.
   A second wake word mid-conversation cancels it rather than restarting it.
3. **Something is announcing** (TTS reply, a battery/charging beep, the
   timer alarm) - `media_player.stop: announcement: true` interrupts it.
4. **Otherwise** - the normal fresh-detection flow: blue NeoPixel/User LED,
   `wake_word_sound` if `Wake Sound` is on, then
   `voice_assistant.start:`.

`wake_word_sound` and `timer_finished_sound` (see [Timers](#timers)) go
through the `play_sound` script rather than a direct
`media_player.play_media`, with `priority: true`: it stops whatever is
currently announcing first, so an interruption is never silently skipped or
queued behind what it's interrupting. The other sounds (startup/battery/
charging) still use `media_player.play_media` directly, since none of them
need to interrupt anything.

**No hardware echo cancellation.** The INMP441 is a plain digital
microphone with no AEC of its own, and ESPHome doesn't run a software AEC
pipeline here. Wake word detection while the device is quiet works fine;
while it's playing music loudly through its own speaker, the mic picks up
that audio too, and reliability drops. This is a known limitation at this
hardware tier, not a bug to chase - a fix would mean a different microphone
front-end entirely (e.g. a dedicated AEC/beamforming chip such as the XMOS
XVF3800), which only cancels its *own* output path and would need
Sendspin/MAX98357A playback rerouted through it to work.

Both `sendspin` and `micro_wake_word`/`voice_assistant` are marked
**experimental** by ESPHome; breaking changes may land in future releases.

### Timers

Timers set through this device's Assist pipeline ("set a timer for 10
minutes") are entirely tracked server-side by Home Assistant; the device
only finds out when one expires, via `voice_assistant: on_timer_finished`,
which turns on the internal `timer_ringing` switch. `timer_ringing`'s
`on_turn_on`/`on_turn_off` drive the actual alarm - ducking the music,
enabling the on-device `stop` wake word model (normally disabled, so it
can't misfire the rest of the time), and looping `timer_finished_sound`
(the `ring_timer` script) until it's turned back off, either by:

- **Any wake word firing while it's ringing** - checked first, before
  anything else, in [Wake word priority](#wake-word-priority) above. Not
  just "stop": saying any of the wake words silences the alarm, the same
  way tapping anywhere on a physical alarm clock does, rather than
  requiring one specific word under pressure.
- **A 15-minute safety timeout** - `timer_ringing: on_turn_on` ends with a
  `delay: 15min` before turning itself back off, in case nobody responds.

No LED ring animation - unlike the reference config this was adapted from
(Home Assistant Voice PE has an RGB LED ring; this board has one NeoPixel),
a ringing timer doesn't get its own status color here, just whatever
[Status LED](#status-led) would otherwise show.

### Network

Only the Home Assistant API is used - no MQTT. `wifi: power_save_mode: NONE`
keeps the radio fully powered for the low, consistent latency multi-room
audio sync needs; `enable_btm`/`enable_rrm` let the device roam between
access points on 802.11v/k signaling instead of only on signal strength.
`fast_connect: False` means the device scans and picks the strongest AP
for a given SSID rather than the first one that answers - flip it to `True`
if the SSID is hidden, since that's the only way to associate with one.

`api:` has no explicit `reboot_timeout`, so the device restarts on Home
Assistant's default timeout if the API connection is lost - unlike a
sensor-only node, that also interrupts whatever this device is currently
playing or listening for.

### Flash and PSRAM

`flash_size: 8MB` is set explicitly - ESPHome's board profile for the XIAO
otherwise assumes 4 MB, which the Sendspin + Voice Assistant + wake word
stack no longer fits into comfortably. PSRAM (`octal`, 8 MB) backs the
media source buffers (500 KB each for `sendspin_source`/`http_source`,
250 KB for `http_announcement_source`), the `sendspin`/`micro_wake_word`/
`mixing_speaker` task stacks, and the automatic high-performance network
buffers ESPHome enables whenever PSRAM and Sendspin/speaker are both
present.

---

## License

GPL-3.0. See `LICENSE`.
