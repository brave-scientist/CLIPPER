# Custom Fonts for ClipSnap Subtitles

ClipSnap uses **Montserrat ExtraBold** for punchy, viral short-form video captions.

### How to install Montserrat ExtraBold:
1. Download the Montserrat font family from Google Fonts:
   👉 https://fonts.google.com/specimen/Montserrat
2. Open the downloaded `.zip` file and find:
   `Montserrat-ExtraBold.ttf` (or `static/Montserrat-ExtraBold.ttf`)
3. Copy or drag `Montserrat-ExtraBold.ttf` into this `fonts/` folder:
   `ClipSnap/fonts/Montserrat-ExtraBold.ttf`

### Fallback Behavior:
If `Montserrat-ExtraBold.ttf` is not found in this directory, FFmpeg will automatically fall back to standard system sans-serif fonts (such as DejaVu Sans, Arial, or Helvetica) without failing the export.
