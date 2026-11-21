---
name: social-video-studio
description: สร้างคลิปเล่าเรื่องภาษาไทยสำหรับโซเชียล (TikTok / Reels / Shorts / YouTube) ครบวงจร — ค่าเริ่มต้นเป็นแบบ "สารคดีคอลลาจ" (พื้นสีต่อบท ป้ายปี หัวข้อ ขอบกระดาษฉีก ฮาล์ฟโทน ซับเด้งคำต่อคำ) ตามคลิปตัวอย่างพื้นฐาน, มีสไตล์ภาพ/ผู้เล่าให้เลือกจากดรอปดาวน์ (สารคดีเล่าชีวิต, เล่าเรื่องละมุน, ครูหน่อง, มานะ ฯลฯ), สคริปต์มีจังหวะเว้นวรรคเล่นอารมณ์, ให้ข้อมูลครั้งเดียวได้ 1–5 คลิป, ซับไทยตรงจังหวะพูด, ส่งออกแนวตั้ง 9:16 และแนวนอน 16:9. ใช้เมื่อผู้ใช้ขอ "ทำคลิป", "เขียนสคริปต์คลิป", "ตัดต่อวิดีโอลงโซเชียล", "ทำซับไทย", "คลิปสารคดี/เล่าชีวิต", "เว็บตัดต่อวิดีโอ" หรือพูดถึงสไตล์ครูหน่อง/มานะ/เล่าเรื่องละมุน.
---

# Social Video Studio (สตูดิโอคลิปเล่าเรื่องภาษาไทย)

Skill นี้มี 3 ส่วน ใช้ร่วมกันหรือแยกกันได้

| ส่วน | ที่อยู่ | ใช้ทำอะไร |
|---|---|---|
| เว็บตัดต่อ | `video-studio-web/index.html` | เปิดในเบราว์เซอร์ กรอกข้อมูลครั้งเดียว ได้ 1–5 คลิป พรีวิวพร้อมเสียงอ่าน ซับ เพลง แล้วดาวน์โหลดวิดีโอ, SRT, project.json |
| สคริปต์เรนเดอร์ | `scripts/build_subs.py`, `scripts/render.py` | สคริปต์เป็นซับ SRT/ASS ที่ตั้งเวลาแล้ว และเรนเดอร์ MP4 ด้วย ffmpeg (9:16 และ/หรือ 16:9) หน้าตาเดียวกับเว็บ |
| ทีม Agent 20 ตำแหน่ง | `.claude/agents/*.md` + `references/team.md` | 5 แผนก: ทำคลิป · โซเชียล · ภาพ/แบรนด์ · ข้อเสนอ/แอด · ทำเว็บ |

อ่านก่อนเริ่มงานทุกครั้ง:
- `references/team.md` — ผังทีม 20 ตำแหน่ง ใครทำอะไร ส่งต่อให้ใคร และโฟลเดอร์ทำงาน
- `references/baseline.md` — ถอดคลิปตัวอย่างพื้นฐาน (สารคดีคอลลาจ) ทั้งภาพ จังหวะ ซับ เสียง ที่ทุกคลิปต้องได้อย่างน้อย
- `references/script-rules.md` — รูปแบบสคริปต์ เครื่องหมายเว้นวรรค `/ // ///` คีย์ในบรรทัดฉาก และโครงเรื่องแต่ละสไตล์
- `references/styles.md` — สไตล์ภาพ ผู้เล่า เพลง ซาวด์ รูปแบบซับ ที่อยู่ในดรอปดาวน์
- `references/subtitle-rules.md` — ซับไทยคำต่อคำ/ทีละวลี ไม่ให้เร็วเกินไป และขนาดคลิปแต่ละแพลตฟอร์ม

## ค่าเริ่มต้น (แบบคลิปตัวอย่างพื้นฐาน)

`visualStyle=collage` · `narratorStyle=doc` · `captionMode=word` · `music=doc` · `speed=normal` · `banner=true` · `formats=9x16,16x9`
ถ้าผู้ใช้เลือกสไตล์อื่นจากดรอปดาวน์ ให้ใช้ค่าตามที่เลือก (เช่น `lamun` + `pastel3d` + ซับทีละวลี ช้า ละมุน)

## ขั้นตอนทำงาน (ทีม 20 ตำแหน่ง)

Claude หลักเป็นโปรดิวเซอร์ เรียกตำแหน่งใน `.claude/agents/` ตามสายงานใน `references/team.md`:

```
A) ทำคลิป:  Content Creator → Reality Checker → Visual Storyteller → Image Prompt Engineer → Brand Guardian
            → Short-Video Editing Coach → Video Optimization Specialist → Reality Checker
B) โซเชียล: TikTok Strategist + Instagram Curator + Carousel Growth Engine (ขนานกัน) → Brand Guardian → Growth Hacker
C) แอด:     Pricing Analyst → Offer & Lead Gen Strategist → Ad Creative Strategist → Paid Social Strategist
D) ทำเว็บ:  UI Designer → Frontend Developer → Code Reviewer + Security Auditor (ขนานกัน) → Minimal Change Engineer → Reality Checker
```

1. **Content Creator**: brief เป็นแผนซีรีส์ 1–5 คลิป (มุมเล่าไม่ซ้ำ) และสคริปต์ตาม `script-rules.md` (สารคดี: เว้นวรรคระหว่างคำ ใส่ `ป้าย:` `หัวข้อ:` ทุกบท)
2. **Reality Checker**: ตรวจข้อเท็จจริงก่อนลงมือทำภาพ
3. **Visual Storyteller** + **Image Prompt Engineer**: บรรทัดฉาก สตอรีบอร์ด prompt ภาพ; **Brand Guardian** ตรวจแบรนด์/ลิขสิทธิ์
4. **Short-Video Editing Coach**: `build_subs.py` ไม่มีท่อนเร็วเกิน → `render.py` → เปิดดูเฟรม; **Video Optimization Specialist** ตรวจสเปก/ปก/ความดัง
5. **Reality Checker** ตรวจไฟล์จริงก่อนส่งผู้ใช้ แล้วจึงต่อสายงาน B/C ตามที่ผู้ใช้ต้องการ

ถ้าใช้ Agent tool ได้ ให้เรียกตามชื่อไฟล์ (งานที่ขนานกันได้ให้เรียกพร้อมกัน) ถ้าไม่ได้ ให้ทำตามบทบาทเรียงลำดับเองในเซสชันเดียว

## คำสั่งที่ใช้บ่อย

```bash
# สคริปต์เป็นซับ (ดูเวลาแต่ละท่อน + เตือนท่อนที่เร็วเกิน)
python3 .claude/skills/social-video-studio/scripts/build_subs.py script.txt --speed normal --style collage --framed --srt out.srt --ass out.ass

# project.json (จากเว็บ หรือ agent) เป็น MP4
python3 .claude/skills/social-video-studio/scripts/render.py project.json --out out/ --formats 9x16,16x9
```

`render.py` ใช้สื่อที่ผู้ใช้ให้ (รูป/วิดีโอต่อฉาก ไฟล์เสียงพากย์ เพลง) ถ้าไม่มีจะสร้างภาพแทนที่ตามสไตล์ให้ ถ้ามีไฟล์เสียงพากย์ + `timings` (จากโหมด "อัดเสียง/แตะเพื่อซิงก์" ในเว็บ) ซับจะตรงเสียงจริง
ต้องมี `ffmpeg` (มี libass) และ Python 3 + Pillow; ถ้ามี Node.js จะใช้ตัดคำภาษาไทยสำหรับซับคำต่อคำ (ไม่มีก็ตัดตามช่องว่างในสคริปต์)

## Skill อื่นที่ดึงมาใช้

- `artifact-design`: ตอนแก้หน้าตาเว็บ `video-studio-web`
- `anthropic-skills:web-artifacts-builder`: ถ้าต้องการแยกเว็บเป็น React หลายคอมโพเนนต์
- `claude-api`: ตอนแก้โหมด "เขียนสคริปต์ด้วย Claude" ในเว็บ (model id, header)
- `design:ux-copy`: ตรวจข้อความปุ่มและคำอธิบายภาษาไทยในเว็บ
- `engineering:testing-strategy`: ตอนเพิ่มเทสต์ให้ตัวตั้งเวลาซับ

## ข้อควรระวัง

- สไตล์ "ครูหน่อง" และ "มานะ" เป็น **โทนการเล่า** (น้ำเสียง จังหวะ คำลงท้าย) ไม่ใช่การปลอมเป็นบุคคลจริงหรือก๊อปตัวละคร/ภาพจากหนังสือเรียน ตั้งชื่อและออกแบบตัวละครใหม่เสมอ
- คลิปสารคดีเรื่องคนจริง: ใช้ข้อเท็จจริงที่ตรวจสอบได้เท่านั้น ห้ามแต่งตัวเลข ใส่ `เครดิต:` ให้ภาพที่ใช้ และใช้ภาพที่มีสิทธิ์ใช้ (เช่น ครีเอทีฟคอมมอนส์)
- คลิปตัวอย่างมีแถบหัวโฆษณาแอปของคนอื่นและช่วงท้ายเป็นโฆษณา ห้ามคัดลอกแบรนด์หรือข้อความนั้น แถบหัวของเราใช้ชื่อซีรีส์/ช่องของผู้ใช้
- ไม่ใช้เสียงโคลนของคนจริงโดยไม่ได้รับอนุญาต; เพลงและซาวด์ที่สร้างเป็นเสียงสังเคราะห์ปลอดลิขสิทธิ์
