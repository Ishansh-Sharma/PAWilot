# Paw's kitten frames

`kitten-sprites.png` is an original AI-generated photorealistic silver tabby kitten animation sheet, created for PAWilot on 2026-10-29. It is not footage of a real animal. No third-party cat artwork was copied.

4 columns × 4 rows, row-major order: 0–7 walking left; 8–11 seated/attentive/blink; 12–15 sleeping. The renderer crops cells at runtime, aligns their alpha silhouettes to a shared ground line, and mirrors walking when facing right. Preserve the alpha channel.

Interaction and alpha-frame approach researched from [andyy-yang/desktop-cat](https://github.com/andyy-yang/desktop-cat) (MIT, Andy Yang). That implementation uses real-video frames, silhouette hit testing, bounded locomotion, and pause-on-drag. PAWilot's Swift implementation is original; no upstream source was copied.
