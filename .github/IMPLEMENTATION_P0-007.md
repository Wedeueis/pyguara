# Implementation Plan: P0-007 Audio System Implementation

**Issue ID:** P0-007
**Priority:** Critical (P0)
**Assignee:** TBD
**Status:** Ready
**Branch:** `feature/P0-007-audio-system`

## Summary

Implement complete audio system with music playback, sound effects, volume control, and basic 2D positional audio.

## Files to Create/Modify

**New Files:**
- `pyguara/audio/manager.py` (AudioManager class)
- `pyguara/audio/backends/pygame_audio.py` (PygameAudioBackend)
- `pyguara/audio/types.py` (AudioClip, AudioSettings, enums)
- `pyguara/audio/protocols.py` (IAudioBackend protocol)
- `tests/test_audio.py` (comprehensive audio tests)

**Modified Files:**
- `pyguara/audio/__init__.py` (export public API)
- `pyguara/application/bootstrap.py` (register AudioManager in DI)
- `pyguara/config/types.py` (add audio configuration)

## Implementation Checklist

### Step 1: Define Audio Types (2 hours)
- [ ] Create `AudioType` enum (MUSIC, SFX, VOICE)
- [ ] Create `AudioClip` dataclass
- [ ] Create `AudioSettings` dataclass
- [ ] Create `IAudioBackend` protocol
- [ ] Add audio config to game settings

### Step 2: Implement Pygame Audio Backend (4 hours)
- [ ] Initialize pygame.mixer with settings
- [ ] Implement music loading and playback
- [ ] Implement sound effect loading and playback
- [ ] Implement stereo panning for 2D audio
- [ ] Implement volume control (master, music, sfx)
- [ ] Implement fade in/out for music
- [ ] Handle channel allocation

### Step 3: Implement AudioManager (5 hours)
- [ ] Resource caching integration
- [ ] Listener position tracking
- [ ] `play_music()` with looping and fade
- [ ] `play_sound()` with volume and position
- [ ] `stop_music()` with fade out
- [ ] Volume control methods (master, music, sfx)
- [ ] 2D positional audio calculation (pan based on position)
- [ ] Audio stats/debugging

### Step 4: Integrate with Application (1 hour)
- [ ] Register AudioManager in DI container
- [ ] Add audio settings to config system
- [ ] Ensure proper initialization order
- [ ] Handle cleanup on shutdown

### Step 5: Advanced Features (3 hours)
- [ ] Audio groups/categories (for fine-grained control)
- [ ] Ducking (lower music when SFX plays)
- [ ] Distance-based attenuation
- [ ] Audio mixing/channel management
- [ ] Pause/resume functionality

### Step 6: Comprehensive Testing (4 hours)
- [ ] Test: Music playback with looping
- [ ] Test: Sound effect playback
- [ ] Test: Volume controls work correctly
- [ ] Test: Spatial audio panning
- [ ] Test: Multiple sounds can play simultaneously
- [ ] Test: Fade in/out works
- [ ] Test: Resource caching (don't reload same file)
- [ ] Mock pygame.mixer for unit tests
- [ ] Integration test with actual audio files

### Step 7: Documentation (2 hours)
- [ ] API documentation for AudioManager
- [ ] Tutorial: Adding sound to your game
- [ ] Best practices: Audio performance
- [ ] Supported audio formats (WAV, OGG, MP3)
- [ ] Example: Background music with sound effects

## Acceptance Criteria

- [ ] Can play music with looping
- [ ] Can play sound effects with volume/pitch variation
- [ ] 2D positional audio works (left/right pan)
- [ ] Master, music, and SFX volume controls work independently
- [ ] Audio files loaded via ResourceManager
- [ ] Fade in/out animations supported
- [ ] No audio crackling or popping
- [ ] Can handle 32+ simultaneous sounds
- [ ] Tests pass (pytest tests/test_audio.py)
- [ ] Type checking passes (mypy pyguara/audio/)
- [ ] Example game uses audio system

## Testing Commands

```bash
# Unit tests
pytest tests/test_audio.py -v

# Integration tests
pytest tests/integration/test_audio_integration.py -v

# Type check
mypy pyguara/audio/

# Manual test (requires audio files)
python examples/audio_demo.py
```

## Implementation Reference

See: `docs/dev/backlog/2026-01-09-product-enhancement-proposal.md` Section 8.3
(Complete implementation with 300+ lines of code provided in PEP)

## Dependencies

- pygame-ce ≥ 2.5.6 (pygame.mixer API)
- Audio files for testing (WAV/OGG recommended)

## Performance Targets

- < 5ms latency for sound playback
- Support 32+ simultaneous channels
- Music streaming (no loading delays)
- < 50ms for sound effect load (cached)

## Audio Format Support

**Required:**
- WAV (uncompressed, universally supported)
- OGG (compressed, good quality/size ratio)

**Optional (pygame.mixer support):**
- MP3 (patent-free now, widely used)
- FLAC (lossless, large files)

## Future Enhancements (Post-P0)

- 3D spatial audio (distance, direction)
- Audio effects (reverb, echo, filters)
- Dynamic music system (layers, transitions)
- Audio compression on load
- Streaming for large music files
- Audio visualization support

## Estimated Effort

- Implementation: 15 hours
- Testing: 4 hours
- Documentation: 2 hours
- **Total: 21 hours (~3 days)**

## Implementation Priority

**Week 2 of Phase 1** - Parallel with gamepad support
Audio is critical for game feel and cannot be left as a stub for any production release.

## Critical Notes

- **No blocking loads**: Music should stream, SFX should be pre-loaded
- **Channel management**: Must handle running out of channels gracefully
- **Thread safety**: pygame.mixer is NOT thread-safe, all calls on main thread
- **Format compatibility**: Test on all target platforms (Linux/Windows/Mac)
