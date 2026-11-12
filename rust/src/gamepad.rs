//! Gamepads for the wgpu backend, on gilrs: what SDL's joysticks did.
//!
//! **Buttons and axes are numbered as `GamepadButton` and `GamepadAxis`**
//! (`pyguara/input/types.py`), from gilrs's standard layout -- which applies
//! SDL's own controller database -- rather than a device's raw indices. So
//! `GamepadButton.A` is the south face button on an Xbox pad, a DualSense
//! and a Switch Pro alike, where under pygame the raw joystick indices only
//! matched that enum on pads that happened to report them in that order.
//!
//! Sticks are -1 to 1 with **y down**, as the engine has them; gilrs has y
//! up. Triggers are 0 to 1.
//!
//! Without the `gamepads` feature (a Linux build with no udev headers) this
//! compiles to an object that never sees a pad.

use pyo3::prelude::*;

/// Engine button indices, in `GamepadButton` order.
pub const BUTTON_COUNT: usize = 17;
/// Engine axis indices, in `GamepadAxis` order.
pub const AXIS_COUNT: usize = 6;

#[cfg(feature = "gamepads")]
mod pads {
    use std::collections::HashMap;
    use std::time::{Duration, Instant};

    use gilrs::ff::{BaseEffect, BaseEffectType, Effect, EffectBuilder, Replay, Ticks};
    use gilrs::{Axis, Button, GamepadId, Gilrs};

    /// `GamepadButton` order: A, B, X, Y, LB, RB, LT, RT, Back, Start,
    /// Guide, L3, R3, Up, Down, Left, Right.
    const BUTTONS: [Button; super::BUTTON_COUNT] = [
        Button::South,
        Button::East,
        Button::West,
        Button::North,
        Button::LeftTrigger,
        Button::RightTrigger,
        Button::LeftTrigger2,
        Button::RightTrigger2,
        Button::Select,
        Button::Start,
        Button::Mode,
        Button::LeftThumb,
        Button::RightThumb,
        Button::DPadUp,
        Button::DPadDown,
        Button::DPadLeft,
        Button::DPadRight,
    ];

    pub struct Pads {
        gilrs: Option<Gilrs>,
        pub error: Option<String>,
        rumbling: HashMap<usize, (Effect, Instant)>,
    }

    impl Pads {
        pub fn open() -> Self {
            match Gilrs::new() {
                Ok(gilrs) => Self { gilrs: Some(gilrs), error: None, rumbling: HashMap::new() },
                // A partial start still sees the pads it could open.
                Err(gilrs::Error::NotImplemented(gilrs)) => Self {
                    gilrs: Some(gilrs),
                    error: Some("gamepads are not supported on this platform".into()),
                    rumbling: HashMap::new(),
                },
                Err(error) => Self { gilrs: None, error: Some(error.to_string()), rumbling: HashMap::new() },
            }
        }

        pub fn poll(&mut self) {
            if let Some(gilrs) = &mut self.gilrs {
                while gilrs.next_event().is_some() {}
            }
            let now = Instant::now();
            self.rumbling.retain(|_, (_, until)| *until > now);
        }

        pub fn ids(&self) -> Vec<usize> {
            self.gilrs
                .as_ref()
                .map(|gilrs| gilrs.gamepads().map(|(id, _)| usize::from(id)).collect())
                .unwrap_or_default()
        }

        fn find(&self, id: usize) -> Option<gilrs::Gamepad<'_>> {
            let gilrs = self.gilrs.as_ref()?;
            gilrs
                .gamepads()
                .find(|(found, _)| usize::from(*found) == id)
                .map(|(_, pad)| pad)
        }

        fn gilrs_id(&self, id: usize) -> Option<GamepadId> {
            self.find(id).map(|pad| pad.id())
        }

        pub fn name(&self, id: usize) -> Option<String> {
            self.find(id).map(|pad| pad.name().to_owned())
        }

        pub fn button(&self, id: usize, index: usize) -> bool {
            let (Some(pad), Some(button)) = (self.find(id), BUTTONS.get(index)) else {
                return false;
            };
            pad.is_pressed(*button)
        }

        pub fn axis(&self, id: usize, index: usize) -> f32 {
            let Some(pad) = self.find(id) else {
                return 0.0;
            };
            match index {
                0 => pad.value(Axis::LeftStickX),
                1 => -pad.value(Axis::LeftStickY),
                2 => pad.value(Axis::RightStickX),
                3 => -pad.value(Axis::RightStickY),
                4 => pad.button_data(Button::LeftTrigger2).map_or(0.0, |data| data.value()),
                5 => pad.button_data(Button::RightTrigger2).map_or(0.0, |data| data.value()),
                _ => 0.0,
            }
        }

        pub fn rumble(&mut self, id: usize, low: f32, high: f32, ms: u32) -> bool {
            let Some(pad_id) = self.gilrs_id(id) else {
                return false;
            };
            let Some(gilrs) = &mut self.gilrs else {
                return false;
            };
            if !gilrs.gamepad(pad_id).is_ff_supported() {
                return false;
            }
            let magnitude = |value: f32| (value.clamp(0.0, 1.0) * f32::from(u16::MAX)) as u16;
            let scheduling = Replay { play_for: Ticks::from_ms(ms), ..Default::default() };
            let effect = EffectBuilder::new()
                .add_effect(BaseEffect {
                    kind: BaseEffectType::Strong { magnitude: magnitude(low) },
                    scheduling,
                    envelope: Default::default(),
                })
                .add_effect(BaseEffect {
                    kind: BaseEffectType::Weak { magnitude: magnitude(high) },
                    scheduling,
                    envelope: Default::default(),
                })
                .gamepads(&[pad_id])
                .finish(gilrs);
            match effect {
                Ok(effect) if effect.play().is_ok() => {
                    // Dropping an effect stops it, so it is kept until done.
                    let until = Instant::now() + Duration::from_millis(u64::from(ms));
                    self.rumbling.insert(id, (effect, until));
                    true
                }
                _ => false,
            }
        }
    }
}

#[cfg(not(feature = "gamepads"))]
mod pads {
    pub struct Pads {
        pub error: Option<String>,
    }

    impl Pads {
        pub fn open() -> Self {
            Self { error: Some("this build has no gamepad support (the gamepads feature is off)".into()) }
        }
        pub fn poll(&mut self) {}
        pub fn ids(&self) -> Vec<usize> {
            Vec::new()
        }
        pub fn name(&self, _id: usize) -> Option<String> {
            None
        }
        pub fn button(&self, _id: usize, _index: usize) -> bool {
            false
        }
        pub fn axis(&self, _id: usize, _index: usize) -> f32 {
            0.0
        }
        pub fn rumble(&mut self, _id: usize, _low: f32, _high: f32, _ms: u32) -> bool {
            false
        }
    }
}

/// Every connected gamepad.
///
/// `poll` once a frame, then read: buttons and axes are as of that poll.
/// Ids are stable while a pad stays connected, and not reused while it is.
#[pyclass(unsendable)]
pub struct NativeGamepads {
    pads: pads::Pads,
}

#[pymethods]
impl NativeGamepads {
    /// Start watching for gamepads.
    #[new]
    fn new() -> Self {
        Self { pads: pads::Pads::open() }
    }

    /// Why gamepads cannot be read here, or None when they can.
    #[getter]
    fn error(&self) -> Option<String> {
        self.pads.error.clone()
    }

    /// Take in every event since the last poll: presses, moves, hot-plugs.
    fn poll(&mut self) {
        self.pads.poll();
    }

    /// The connected pads' ids, in the order they were found.
    fn ids(&self) -> Vec<usize> {
        self.pads.ids()
    }

    /// A pad's name, or None for one no longer connected.
    fn name(&self, id: usize) -> Option<String> {
        self.pads.name(id)
    }

    /// Whether a button is held, by `GamepadButton` value.
    fn button(&self, id: usize, index: usize) -> bool {
        self.pads.button(id, index)
    }

    /// An axis, by `GamepadAxis` value: sticks -1 to 1 with y down,
    /// triggers 0 to 1.
    fn axis(&self, id: usize, index: usize) -> f32 {
        self.pads.axis(id, index)
    }

    /// Rumble for `ms` milliseconds; returns whether the pad can.
    fn rumble(&mut self, id: usize, low: f32, high: f32, ms: u32) -> bool {
        self.pads.rumble(id, low, high, ms)
    }

    /// How many buttons every pad reports.
    #[classattr]
    const BUTTONS: usize = BUTTON_COUNT;

    /// How many axes every pad reports.
    #[classattr]
    const AXES: usize = AXIS_COUNT;
}
