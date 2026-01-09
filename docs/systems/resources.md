# Resource Management

The `ResourceManager` (`pyguara.resources`) is the central asset hub.

## Features

- **Unified Access**: Load assets via `manager.load("path/to/asset.png", Texture)`.
- **Type Safety**: Enforces return types (raises error if you load a Sound as a Texture).
- **Caching**: Implements the Flyweight pattern to ensure assets are loaded only once.
- **Indexing**: Scans directories to allow loading files by filename (e.g., "player") instead of full path.

## Loaders
The system uses the **Strategy Pattern** for loading different file types.
- `JsonLoader`: Loads `.json` into `DataResource`.
- `PygameImageLoader`: Loads images into `Texture`.
- `PygameSoundLoader`: Loads audio into `AudioClip`.

---

# Audio System

The `IAudioSystem` (`pyguara.audio`) protocol abstracts audio playback.

- **SFX**: "Fire and forget" sound effects (`play_sfx`).
- **Music**: Streamed audio with looping and fading (`play_music`).
- **Backends**: Currently implemented via `PygameAudioSystem`.

---

# Persistence

The persistence layer (`pyguara.persistence`) handles Saving and Loading game data.

- **Serialization**: Supports JSON (default) and Binary/Pickle formats.
- **Integrity**: Calculates MD5 checksums to detect save file corruption.
- **Metadata**: Stores timestamps, engine version, and save version alongside data for migration support.
