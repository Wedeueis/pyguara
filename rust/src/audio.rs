//! Decoding and resampling for the native audio backend.
//!
//! The first native code with **no Python counterpart**: `pygame.mixer` cannot
//! pitch-shift at all, so there is no second store to run a parity suite
//! against, and `tests/test_native_audio.py` asserts against constructed PCM
//! and measured properties instead. That is also why everything here is a
//! pure function from samples to samples with no device anywhere near it --
//! the offline sink ADR 0004 asks of a backend with no reference is simply
//! that the mix's inputs are bytes a test can read.
//!
//! The mixer that plays what this decodes, and owns the device, is
//! `mixer.rs`.
//!
//! Resampling is **linear interpolation**, so a pitch above 1.0 aliases a
//! little rather than being band-limited. Pitch here is SFX variation of a
//! few percent, where that is inaudible; it is the first thing to replace if
//! the range in use widens.

use std::fs::File;
use std::path::Path;

use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use symphonia::core::audio::SampleBuffer;
use symphonia::core::codecs::{CODEC_TYPE_NULL, DecoderOptions};
use symphonia::core::errors::Error as SymphoniaError;
use symphonia::core::formats::FormatOptions;
use symphonia::core::io::MediaSourceStream;
use symphonia::core::meta::MetadataOptions;
use symphonia::core::probe::Hint;

const BYTES_PER_SAMPLE: usize = 2;

/// Decode a whole file to interleaved signed 16-bit samples.
///
/// Returns the samples with the file's own rate and channel count.
pub(crate) fn decode_to_samples(path: &str) -> Result<(Vec<i16>, u32, usize), String> {
    let file = File::open(path).map_err(|error| format!("{path}: {error}"))?;
    let stream = MediaSourceStream::new(Box::new(file), Default::default());

    let mut hint = Hint::new();
    if let Some(extension) = Path::new(path).extension().and_then(|e| e.to_str()) {
        hint.with_extension(extension);
    }
    let format_options = FormatOptions {
        enable_gapless: true,
        ..Default::default()
    };
    let probed = symphonia::default::get_probe()
        .format(&hint, stream, &format_options, &MetadataOptions::default())
        .map_err(|error| format!("{path}: {error}"))?;
    let mut format = probed.format;

    let track = format
        .tracks()
        .iter()
        .find(|track| track.codec_params.codec != CODEC_TYPE_NULL)
        .ok_or_else(|| format!("{path}: no decodable audio track"))?;
    let track_id = track.id;
    let mut decoder = symphonia::default::get_codecs()
        .make(&track.codec_params, &DecoderOptions::default())
        .map_err(|error| format!("{path}: {error}"))?;

    let mut samples: Vec<i16> = Vec::new();
    let mut rate = track.codec_params.sample_rate.unwrap_or(0);
    let mut channels = 0usize;
    let mut buffer: Option<SampleBuffer<i16>> = None;

    loop {
        let packet = match format.next_packet() {
            Ok(packet) => packet,
            // How every format reader reports the end of the stream.
            Err(SymphoniaError::IoError(error))
                if error.kind() == std::io::ErrorKind::UnexpectedEof =>
            {
                break;
            }
            Err(error) => return Err(format!("{path}: {error}")),
        };
        if packet.track_id() != track_id {
            continue;
        }
        let decoded = match decoder.decode(&packet) {
            Ok(decoded) => decoded,
            // One corrupt packet is a click, not an unusable file.
            Err(SymphoniaError::DecodeError(_)) => continue,
            Err(error) => return Err(format!("{path}: {error}")),
        };
        let spec = *decoded.spec();
        rate = spec.rate;
        channels = spec.channels.count();
        let capacity = decoded.capacity() as u64;
        let target = buffer.get_or_insert_with(|| SampleBuffer::new(capacity, spec));
        if (target.capacity() as u64) < capacity * channels as u64 {
            *target = SampleBuffer::new(capacity, spec);
        }
        target.copy_interleaved_ref(decoded);
        samples.extend_from_slice(target.samples());
    }

    if channels == 0 {
        return Err(format!("{path}: no audio decoded"));
    }
    Ok((samples, rate, channels))
}

/// Map one interleaved frame to `dst` channels.
///
/// Mono spreads to every output; several channels to mono averages them;
/// anything else keeps the first `dst`, repeating the last if there are fewer.
fn map_frame(frame: &[i16], dst: usize, out: &mut [i32]) {
    if dst == 1 && frame.len() > 1 {
        let sum: i32 = frame.iter().map(|&sample| i32::from(sample)).sum();
        out[0] = sum / frame.len() as i32;
        return;
    }
    for (index, slot) in out.iter_mut().enumerate().take(dst) {
        *slot = i32::from(frame[index.min(frame.len() - 1)]);
    }
}

/// Resample interleaved samples by linear interpolation.
///
/// Positions are computed from the output index rather than accumulated, so
/// a long clip does not drift by the rounding of `step`. The output ends at
/// the last position inside the input, so `step == 1.0` is the identity.
pub(crate) fn resample(
    input: &[i16],
    src_channels: usize,
    dst_channels: usize,
    step: f64,
) -> Vec<i16> {
    let frames = input.len() / src_channels;
    if frames == 0 {
        return Vec::new();
    }
    let out_frames = ((frames - 1) as f64 / step).floor() as usize + 1;
    let mut output = Vec::with_capacity(out_frames * dst_channels);
    let mut left = vec![0i32; dst_channels];
    let mut right = vec![0i32; dst_channels];

    for index in 0..out_frames {
        let position = index as f64 * step;
        let whole = position as usize;
        let fraction = position - whole as f64;
        let next = (whole + 1).min(frames - 1);
        map_frame(
            &input[whole * src_channels..(whole + 1) * src_channels],
            dst_channels,
            &mut left,
        );
        map_frame(
            &input[next * src_channels..(next + 1) * src_channels],
            dst_channels,
            &mut right,
        );
        for channel in 0..dst_channels {
            let a = f64::from(left[channel]);
            let b = f64::from(right[channel]);
            let value = (a + (b - a) * fraction).round();
            output.push(value.clamp(f64::from(i16::MIN), f64::from(i16::MAX)) as i16);
        }
    }
    output
}

fn samples_to_bytes(samples: &[i16]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(samples.len() * BYTES_PER_SAMPLE);
    for sample in samples {
        bytes.extend_from_slice(&sample.to_le_bytes());
    }
    bytes
}

fn bytes_to_samples(bytes: &[u8]) -> Vec<i16> {
    bytes
        .chunks_exact(BYTES_PER_SAMPLE)
        .map(|pair| i16::from_le_bytes([pair[0], pair[1]]))
        .collect()
}

/// Decode an audio file to PCM.
///
/// Args:
///     path: The file. Its extension is a hint; the content decides.
///
/// Returns:
///     `(pcm, rate, channels)`: interleaved little-endian signed 16-bit
///     samples, with the file's own rate and channel count.
///
/// Raises:
///     OSError: If the file cannot be read or holds no decodable audio.
#[pyfunction]
pub fn decode_audio<'py>(
    py: Python<'py>,
    path: &str,
) -> PyResult<(Bound<'py, PyBytes>, u32, usize)> {
    let (samples, rate, channels) = py
        .detach(|| decode_to_samples(path))
        .map_err(PyOSError::new_err)?;
    let bytes = py.detach(|| samples_to_bytes(&samples));
    Ok((PyBytes::new(py, &bytes), rate, channels))
}

/// Convert PCM to another rate, channel count and playback rate.
///
/// Pitch is resampling, so **a pitch above 1.0 also shortens the sound**.
///
/// Args:
///     pcm: Interleaved little-endian signed 16-bit samples.
///     src_rate: The rate `pcm` is at.
///     src_channels: The channel count of `pcm`.
///     dst_rate: The rate to produce.
///     dst_channels: The channel count to produce.
///     pitch: Playback rate multiplier; 1.0 keeps the sound's own pitch.
///
/// Returns:
///     The converted PCM, in the same sample format.
///
/// Raises:
///     ValueError: If a rate, a channel count or `pitch` is not positive, or
///         `pcm` is not a whole number of frames.
#[pyfunction]
#[pyo3(signature = (pcm, src_rate, src_channels, dst_rate, dst_channels, pitch=1.0))]
pub fn resample_pcm<'py>(
    py: Python<'py>,
    pcm: &[u8],
    src_rate: u32,
    src_channels: usize,
    dst_rate: u32,
    dst_channels: usize,
    pitch: f64,
) -> PyResult<Bound<'py, PyBytes>> {
    if src_rate == 0 || dst_rate == 0 || src_channels == 0 || dst_channels == 0 {
        return Err(PyValueError::new_err(
            "rates and channel counts must be positive",
        ));
    }
    if !(pitch.is_finite() && pitch > 0.0) {
        return Err(PyValueError::new_err(format!(
            "pitch must be positive, got {pitch}"
        )));
    }
    if pcm.len() % (BYTES_PER_SAMPLE * src_channels) != 0 {
        return Err(PyValueError::new_err(format!(
            "{} bytes is not a whole number of {src_channels}-channel frames",
            pcm.len()
        )));
    }
    let step = f64::from(src_rate) / f64::from(dst_rate) * pitch;
    let bytes = py.detach(|| {
        let samples = bytes_to_samples(pcm);
        samples_to_bytes(&resample(&samples, src_channels, dst_channels, step))
    });
    Ok(PyBytes::new(py, &bytes))
}
