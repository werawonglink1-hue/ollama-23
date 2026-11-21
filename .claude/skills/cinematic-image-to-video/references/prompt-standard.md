# มาตรฐาน prompt: CINEMATIC 3D ANIMATION — IMAGE TO VIDEO

ต้นฉบับจากเจ้าของช่อง (ใช้เป็นมาตรฐานของทุกช็อตที่ทำเป็นวิดีโอ ห้ามตัดข้อกำหนดออก):

```
CINEMATIC 3D ANIMATION — IMAGE TO VIDEO
Transform the provided static image into a high-quality cinematic 3D animated movie scene.
Character Consistency:
Preserve the exact same female character throughout the entire animation. Maintain identical facial features, hairstyle, black ponytail with yellow scrunchie, green knitted cardigan, white shirt, navy trousers, white sneakers, body proportions and character design.
Character Animation:
Create natural human-like movements with realistic body mechanics. Include subtle breathing, natural blinking, eye movement, head tilting, hand gestures, and realistic facial expressions. All movements should feel smooth, organic and emotionally expressive.
Camera Animation:
Use professional cinematic camera movements, including slow dolly-in, tracking shots, subtle camera pans, cinematic close-ups and smooth transitions. Avoid static camera framing unless artistically necessary.
Environment Animation:
Animate environmental elements naturally. Moving trains, flowing wind, subtle hair movement, reflections on wet floors, flickering city lights, atmospheric particles, steam rising from hot food and realistic environmental lighting.
Visual Quality:
High-end 3D animated feature film quality, detailed character modeling, realistic fabric simulation, expressive facial animation, cinematic depth of field, global illumination, physically based rendering, soft volumetric lighting and beautiful cinematic composition.
Animation Requirements:
* Smooth continuous motion.
* Natural movement without sudden jumps.
* Preserve original scene composition.
* Maintain character identity and clothing consistency.
* No facial distortion or body deformation.
* No extra fingers or duplicated limbs.
* No random object generation.
* No sudden scene changes.
* No unwanted text or subtitles.
Output: Cinematic 3D animated movie, 4K visual quality, 24 FPS, vertical 9:16 aspect ratio, emotionally engaging storytelling.
```

## ใช้กับทุกตัวละครและทุกช็อตอย่างไร (`scripts/i2v_prompt.py`)

| หัวข้อในมาตรฐาน | ส่วนของ prompt | มาจาก |
|---|---|---|
| Transform the provided static image… | ประโยคเปิด + สัดส่วนภาพ | `formats` ของโปรเจกต์ (9:16 / 16:9) |
| Character Consistency | รูปลักษณ์ + ชุดของตัวละครในช็อต และบอกให้ยึดภาพแรกกับ character sheet | `characters[].look` + `outfit` ของตัวที่อยู่ใน `ตัวละคร:` ของฉาก · sheet แนบเป็น `image_references` เมื่อโมเดลรองรับ |
| (การกระทำของช็อต) | Action in this shot | `scenes[j].motionPrompt` (อังกฤษ) › `เคลื่อนไหว:` (อังกฤษแม่นสุด) › `ท่าทาง:` + `เคลื่อนไหว:` ภาษาไทย |
| Character Animation | หายใจ กะพริบตา กลอกตา เอียงศีรษะ มือ สีหน้า | ข้อความคงที่ (ใส่เฉพาะช็อตที่มีตัวละคร) |
| Camera Animation | dolly-in / tracking / pan / tilt | `กล้อง:` ของฉาก (ไม่ใส่ = วนตามสไตล์) |
| Environment Animation | รถไฟ ไอน้ำ พื้นเปียก ไฟเมือง ลม ฯลฯ | **เฉพาะสิ่งที่มีในฉากนั้น** (ค้นคำจากคำบรรยายฉาก/ท่าทาง/เคลื่อนไหว) + ผมไหวเบา ๆ และฝุ่นละอองในแสงเสมอ — ห้ามใส่รถไฟในฉากร้านข้าวต้ม เพราะขัดข้อ "No random object generation" |
| Visual Quality | คงที่ + "ultra-detailed 4K look, 24 fps feel" | — |
| Animation Requirements | ข้อห้ามทั้งหมดเป็นประโยคเดียว | — |
| Output 4K / 24 FPS / 9:16 | ความละเอียดตามงบ (ดูตารางราคาใน SKILL.md) · 24 fps = `"fps": 24` ใน project.json ตอน render · 9:16 = `aspect_ratio` | — |

## ตัวอย่าง prompt ที่สร้างได้ (มิ้นท์ ฉาก 4 โคลสอัพน้ำตา)

```
Animate this exact still frame into a vertical 9:16 shot from a high-end cinematic 3D animated feature film.
Character consistency: keep exactly the same character throughout the whole shot (24-year-old Thai woman, warm
light-tan skin, slim, oval face with high rounded cheekbones, almond dark-brown eyes, long straight black hair in a
low ponytail with a mustard-yellow scrunchie, mint-green knit cardigan over a white blouse, navy wide-leg trousers,
white canvas sneakers, navy lanyard with a blank white ID card), with identical facial features, hairstyle, clothing,
colors, body proportions and character design as in the start frame and the attached character reference sheet.
Action in this shot: a tear slowly rolls down her cheek, then a small trembling smile spreads across her face as she
reads the message. Character animation: natural human-like movement … Camera: slow cinematic dolly-in toward the
subject, smooth and steady, cinematic. Environment animation: the phone screen glow softly lighting the face, a single
tear slowly rolling down the cheek, subtle hair movement and fine atmospheric particles drifting in the light.
Visual quality: … Requirements: … no text, captions, subtitles, logos or watermark.
```

ดู prompt จริงของโปรเจกต์: `python3 .claude/skills/cinematic-image-to-video/scripts/i2v_prompt.py project.json --scene 4`
