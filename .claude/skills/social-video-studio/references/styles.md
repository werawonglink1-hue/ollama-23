# สไตล์ในดรอปดาวน์

ค่า `id` ตรงกับเว็บ (`video-studio-web/index.html`) และ `render.py`

## สไตล์ภาพบนคลิป (`visualStyle`)

| id | ชื่อ | อ้างอิง | ซับอัตโนมัติ | prompt ภาพ AI (ต่อท้ายฉาก) |
|---|---|---|---|---|
| `collage` (ค่าเริ่มต้น) | สารคดีคอลลาจ กระดาษฉีก | คลิปตัวอย่างพื้นฐาน (`baseline.md`) | คำต่อคำ เหลือง `#FFD21F` | `editorial collage, torn paper edges, halftone dots, duotone archival photo, bold flat color blocks, magazine cut-out style` |
| `pastel3d` | 3D พาสเทลเมืองไทยละมุน | คลิปเล่าเรื่อง "โลกที่ปลาว่ายบนฟ้า" | ทีละวลี เหลืองมะนาว `#E6FF3D` | `soft low-poly 3D diorama, Thai neighborhood shophouses, pastel pink and lavender sky, warm sunset light, toy-like characters with round heads, tilt-shift, gentle` |
| `kinetic` | ดินน้ำมันจัดจ้าน + ตัวหนังสือเด้ง | คลิปดินน้ำมัน/อวกาศ | คำต่อคำ | `claymation 3D characters, bold saturated colors, swirling psychedelic background, kinetic typography, playful` |
| `watercolor` | สีน้ำอบอุ่น | | ทีละวลี | `warm watercolor storybook illustration, paper texture, soft edges, Thai countryside` |
| `anime-dusk` | อนิเมะยามเย็น | | ทีละวลี | `anime background art, golden hour, volumetric light, nostalgic, detailed sky` |
| `papercut` | กระดาษตัดมินิมอล | | ทีละวลี | `layered paper-cut craft, minimal shapes, soft shadows between layers` |
| `neon-night` | เมืองกลางคืนนีออน | | ทีละวลี | `quiet night city street, glowing neon lights, deep blue, bokeh, dreamy` |
| `film` | ฟิล์มเก่าอบอุ่น | | ทีละวลี | `35mm film photo, warm grain, nostalgic Thai street, soft focus` |

### คีย์เพิ่มเติมในบรรทัดฉาก (ใช้ได้ทุกสไตล์ แต่ `collage` ใช้เต็มที่)

`[ฉาก: คำบรรยายภาพ | ป้าย: 1997 | หัวข้อ: ร่างกายไม่ยอมโต | ภาพ: เต็ม|วงกลม | โทน: ขาวดำ | สี: แดง | เครดิต: Wikimedia Commons]`

- `ป้าย` ป้ายปี/ช่วงอายุมุมซ้ายบน · `หัวข้อ` กล่องหัวข้อเอียง · `ภาพ: วงกลม` = สติกเกอร์คนบนวงกลมลายจุด
- `โทน: ขาวดำ` = ภาพดูโอโทนแบบภาพเก่า · `สี:` น้ำเงิน/เหลือง/ฟ้า/แดง/เขียว/น้ำเงินสด/ชมพู/ดำ หรือ `#hex` · `เครดิต:` ข้อความเครดิตภาพ
- ไม่ระบุ `ภาพ:` ระบบสลับให้เอง (ทุกฉากที่ 2 ใน 3 เป็นวงกลม)

## สไตล์ผู้เล่า (`narratorStyle`)

| id | ชื่อ | โทน | คำ/วลีประจำ | ความเร็ว | เพลงเริ่มต้น |
|---|---|---|---|---|---|
| `doc` (ค่าเริ่มต้น) | สารคดีเล่าชีวิต / ตำนาน | กระชับ เร้าใจ บุรุษที่สาม ใช้ปีและตัวเลข | "หมอบอกว่า... แต่วันนี้", "แต่มีอย่างเดียวที่...", "ฝากกดติดตามไว้" | `normal` | `doc` |
| `lamun` | เล่าเรื่องละมุน | อบอุ่น ลึกลับนิด ๆ พูดกับ "คุณ" | "ลองนึกภาพว่า", "และคืนนี้", "ตอนหน้า" | `slow` | `musicbox` |
| `kru-nong` | ครูหน่อง (คุณครูใจดีเล่านิทาน) | ครูอนุบาล-ประถม อ่อนโยน ถาม-รอ-ชม | "เด็ก ๆ จ๋า", "รู้ไหมคะ", "ลองทายสิ", "นิทานเรื่องนี้สอนให้รู้ว่า" | `slow` | `musicbox` |
| `mana` | มานะ (แบบเรียนไทยคลาสสิก) | ประโยคสั้น ง่าย ซ้ำโครง บุรุษที่สาม | "มานะ...", "...ก็...", "แม่ยิ้ม แล้วบอกว่า" | `slow` | `playful` |
| `mystery` | ลึกลับนุ่ม ๆ | กระซิบ ระทึกเบา ๆ | "คุณเคยสังเกตไหม", "มีกฎอยู่ข้อเดียว" | `slow` | `dream` |
| `funny` | ขำอบอุ่น | ยิ้มได้ มุกเบา ๆ | "เดี๋ยวนะ", "มานี่ เดี๋ยวเล่าให้ฟัง" | `normal` | `playful` |

> "ครูหน่อง" และ "มานะ" คือโทนการเล่า ไม่ใช่การเลียนแบบบุคคลจริงหรือก๊อปตัวละคร/ภาพประกอบเดิม

## เพลง (`music`): สังเคราะห์สด ปลอดลิขสิทธิ์ (เว็บใช้ Web Audio, render.py สร้างไฟล์ WAV)

| id | ชื่อ | ลักษณะ |
|---|---|---|
| `doc` | สารคดีเร้าใจ | คอร์ดไมเนอร์ Am–F–C–G, เปียโนโน้ตเขบ็ตวน, จังหวะหัวใจเบา ๆ ทุกจังหวะ (เริ่มบาร์ 3) |
| `musicbox` | กล่องดนตรีละมุน | pad อุ่น + กล่องดนตรีอาร์เปจโจช้า |
| `lofi` | Lo-fi อบอุ่น | คอร์ด 7th นุ่ม + เสียงแผ่นเสียงแตกเบา ๆ |
| `dream` | ฝันกลางคืน | pad ยาว + กระดิ่งไกล ๆ |
| `playful` | สนุกเบา ๆ | พิซซิคาโตเด้ง |
| `none` | ไม่มีเพลง | |

## เสียงประกอบ (`sfx`) ในเว็บ

`paper` (เปลี่ยนบทสไตล์ collage), `whoosh` (เปลี่ยนฉากสไตล์อื่น), `chime`, `pop` (สไตล์ kinetic), `rain`, `wind`
เรียกจาก `{เสียง: ...}`: คำที่มี "ลม" → wind, "ฝน" → rain, "กระดิ่ง/ระฆัง" → chime, "วูบ/ปลิว" → whoosh
(render.py ยังไม่ใส่ SFX: ถ้าต้องการให้ส่งออกวิดีโอจากเว็บ หรือมิกซ์เพิ่มภายหลัง)
