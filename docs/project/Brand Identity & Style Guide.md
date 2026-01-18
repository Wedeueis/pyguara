# PyGuara Brand Identity & Style Guide

**Version:** 1.0
**Date:** 2026-01-17
**Status:** Approved

---

## 1. Brand Essence

PyGuara is not just a game engine; it is a celebration of **Native Intelligence**. Like the fauna of the Brazilian Cerrado, it is distinctive, adaptable, and built to thrive in specific conditions. It rejects the generic "grey box" aesthetic of standard software in favor of warmth, personality, and biological metaphors.

### 1.1 Core Metaphor: "The Symbiosis"

The brand is built on the relationship between two iconic Cerrado species:

* **The Maned Wolf (Lobo Guará):** Represents the **Engine Core** (ECS/Physics). Grounded, powerful, adaptable long legs for traversing difficult terrain (complex systems).
* **The Aplomado Falcon (Falcão-de-coleira):** Represents the **High-Level Logic** (Events/Scripting). Agile, observant, riding above the core to direct action.

### 1.2 Voice & Tone

* **Intelligent but Wild:** We use technical precision mixed with ecological terminology.
* **Distinctive:** We avoid standard naming (e.g., "Output Window") in favor of thematic naming ("Papagaio Shell").
* **Crepuscular:** Our aesthetic is dark, high-contrast, and warm, evoking the twilight hours when the Guará is active.

**Tagline:** *"Wildly Adaptable."* / *"Código em Movimento."*

---

## 2. Visual Identity

### 2.1 Logo System

* **Primary Logomark:** A silhouette of the Maned Wolf walking, with the Aplomado Falcon perched on its shoulder or hovering just above. The curve of the Wolf's ear should flow into the Falcon's wing.
* **The Glyph (Icon):** A simplified, single-color symbol (Paw Print or stylized "G" with a tail) for use in file icons (`.pyg`), favicons, and window title bars.
* **Wordmark:** "PyGuara" set in **Archivo Black**, with the "G" stylized to suggest a tail.

### 2.2 Color Palette: "The Cerrado Dark"

This palette replaces the generic software "blues and grays" with earth tones derived from the biome.

| Role | Color Name | Hex Code | Usage |
| --- | --- | --- | --- |
| **Primary Action** | **Guará Orange** | `#D95204` | Active buttons, selection borders, the "Play" button. |
| **Structure/Chrome** | **Aplomado Slate** | `#3B414D` | Window headers, panel backgrounds, toolbars. |
| **Background** | **Night Charcoal** | `#2C2C2C` | The main viewport, code editor background. |
| **Deep Background** | **Shadow Black** | `#1A1A1A` | Console input areas, modal dimming. |
| **Text/Content** | **Fur Cream** | `#F0EAD6` | All primary text, iconography. High readability. |
| **Success/System** | **Bamboo Green** | `#6B8E23` | "Build Success", boolean `True`, active processes. |
| **Warning/Accent** | **Falcon Cinnamon** | `#C18C5D` | Warnings, code comments, secondary highlights. |

### 2.3 Typography

* **Headings / Marketing:** **Archivo** (Omnibus-Type).
* *Why:* A South American grotesque sans-serif. It feels technical, sturdy, yet modern.


* **UI / Code:** **JetBrains Mono** or **Fira Code**.
* *Why:* Industry standard for readability. Ligatures are essential for Python (`->`, `!=`).



---

## 3. Product Naming Convention

To reinforce the identity, subsystems within the Editor are renamed to match the fauna theme.

| Standard Name | PyGuara Name | Rationale |
| --- | --- | --- |
| **The Editor** | **Toca** (The Den) | The home/hub where everything is safe and managed. |
| **Job System** | **Formiga** (Ant) | Small workers handling massive tasks in parallel. |
| **Asset Manager** | **Arara** (Macaw) | Colorful, loud, handles visual/audio files. |
| **Console/Shell** | **Papagaio** (Parrot) | Echoes commands, repeats output. |
| **Releases** | **Flora Names** | v0.1 *Araucária*, v0.2 *Buriti*, v1.0 *Cerrado*. |

---

## 4. Technical Implementation

### 4.1 Theme Preset Code

Add this to `pyguara/ui/theme_presets.py` to enable the brand identity in the engine immediately.

```python
def _create_cerrado_theme() -> UITheme:
    """Create the official PyGuara 'Cerrado' brand theme."""
    return UITheme(
        name="cerrado",
        colors=ColorScheme(
            # Guará Orange - The Hero Color
            primary=Color(217, 82, 4),      # #D95204

            # Bamboo Green - Success/System
            secondary=Color(107, 142, 35),  # #6B8E23

            # Night Charcoal - Main Background
            background=Color(44, 44, 44),   # #2C2C2C

            # Fur Cream - Readable Text
            text=Color(240, 234, 214),      # #F0EAD6

            # Aplomado Slate - Borders & Structure
            border=Color(59, 65, 77),       # #3B414D

            # Subtle Orange overlay for hovers
            hover_overlay=Color(217, 82, 4, 40),

            # Darker Slate for press states
            press_overlay=Color(0, 0, 0, 80),
        ),
        spacing=SpacingScheme(padding=8, margin=4, gap=8),
        fonts=FontScheme(
            family="Archivo",  # Requires loading the font file
            size_small=12,
            size_normal=16,
            size_large=24,
            size_title=32
        ),
        borders=BorderScheme(width=2, radius=4, color=Color(59, 65, 77)),
        shadows=ShadowScheme(
            enabled=True,
            offset_x=2,
            offset_y=2,
            blur=5,
            color=Color(26, 26, 26, 180), # Shadow Black
        ),
    )

# Update the ThemeConstants dataclass
@dataclass(frozen=True)
class ThemeConstants:
    # ... existing themes ...
    CERRADO = _create_cerrado_theme()

```

### 4.2 Asset Checklist (Beta Launch)

To fully realize this brand, the following assets must be produced:

1. **Splash Screen (1920x1080):**
* High-fidelity digital painting of the Wolf & Falcon in a stylized, low-poly or silhouette Cerrado landscape.
* Must feature the logo prominently.


2. **App Icons:**
* `.ico` / `.png` files generated from the Glyph.


3. **Default Project Template:**
* Instead of an empty gray world, new projects should spawn a **Voxel Maned Wolf** standing on a patch of grass.


4. **Social Media Kit:**
* Twitter Banner (1500x500): "Native Intelligence" tagline with brand colors.
* Profile Picture: The Glyph on a Charcoal background.
