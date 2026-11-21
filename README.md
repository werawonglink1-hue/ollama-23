# Social Video Studio: สตูดิโอคลิปเล่าเรื่องภาษาไทย

| ส่วน | ที่อยู่ |
|---|---|
| เว็บตัดต่อ (เปิด `index.html` ใน Chrome/Edge) | [`video-studio-web/`](video-studio-web/README.md) |
| Skill สำหรับ Claude Code | [`.claude/skills/social-video-studio/`](.claude/skills/social-video-studio/SKILL.md) |
| ทีม Agent (ผู้กำกับ, นักเขียนสคริปต์, อาร์ตไดเรกเตอร์, ซับ+ซาวด์, ตัดต่อ) | [`.claude/agents/`](.claude/agents/) |

กรอกข้อมูลครั้งเดียวได้ 1–5 คลิป ค่าเริ่มต้นเป็นแบบ "สารคดีคอลลาจ" ตามคลิปตัวอย่างพื้นฐาน
(ป้ายปี หัวข้อ ขอบกระดาษฉีก ซับเด้งคำต่อคำ) และเลือกสไตล์อื่นได้จากดรอปดาวน์ เช่น เล่าเรื่องละมุน ครูหน่อง มานะ
ส่งออกได้ทั้งแนวตั้ง 9:16 และแนวนอน 16:9

เรนเดอร์ด้วย ffmpeg:

```bash
python3 .claude/skills/social-video-studio/scripts/render.py .claude/skills/social-video-studio/templates/project.example.json --out out/
```
