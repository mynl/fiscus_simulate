# Branding assets

Source-of-truth branding for `fiscus_simulate`.

- **Origin:** `../fiscus_art/USED_A_minimalist_2D_flat_vector_icon_of_a_Roman_Style_FIS_colorfu_4720900e-…_2.png`
  (marked `USED_` there so it isn't reused). A "Roman-style FIS" mark — colorful `FIS`
  wordmark over classical columns; fits *fiscus* (Latin).
- `logo-source.png` — the raw copy (2048², white background).
- `master-1024.png` — trimmed + centered square master; the regeneration base.

Web-served copies live in
`src/fiscus_simulate/web/static/fiscus_simulate/branding/`:
`favicon.ico` (48/32/16), `favicon-16.png`, `favicon-32.png`, `apple-touch-icon.png`
(180), `logo-192.png`, `logo-512.png`.

## Regenerate (ImageMagick 7)

```sh
M=assets/branding/master-1024.png
OUT=src/fiscus_simulate/web/static/fiscus_simulate/branding
magick assets/branding/logo-source.png -trim +repage -resize 900x900 \
    -background white -gravity center -extent 1024x1024 "$M"
magick "$M" -resize 512x512 "$OUT/logo-512.png"
magick "$M" -resize 192x192 "$OUT/logo-192.png"
magick "$M" -resize 180x180 "$OUT/apple-touch-icon.png"
magick "$M" -resize 32x32   "$OUT/favicon-32.png"
magick "$M" -resize 16x16   "$OUT/favicon-16.png"
magick "$M" -define icon:auto-resize=48,32,16 "$OUT/favicon.ico"
```

Note: white (not transparent) background — fine for tabs and a bordered navbar mark.
Revisit transparency/dark-mode variant at the Stage 6 web polish if wanted.
