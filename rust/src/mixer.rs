//! The native audio backend's mixer, and the device it plays to.
//!
//! What `pygame.mixer` did for the native backend, owned here instead:
//! voices summed into one stereo stream and written to the sound card
//! (through cpal, or ALSA loaded at run time on Linux). Owning it is what makes three things simple that were
//! not:
//!
//! - **Pitch is continuous.** A voice steps through its clip by its pitch,
//!   interpolating linearly, so there is no rendered copy per pitch to
//!   quantise and cache.
//! - **Loop regions are native.** A voice wraps from its loop end to its
//!   loop start in the same sample loop that plays it: no queued segments,
//!   no frame-rate dependence, no seam.
//! - **Music decodes off the frame.** A track is decoded on a worker thread
//!   and starts when it is ready, fading in.
//!
//! Policy stays in Python (`NativeAudioSystem`): which bus a sound is on,
//! how loud that makes it, which voice to steal. A voice here has a gain
//! per side and a group -- effects or music -- that can be paused, and
//! nothing else.
//!
//! **Three outputs, one mixer.** The device (the `audio-output` feature, on
//! in every wheel): cpal on Windows and macOS, ALSA through `dlopen` on
//! Linux, so the extension never links `libasound` -- see `device` below. A silent clock, when there is
//! no device or the feature is off: it renders and discards in real time, so
//! a sound still ends when it would have -- what SDL's `dummy` driver did
//! for pygame. And offline, where nothing runs until `render` is called,
//! which is what tests and `tools/audio_capture.py` use.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread;
use std::time::{Duration, Instant};

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;

use crate::audio;

/// Effects and interface sounds.
const GROUP_EFFECTS: u8 = 0;
/// The music track.
const GROUP_MUSIC: u8 = 1;

/// Decoded audio, stereo float at the mixer's rate, shared by every voice
/// playing it.
#[pyclass(frozen)]
pub struct MixerClip {
    samples: Arc<Vec<f32>>,
}

#[pymethods]
impl MixerClip {
    /// Its length in frames.
    #[getter]
    fn frames(&self) -> usize {
        self.samples.len() / 2
    }
}

/// A gain moving towards a target, one step a frame.
#[derive(Clone, Copy)]
struct Fade {
    gain: f32,
    step: f32,
    target: f32,
    stop_at_end: bool,
}

impl Fade {
    fn new(from: f32, to: f32, frames: u64, stop_at_end: bool) -> Self {
        let frames = frames.max(1) as f32;
        Self { gain: from, step: (to - from) / frames, target: to, stop_at_end }
    }

    /// Advance a frame; returns the gain to use for it.
    fn next(&mut self) -> f32 {
        let gain = self.gain;
        if (self.step > 0.0 && self.gain < self.target) || (self.step < 0.0 && self.gain > self.target) {
            self.gain += self.step;
            if (self.step > 0.0 && self.gain > self.target) || (self.step < 0.0 && self.gain < self.target) {
                self.gain = self.target;
            }
        }
        gain
    }

    fn done(&self) -> bool {
        self.gain == self.target
    }
}

struct Voice {
    id: u64,
    group: u8,
    samples: Arc<Vec<f32>>,
    /// Position in source frames.
    cursor: f64,
    step: f64,
    loop_start: f64,
    loop_end: f64,
    /// Wraps still to make: -1 forever, 0 none.
    loops: i64,
    gain_left: f32,
    gain_right: f32,
    fade: Option<Fade>,
    finished: bool,
}

impl Voice {
    fn frames(&self) -> usize {
        self.samples.len() / 2
    }

    /// The sample pair at a fractional source position, interpolated.
    ///
    /// The frame after the last of a looping region is its first, so a
    /// wrap interpolates across the seam rather than into silence.
    fn sample_at(&self, position: f64) -> (f32, f32) {
        let frames = self.frames();
        let whole = position as usize;
        if whole >= frames {
            return (0.0, 0.0);
        }
        let fraction = (position - whole as f64) as f32;
        let mut next = whole + 1;
        if self.loops != 0 && next as f64 >= self.loop_end {
            next = self.loop_start as usize;
        }
        let next = next.min(frames - 1);
        let (a_left, a_right) = (self.samples[whole * 2], self.samples[whole * 2 + 1]);
        let (b_left, b_right) = (self.samples[next * 2], self.samples[next * 2 + 1]);
        (a_left + (b_left - a_left) * fraction, a_right + (b_right - a_right) * fraction)
    }

    /// Add this voice's next `out.len() / 2` frames into `out`.
    fn mix_into(&mut self, out: &mut [f32]) {
        for frame in out.chunks_exact_mut(2) {
            if self.cursor >= self.loop_end {
                if self.loops == 0 {
                    self.finished = true;
                    return;
                }
                self.cursor -= self.loop_end - self.loop_start;
                if self.loops > 0 {
                    self.loops -= 1;
                }
            }
            let (left, right) = self.sample_at(self.cursor);
            let fade = match &mut self.fade {
                Some(fade) => fade.next(),
                None => 1.0,
            };
            frame[0] += left * self.gain_left * fade;
            frame[1] += right * self.gain_right * fade;
            self.cursor += self.step;
        }
        if let Some(fade) = self.fade {
            if fade.done() {
                if fade.stop_at_end {
                    self.finished = true;
                } else {
                    self.fade = None;
                }
            }
        }
    }
}

#[derive(Default)]
struct State {
    voices: Vec<Voice>,
    paused: [bool; 2],
    /// Bumped by every `play_music`/`stop_music`, so a track whose decode
    /// finishes after it was replaced is dropped rather than started.
    music_generation: u64,
    music_pending: bool,
}

impl State {
    fn render(&mut self, out: &mut [f32]) {
        out.fill(0.0);
        let paused = self.paused;
        for voice in &mut self.voices {
            if !paused[voice.group as usize] {
                voice.mix_into(out);
            }
        }
        self.voices.retain(|voice| !voice.finished);
        // A hard clip, as SDL's mixer has: a sum over full scale is
        // distortion either way, and wrapping round would be worse.
        for sample in out.iter_mut() {
            *sample = sample.clamp(-1.0, 1.0);
        }
    }

    fn music(&mut self) -> Option<&mut Voice> {
        self.voices.iter_mut().find(|voice| voice.group == GROUP_MUSIC)
    }
}

type Shared = Arc<Mutex<State>>;

fn lock(shared: &Shared) -> MutexGuard<'_, State> {
    // A panic while mixing poisons the lock; the state is still sound
    // enough to go on playing, which beats a game falling silent for good.
    shared.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// Where the mix goes.
enum Output {
    Offline,
    Silent { running: Arc<AtomicBool> },
    #[cfg(feature = "audio-output")]
    Device { _stream: device::Stream },
}

/// Renders and discards in real time, so voices end when they would have.
fn silent_clock(shared: Shared, rate: u32) -> Arc<AtomicBool> {
    let running = Arc::new(AtomicBool::new(true));
    let flag = running.clone();
    thread::spawn(move || {
        let mut buffer = vec![0.0f32; 4096];
        let mut last = Instant::now();
        while flag.load(Ordering::Relaxed) {
            thread::sleep(Duration::from_millis(10));
            let now = Instant::now();
            let frames = ((now - last).as_secs_f64() * f64::from(rate)) as usize;
            if frames == 0 {
                continue;
            }
            last = now;
            let mut left = frames;
            while left > 0 {
                let chunk = left.min(buffer.len() / 2);
                lock(&shared).render(&mut buffer[..chunk * 2]);
                left -= chunk;
            }
        }
    });
    running
}

#[cfg(all(feature = "audio-output", not(target_os = "linux")))]
mod device {
    use super::{Shared, lock};
    use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
    use cpal::{FromSample, SampleFormat, SizedSample, StreamConfig};

    pub type Stream = cpal::Stream;

    /// Open the default output device at its own rate.
    ///
    /// Returns the stream (playing), the rate it runs at, and its name.
    pub fn open(shared: Shared) -> Result<(cpal::Stream, u32, String), String> {
        let host = cpal::default_host();
        let device = host
            .default_output_device()
            .ok_or_else(|| "no output device".to_owned())?;
        let name = device
            .description()
            .map(|description| description.to_string())
            .unwrap_or_else(|_| "output device".to_owned());
        let supported = device.default_output_config().map_err(|error| error.to_string())?;
        let format = supported.sample_format();
        let config: StreamConfig = supported.into();
        let rate = config.sample_rate;
        let stream = match format {
            SampleFormat::F32 => build::<f32>(&device, config, shared),
            SampleFormat::I16 => build::<i16>(&device, config, shared),
            SampleFormat::U16 => build::<u16>(&device, config, shared),
            SampleFormat::I32 => build::<i32>(&device, config, shared),
            other => Err(format!("the device wants {other:?} samples")),
        }?;
        stream.play().map_err(|error| error.to_string())?;
        Ok((stream, rate, name))
    }

    fn build<T>(device: &cpal::Device, config: StreamConfig, shared: Shared) -> Result<cpal::Stream, String>
    where
        T: SizedSample + FromSample<f32>,
    {
        let channels = config.channels as usize;
        let mut mix: Vec<f32> = Vec::new();
        device
            .build_output_stream(
                config,
                move |data: &mut [T], _| {
                    let frames = data.len() / channels.max(1);
                    mix.resize(frames * 2, 0.0);
                    lock(&shared).render(&mut mix);
                    for (frame, pair) in data.chunks_mut(channels).zip(mix.chunks_exact(2)) {
                        match frame.len() {
                            1 => frame[0] = T::from_sample((pair[0] + pair[1]) * 0.5),
                            _ => {
                                frame[0] = T::from_sample(pair[0]);
                                frame[1] = T::from_sample(pair[1]);
                                for rest in &mut frame[2..] {
                                    *rest = T::from_sample(0.0);
                                }
                            }
                        }
                    }
                },
                |error| eprintln!("pyguara audio: {error}"),
                None,
            )
            .map_err(|error| error.to_string())
    }
}

/// Linux's device: ALSA, loaded with `dlopen` when a mixer opens one.
///
/// **Not cpal, and not linked**, because a linked `libasound.so.2` is a
/// load-time dependency of the whole extension: on a machine without it --
/// a slim container, a server, a minimal CI image -- `import
/// pyguara.pyguara_core_rs` failed, taking every native store with it. Loaded
/// here, a missing ALSA is one more reason the mixer is silent.
///
/// It plays through ALSA's `default` device, which on a desktop is
/// PipeWire's or PulseAudio's plugin, as cpal's did. Only the simple API is
/// used: `snd_pcm_set_params` asks for 16-bit stereo at 48 kHz and lets the
/// plug layer convert, and a thread mixes a period at a time into the
/// blocking `snd_pcm_writei`. `PYGUARA_ALSA_DEVICE` names another device;
/// ALSA's `null` takes samples with no card, which is how this is tested.
#[cfg(all(feature = "audio-output", target_os = "linux"))]
mod device {
    use std::ffi::{CStr, CString, c_char, c_int, c_long, c_uint, c_ulong, c_void};
    use std::sync::Arc;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::thread::{self, JoinHandle};

    use libloading::Library;

    use super::{Shared, lock};

    const RATE: u32 = 48_000;
    /// Frames mixed per write: about 5 ms.
    const PERIOD: usize = 256;
    /// What ALSA may hold, in microseconds.
    const LATENCY_US: c_uint = 40_000;
    const SND_PCM_STREAM_PLAYBACK: c_int = 0;
    const SND_PCM_FORMAT_S16_LE: c_int = 2;
    const SND_PCM_ACCESS_RW_INTERLEAVED: c_int = 3;

    type Open = unsafe extern "C" fn(*mut *mut c_void, *const c_char, c_int, c_int) -> c_int;
    type SetParams =
        unsafe extern "C" fn(*mut c_void, c_int, c_int, c_uint, c_uint, c_int, c_uint) -> c_int;
    type Writei = unsafe extern "C" fn(*mut c_void, *const c_void, c_ulong) -> c_long;
    type Recover = unsafe extern "C" fn(*mut c_void, c_int, c_int) -> c_int;
    type Close = unsafe extern "C" fn(*mut c_void) -> c_int;
    type StrError = unsafe extern "C" fn(c_int) -> *const c_char;
    type Quiet = unsafe extern "C" fn(*const c_char, c_int, *const c_char, c_int, *const c_char);
    type SetErrorHandler = unsafe extern "C" fn(Option<Quiet>) -> c_int;

    /// Takes ALSA's error reports while a device opens, and drops them.
    ///
    /// ALSA prints its config's complaints straight to stderr -- eight lines
    /// of `ALSA lib confmisc.c` on a machine with no card -- where the mixer
    /// already says in one why it is silent. The handler is variadic in C;
    /// on Linux's x86_64 and aarch64 ABIs a callee that reads only the fixed
    /// arguments is called correctly.
    unsafe extern "C" fn quiet(_: *const c_char, _: c_int, _: *const c_char, _: c_int, _: *const c_char) {}

    struct Alsa {
        // Held so the functions below stay loaded.
        _library: Library,
        open: Open,
        set_params: SetParams,
        writei: Writei,
        recover: Recover,
        drop_pcm: Close,
        close: Close,
        strerror: StrError,
        set_error_handler: SetErrorHandler,
    }

    impl Alsa {
        fn load() -> Result<Self, String> {
            // SAFETY: libasound's initialisers have no preconditions, and each
            // symbol is read with the signature alsa/pcm.h gives it.
            unsafe {
                let library = Library::new("libasound.so.2")
                    .map_err(|error| format!("ALSA is not installed ({error})"))?;
                macro_rules! symbol {
                    ($name:literal) => {
                        *library
                            .get($name)
                            .map_err(|error| format!("ALSA lacks a function: {error}"))?
                    };
                }
                Ok(Self {
                    open: symbol!(b"snd_pcm_open\0"),
                    set_params: symbol!(b"snd_pcm_set_params\0"),
                    writei: symbol!(b"snd_pcm_writei\0"),
                    recover: symbol!(b"snd_pcm_recover\0"),
                    drop_pcm: symbol!(b"snd_pcm_drop\0"),
                    close: symbol!(b"snd_pcm_close\0"),
                    strerror: symbol!(b"snd_strerror\0"),
                    set_error_handler: symbol!(b"snd_lib_error_set_handler\0"),
                    _library: library,
                })
            }
        }

        fn error(&self, code: c_int) -> String {
            // SAFETY: snd_strerror returns a static string for any code.
            unsafe { CStr::from_ptr((self.strerror)(code)) }.to_string_lossy().into_owned()
        }
    }

    /// An open PCM handle, moved once to the thread that writes it.
    struct Pcm(*mut c_void);
    // SAFETY: the handle is only ever used by one thread at a time: opened
    // here, then owned by the writer until it closes it.
    unsafe impl Send for Pcm {}

    /// A playing device; dropping it stops the writer and closes ALSA.
    pub struct Stream {
        running: Arc<AtomicBool>,
        writer: Option<JoinHandle<()>>,
    }

    impl Drop for Stream {
        fn drop(&mut self) {
            self.running.store(false, Ordering::Relaxed);
            if let Some(writer) = self.writer.take() {
                let _ = writer.join();
            }
        }
    }

    pub fn open(shared: Shared) -> Result<(Stream, u32, String), String> {
        let alsa = Alsa::load()?;
        let name = std::env::var("PYGUARA_ALSA_DEVICE").unwrap_or_else(|_| "default".to_owned());
        let c_name = CString::new(name.clone()).map_err(|_| "bad device name".to_owned())?;
        let mut pcm: *mut c_void = std::ptr::null_mut();
        // SAFETY: the handler matches what ALSA calls (see `quiet`); None
        // restores ALSA's own once the device is open or refused.
        unsafe { (alsa.set_error_handler)(Some(quiet)) };
        let opened = open_pcm(&alsa, &mut pcm, &c_name, &name);
        // SAFETY: None is ALSA's documented way back to its default handler.
        unsafe { (alsa.set_error_handler)(None) };
        opened?;
        let running = Arc::new(AtomicBool::new(true));
        let flag = running.clone();
        let handle = Pcm(pcm);
        let writer = thread::Builder::new()
            .name("pyguara-alsa".into())
            .spawn(move || write(alsa, handle, shared, flag))
            .map_err(|error| error.to_string())?;
        Ok((Stream { running, writer: Some(writer) }, RATE, format!("ALSA {name}")))
    }

    /// Open `name` for playback and set its format; closes it on failure.
    fn open_pcm(alsa: &Alsa, pcm: &mut *mut c_void, c_name: &CStr, name: &str) -> Result<(), String> {
        // SAFETY: `pcm` is written by a successful open, and closed here on
        // failure or later by the writer.
        unsafe {
            let code = (alsa.open)(pcm, c_name.as_ptr(), SND_PCM_STREAM_PLAYBACK, 0);
            if code < 0 {
                return Err(format!("ALSA could not open {name:?}: {}", alsa.error(code)));
            }
            let code = (alsa.set_params)(
                *pcm,
                SND_PCM_FORMAT_S16_LE,
                SND_PCM_ACCESS_RW_INTERLEAVED,
                2,
                RATE,
                1,
                LATENCY_US,
            );
            if code < 0 {
                (alsa.close)(*pcm);
                return Err(format!("ALSA refused 16-bit stereo at {RATE} Hz: {}", alsa.error(code)));
            }
        }
        Ok(())
    }

    fn write(alsa: Alsa, pcm: Pcm, shared: Shared, running: Arc<AtomicBool>) {
        let pcm = pcm.0;
        let mut mix = vec![0.0f32; PERIOD * 2];
        let mut samples = vec![0i16; PERIOD * 2];
        while running.load(Ordering::Relaxed) {
            lock(&shared).render(&mut mix);
            for (out, &value) in samples.iter_mut().zip(&mix) {
                *out = (value.clamp(-1.0, 1.0) * 32767.0) as i16;
            }
            let mut done = 0usize;
            while done < PERIOD && running.load(Ordering::Relaxed) {
                // SAFETY: the slice holds PERIOD - done whole frames from `done`.
                let wrote = unsafe {
                    (alsa.writei)(
                        pcm,
                        samples[done * 2..].as_ptr().cast(),
                        (PERIOD - done) as c_ulong,
                    )
                };
                if wrote >= 0 {
                    done += wrote as usize;
                    continue;
                }
                // An underrun or a suspend: recover and carry on; anything
                // else ends playback rather than spinning on it.
                // SAFETY: `pcm` is open.
                if unsafe { (alsa.recover)(pcm, wrote as c_int, 1) } < 0 {
                    eprintln!("pyguara audio: ALSA stopped: {}", alsa.error(wrote as c_int));
                    running.store(false, Ordering::Relaxed);
                }
            }
        }
        // SAFETY: the writer owns the handle; nothing uses it after this.
        unsafe {
            (alsa.drop_pcm)(pcm);
            (alsa.close)(pcm);
        }
    }
}

/// Convert interleaved i16 PCM at any rate and channel count to the mixer's
/// stereo float.
fn to_stereo_float(samples: &[i16], channels: usize, from_rate: u32, to_rate: u32) -> Vec<f32> {
    let stereo = if from_rate == to_rate && channels == 2 {
        samples.to_vec()
    } else {
        audio::resample(samples, channels, 2, f64::from(from_rate) / f64::from(to_rate))
    };
    stereo.iter().map(|&sample| f32::from(sample) / 32768.0).collect()
}

/// The mixer.
///
/// Made and used on one thread (`unsendable`): a cpal stream is not `Send`
/// on every platform. The mix itself runs on the audio thread, behind a
/// lock this holds only to change a voice.
#[pyclass(unsendable)]
pub struct NativeMixer {
    shared: Shared,
    rate: u32,
    output: Output,
    description: String,
    next_id: AtomicU64,
}

impl NativeMixer {
    fn state(&self) -> MutexGuard<'_, State> {
        lock(&self.shared)
    }
}

#[pymethods]
impl NativeMixer {
    /// Open a mixer.
    ///
    /// Args:
    ///     rate: The rate to mix at offline. A device runs at its own rate,
    ///         which `rate` then reports.
    ///     output: `"device"` for the sound card, falling back to a silent
    ///         clock when there is none; `"silent"` for the clock; or
    ///         `"offline"`, where nothing plays until `render` is called.
    #[new]
    #[pyo3(signature = (rate=44100, output="device"))]
    fn new(rate: u32, output: &str) -> PyResult<Self> {
        if rate == 0 {
            return Err(PyValueError::new_err("the rate must be positive"));
        }
        let shared: Shared = Arc::new(Mutex::new(State::default()));
        let (output, rate, description) = match output {
            "offline" => (Output::Offline, rate, "offline".to_owned()),
            "silent" => (
                Output::Silent { running: silent_clock(shared.clone(), rate) },
                rate,
                "silent: asked for".to_owned(),
            ),
            "device" => open_device(&shared, rate),
            other => {
                return Err(PyValueError::new_err(format!(
                    "output must be 'device', 'silent' or 'offline', got {other:?}"
                )));
            }
        };
        Ok(Self { shared, rate, output, description, next_id: AtomicU64::new(1) })
    }

    /// The rate the mix runs at, in frames per second.
    #[getter]
    fn rate(&self) -> u32 {
        self.rate
    }

    /// Where the mix goes: `device: <name>`, `silent: <why>` or `offline`.
    #[getter]
    fn output(&self) -> &str {
        &self.description
    }

    /// Make a clip from PCM, converted to the mixer's rate and stereo.
    ///
    /// Args:
    ///     pcm: Interleaved little-endian signed 16-bit samples.
    ///     rate: The rate `pcm` is at.
    ///     channels: Its channel count.
    fn clip(&self, py: Python<'_>, pcm: &[u8], rate: u32, channels: usize) -> PyResult<MixerClip> {
        if rate == 0 || channels == 0 {
            return Err(PyValueError::new_err("rate and channels must be positive"));
        }
        if pcm.len() % (2 * channels) != 0 {
            return Err(PyValueError::new_err(format!(
                "{} bytes is not a whole number of {channels}-channel frames",
                pcm.len()
            )));
        }
        let to_rate = self.rate;
        let samples = py.detach(|| {
            let samples: Vec<i16> = pcm
                .chunks_exact(2)
                .map(|pair| i16::from_le_bytes([pair[0], pair[1]]))
                .collect();
            to_stereo_float(&samples, channels, rate, to_rate)
        });
        Ok(MixerClip { samples: Arc::new(samples) })
    }

    /// Start a voice.
    ///
    /// Args:
    ///     clip: What to play.
    ///     left: Gain on the left.
    ///     right: Gain on the right.
    ///     pitch: Playback rate; 2.0 is an octave up and half as long.
    ///     loops: Times to wrap: 0 plays once, -1 forever.
    ///     loop_start: Where a wrap lands, in the clip's frames.
    ///     loop_end: Where a wrap happens; None is the clip's end.
    ///
    /// Returns:
    ///     The voice's id.
    #[pyo3(signature = (clip, left, right, pitch=1.0, loops=0, loop_start=0.0, loop_end=None))]
    #[allow(clippy::too_many_arguments)]
    fn play(
        &self,
        clip: &MixerClip,
        left: f32,
        right: f32,
        pitch: f64,
        loops: i64,
        loop_start: f64,
        loop_end: Option<f64>,
    ) -> PyResult<u64> {
        if !(pitch.is_finite() && pitch > 0.0) {
            return Err(PyValueError::new_err(format!("pitch must be positive, got {pitch}")));
        }
        let frames = (clip.samples.len() / 2) as f64;
        let loop_end = loop_end.unwrap_or(frames).min(frames);
        if !(0.0 <= loop_start && loop_start < loop_end) {
            return Err(PyValueError::new_err(format!(
                "the loop region {loop_start}..{loop_end} is empty"
            )));
        }
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        self.state().voices.push(Voice {
            id,
            group: GROUP_EFFECTS,
            samples: clip.samples.clone(),
            cursor: 0.0,
            step: pitch,
            loop_start,
            loop_end,
            loops,
            gain_left: left,
            gain_right: right,
            fade: None,
            finished: false,
        });
        Ok(id)
    }

    /// Change a playing voice's gains. A voice that has ended is ignored.
    fn set_gains(&self, voice: u64, left: f32, right: f32) {
        if let Some(found) = self.state().voices.iter_mut().find(|v| v.id == voice) {
            found.gain_left = left;
            found.gain_right = right;
        }
    }

    /// Stop a voice now. A voice that has ended is ignored.
    fn stop(&self, voice: u64) {
        self.state().voices.retain(|v| v.id != voice);
    }

    /// Whether a voice is still playing (or paused, unfinished).
    fn is_playing(&self, voice: u64) -> bool {
        self.state().voices.iter().any(|v| v.id == voice)
    }

    /// How many effect voices are playing.
    #[getter]
    fn voice_count(&self) -> usize {
        self.state().voices.iter().filter(|v| v.group == GROUP_EFFECTS).count()
    }

    /// Pause effects (`music=False`) or the music track.
    #[pyo3(signature = (music=false))]
    fn pause(&self, music: bool) {
        self.state().paused[usize::from(music)] = true;
    }

    /// Resume what `pause` paused.
    #[pyo3(signature = (music=false))]
    fn resume(&self, music: bool) {
        self.state().paused[usize::from(music)] = false;
    }

    /// Stop every effect voice.
    fn stop_effects(&self) {
        self.state().voices.retain(|v| v.group != GROUP_EFFECTS);
    }

    /// Decode a music file on a worker thread, then play it, fading in.
    ///
    /// Replaces the current track at once. A file that will not decode is
    /// reported to stderr and plays nothing; the game carries on.
    ///
    /// Args:
    ///     path: The file.
    ///     looping: Play it forever rather than once.
    ///     fade_ms: The fade in.
    ///     gain: Its loudness.
    #[pyo3(signature = (path, looping=true, fade_ms=0, gain=1.0))]
    fn play_music(&self, path: String, looping: bool, fade_ms: u64, gain: f32) {
        let generation = {
            let mut state = self.state();
            state.voices.retain(|v| v.group != GROUP_MUSIC);
            state.music_generation += 1;
            state.music_pending = true;
            state.music_generation
        };
        let shared = self.shared.clone();
        let rate = self.rate;
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        thread::spawn(move || {
            let decoded = audio::decode_to_samples(&path)
                .map(|(samples, from_rate, channels)| to_stereo_float(&samples, channels, from_rate, rate));
            let mut state = lock(&shared);
            if state.music_generation != generation {
                return;
            }
            state.music_pending = false;
            let samples = match decoded {
                Ok(samples) if !samples.is_empty() => samples,
                Ok(_) => return,
                Err(error) => {
                    eprintln!("pyguara audio: music {error}");
                    return;
                }
            };
            let frames = (samples.len() / 2) as f64;
            let fade_frames = fade_ms * u64::from(rate) / 1000;
            state.voices.push(Voice {
                id,
                group: GROUP_MUSIC,
                samples: Arc::new(samples),
                cursor: 0.0,
                step: 1.0,
                loop_start: 0.0,
                loop_end: frames,
                loops: if looping { -1 } else { 0 },
                gain_left: gain,
                gain_right: gain,
                fade: (fade_frames > 0).then(|| Fade::new(0.0, 1.0, fade_frames, false)),
                finished: false,
            });
        });
    }

    /// Fade the music out over `fade_ms`, then stop it.
    #[pyo3(signature = (fade_ms=0))]
    fn stop_music(&self, fade_ms: u64) {
        let rate = self.rate;
        let mut state = self.state();
        state.music_generation += 1;
        state.music_pending = false;
        if fade_ms == 0 {
            state.voices.retain(|v| v.group != GROUP_MUSIC);
            return;
        }
        if let Some(music) = state.music() {
            let from = music.fade.map_or(1.0, |fade| fade.gain);
            music.fade = Some(Fade::new(from, 0.0, fade_ms * u64::from(rate) / 1000, true));
        }
    }

    /// Set the music track's loudness.
    fn set_music_gain(&self, gain: f32) {
        if let Some(music) = self.state().music() {
            music.gain_left = gain;
            music.gain_right = gain;
        }
    }

    /// Whether a track is playing or still being decoded to play.
    #[getter]
    fn music_playing(&self) -> bool {
        let mut state = self.state();
        state.music_pending || state.music().is_some()
    }

    /// Mix the next `frames` frames and return them.
    ///
    /// Only for an `offline` mixer: on any other the audio thread is
    /// already consuming the mix.
    ///
    /// Returns:
    ///     Interleaved stereo little-endian 32-bit floats.
    fn render<'py>(&self, py: Python<'py>, frames: usize) -> PyResult<Bound<'py, PyBytes>> {
        if !matches!(self.output, Output::Offline) {
            return Err(PyRuntimeError::new_err("only an offline mixer can be rendered"));
        }
        let mut out = vec![0.0f32; frames * 2];
        self.state().render(&mut out);
        let bytes: Vec<u8> = out.iter().flat_map(|sample| sample.to_le_bytes()).collect();
        Ok(PyBytes::new(py, &bytes))
    }

    /// Stop everything and release the output. Idempotent.
    fn close(&mut self) {
        {
            let mut state = self.state();
            state.voices.clear();
            state.music_generation += 1;
            state.music_pending = false;
        }
        if let Output::Silent { running } = &self.output {
            running.store(false, Ordering::Relaxed);
        }
        self.output = Output::Offline;
        self.description = "closed".to_owned();
    }
}

/// Open the device, or fall back to the silent clock and say why.
fn open_device(shared: &Shared, rate: u32) -> (Output, u32, String) {
    #[cfg(feature = "audio-output")]
    {
        match device::open(shared.clone()) {
            Ok((stream, device_rate, name)) => {
                return (Output::Device { _stream: stream }, device_rate, format!("device: {name}"));
            }
            Err(reason) => {
                let running = silent_clock(shared.clone(), rate);
                return (Output::Silent { running }, rate, format!("silent: {reason}"));
            }
        }
    }
    #[cfg(not(feature = "audio-output"))]
    {
        let running = silent_clock(shared.clone(), rate);
        (
            Output::Silent { running },
            rate,
            "silent: this build has no audio output (the audio-output feature is off)".to_owned(),
        )
    }
}
