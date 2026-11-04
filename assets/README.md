# Royalty-Free Music & Sound Effects Guide for ClipSnap

This folder contains background music tracks and sound effects (SFX) that are automatically overlaid onto your exported clips.

---

## 🎵 Background Music

### Location
Place `.mp3` or `.wav` music tracks in:
```
assets/music/
```

### Free Sources for Royalty-Free Music
1. **YouTube Audio Library** (Free & Safe for monetization):
   👉 [https://studio.youtube.com](https://studio.youtube.com) -> Audio Library
   *(Recommended genres: Hip-Hop, Ambient, Lo-Fi, Electronic, Vlog/Upbeat)*
2. **Pixabay Music** (Free for commercial use, no attribution required):
   👉 [https://pixabay.com/music/](https://pixabay.com/music/)
3. **Free Music Archive (FMA)**:
   👉 [https://freemusicarchive.org/](https://freemusicarchive.org/)
4. **Incompetech (Kevin MacLeod)**:
   👉 [https://incompetech.com/](https://incompetech.com/)

### How ClipSnap mixes music:
- Automatically loops or trims to match clip duration.
- Normalizes volume to **-22 dB**.
- Applies a **1.0s fade-in** and **1.5s fade-out**.
- Uses **sidechain compression / audio ducking** so the music dips automatically while a speaker talks.

---

## 🔊 Sound Effects (SFX)

### Expected Folder and File Names
Place sound effects in:
```
assets/sfx/
├── whoosh.mp3   (or whoosh.wav) - For hook transitions, text reveals, or fast cuts
├── pop.mp3      (or pop.wav)    - For caption pop animations or bullet points
└── ding.mp3     (or ding.wav)   - For key emphasis, tips, and value statements
```

### Free Sources for Sound Effects
1. **Pixabay Sound Effects** (Free CC0 / royalty-free):
   👉 [https://pixabay.com/sound-effects/](https://pixabay.com/sound-effects/)
   *(Search for "whoosh", "pop bubble", "bell ding")*
2. **Freesound.org** (Filter by Creative Commons 0):
   👉 [https://freesound.org/](https://freesound.org/)
3. **BBC Sound Effects** (Personal & educational use):
   👉 [https://sound-effects.bbcrewind.co.uk/](https://sound-effects.bbcrewind.co.uk/)

### How ClipSnap mixes SFX:
- Uses Gemini AI to pinpoint the top key moments (up to 3 per clip).
- Overlays sound effects at exact timestamps at **-12 dB** without distorting speech.
